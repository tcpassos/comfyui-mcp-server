"""Seed lock for generate_anima.

The Anima workflow used to hardcode the KSampler seed (node 166:165), so the
`generate_anima` tool had no `seed` parameter: every run used a fixed/unknown
seed and the returned `seed` was never captured. Turning that literal into a
`PARAM_INT_SEED` placeholder makes the seed a real optional parameter —
reproducible when provided, random when omitted, and always read back via
`_extract_seed`. This is the prerequisite for editing a finished image.
"""

from pathlib import Path

import pytest

from managers.workflow_manager import WorkflowManager
from tools.helpers import _extract_seed

WORKFLOWS_DIR = Path(__file__).parent.parent / "workflows"
SEED_NODE = "166:165"  # Seed (rgthree) feeding the sampler's RandomNoise


@pytest.fixture
def anima_definition():
    """The auto-registered tool definition for the real generate_anima workflow."""
    mgr = WorkflowManager(WORKFLOWS_DIR)
    defn = next((d for d in mgr.tool_definitions if d.workflow_id == "generate_anima"), None)
    assert defn is not None, "generate_anima workflow should auto-register a tool"
    return mgr, defn


class TestGenerateAnimaSeedParam:
    def test_seed_is_an_optional_parameter(self, anima_definition):
        _, defn = anima_definition
        assert "seed" in defn.parameters, (
            f"generate_anima should expose a 'seed' param, got: {list(defn.parameters)}"
        )
        seed_param = defn.parameters["seed"]
        assert seed_param.annotation is int
        assert seed_param.required is False  # omitting it must stay valid

    def test_render_without_seed_generates_a_random_int(self, anima_definition):
        mgr, defn = anima_definition
        wf = mgr.render_workflow(defn, {"prompt": "1girl, solo"})
        seed = wf[SEED_NODE]["inputs"]["seed"]
        assert isinstance(seed, int) and not isinstance(seed, bool)
        # No leftover placeholder string.
        assert seed != "PARAM_INT_SEED"

    def test_render_without_seed_varies_between_calls(self, anima_definition):
        mgr, defn = anima_definition
        a = mgr.render_workflow(defn, {"prompt": "x"})[SEED_NODE]["inputs"]["seed"]
        b = mgr.render_workflow(defn, {"prompt": "x"})[SEED_NODE]["inputs"]["seed"]
        # Random 32-bit space — a collision here is astronomically unlikely.
        assert a != b

    def test_render_respects_a_provided_seed(self, anima_definition):
        mgr, defn = anima_definition
        wf = mgr.render_workflow(defn, {"prompt": "x", "seed": 123456789})
        assert wf[SEED_NODE]["inputs"]["seed"] == 123456789

    def test_extract_seed_reads_back_the_provided_seed(self, anima_definition):
        """The same value the orchestrator passes is what _extract_seed returns,
        so iteration.seed is populated and the image is reproducible."""
        mgr, defn = anima_definition
        wf = mgr.render_workflow(defn, {"prompt": "x", "seed": 987654321})
        assert _extract_seed(wf) == 987654321

    def test_extract_seed_reads_back_a_random_seed(self, anima_definition):
        mgr, defn = anima_definition
        wf = mgr.render_workflow(defn, {"prompt": "x"})
        assert _extract_seed(wf) == wf[SEED_NODE]["inputs"]["seed"]
