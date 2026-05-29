import json

wf = json.load(open('workflows/generate_anima.json', encoding='utf-8'))

print("=== Node 146 consumers ===")
for nid, node in wf.items():
    if not isinstance(node, dict):
        continue
    for k, v in node.get('inputs', {}).items():
        if isinstance(v, list) and len(v) == 2 and str(v[0]) == '146':
            title = node.get('_meta', {}).get('title', '')
            print(f"  Node {nid} ({title}) uses 146 via input '{k}'")

print()
print("=== Node 25 full structure ===")
print(json.dumps(wf['25'], indent=2, ensure_ascii=False))
