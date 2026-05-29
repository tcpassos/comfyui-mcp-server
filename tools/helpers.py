"""Shared helper functions for tool implementations"""

import json
import logging
from typing import Any, Dict, Optional

from mcp.types import ImageContent, TextContent

from asset_processor import encode_preview_for_mcp, fetch_asset_bytes, get_cache_key

logger = logging.getLogger("MCP_Server")


_SEED_KEYS = ("seed", "noise_seed")


def _extract_seed(workflow: Optional[Dict[str, Any]]) -> Optional[int]:
    """Scan a rendered ComfyUI workflow for the primary integer seed.

    Looks at any node whose `inputs` contain a literal integer under a known seed key
    (`seed` or `noise_seed`). Skips graph references (lists/tuples). Returns the seed
    from the first matching node in insertion order, or None if no seed is found.
    """
    if not isinstance(workflow, dict):
        return None
    for node in workflow.values():
        inputs = node.get("inputs") if isinstance(node, dict) else None
        if not isinstance(inputs, dict):
            continue
        for key in _SEED_KEYS:
            value = inputs.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def register_and_build_response(
    result: Dict[str, Any],
    workflow_id: str,
    asset_registry,
    tool_name: Optional[str] = None,
    return_inline_preview: bool = False,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Helper function to register asset and build response data.

    Eliminates code duplication between run_workflow() and _register_workflow_tool().

    Args:
        result: Result dict from comfyui_client.run_custom_workflow()
        workflow_id: Workflow ID
        asset_registry: AssetRegistry instance
        tool_name: Optional tool name (for workflow-backed tools)
        return_inline_preview: Whether to include inline preview
        session_id: Optional session identifier for conversation filtering

    Returns:
        Response data dict with asset_id, asset_url, metadata, etc.
        If the workflow is still running (timeout), returns a job handle dict instead.
    """
    # If the result is a "still running" job handle, pass it through directly
    if result.get("status") == "running":
        return result

    # Register asset in registry using stable identity
    asset_metadata = result.get("asset_metadata", {})
    metadata = {"workflow_id": workflow_id}
    if tool_name:
        metadata["tool"] = tool_name
    
    asset_record = asset_registry.register_asset(
        filename=result.get("filename", ""),
        subfolder=result.get("subfolder", ""),
        folder_type=result.get("folder_type", "output"),
        workflow_id=workflow_id,
        prompt_id=result.get("prompt_id", ""),
        mime_type=asset_metadata.get("mime_type"),
        width=asset_metadata.get("width"),
        height=asset_metadata.get("height"),
        bytes_size=asset_metadata.get("bytes_size"),
        comfy_history=result.get("comfy_history"),
        submitted_workflow=result.get("submitted_workflow"),
        metadata=metadata,
        session_id=session_id
    )
    
    # Build response data
    asset_url = asset_record.asset_url or result.get("asset_url", "")
    seed = _extract_seed(result.get("submitted_workflow"))
    response_data = {
        "asset_id": asset_record.asset_id,
        "asset_url": asset_url,
        "image_url": asset_url,
        "filename": asset_record.filename,
        "subfolder": asset_record.subfolder,
        "folder_type": asset_record.folder_type,
        "workflow_id": workflow_id,
        "prompt_id": result.get("prompt_id"),
        "mime_type": asset_record.mime_type,
        "width": asset_record.width,
        "height": asset_record.height,
        "bytes_size": asset_record.bytes_size,
        "seed": seed,
    }

    if tool_name:
        response_data["tool"] = tool_name

    # Include inline preview if requested
    if return_inline_preview:
        try:
            supported_types = ("image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif")
            if asset_record.mime_type in supported_types:
                preview_url = asset_url or asset_record.get_asset_url(asset_registry.comfyui_base_url)
                image_bytes = fetch_asset_bytes(preview_url)
                cache_key = get_cache_key(asset_record.asset_id, 512, 80)
                encoded = encode_preview_for_mcp(
                    image_bytes,
                    max_dim=512,
                    max_b64_chars=500_000,
                    quality=80,
                    cache_key=cache_key,
                )
                # Return MCP content list: ImageContent lets the model "see" the image
                # via its vision capability. TextContent carries the metadata.
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(response_data, ensure_ascii=False),
                    ),
                    ImageContent(
                        type="image",
                        data=encoded.b64,
                        mimeType=encoded.mime_type,
                    ),
                ]
        except Exception as e:
            logger.warning("Failed to generate inline preview: %s", e)

    # Include base64 image data if available (legacy)
    if "image_base64" in result:
        response_data["image_base64"] = result["image_base64"]
        response_data["image_mime_type"] = result.get("image_mime_type", "image/png")

    return response_data

