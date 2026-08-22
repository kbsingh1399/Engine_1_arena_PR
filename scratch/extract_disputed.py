import re

def get_disputed(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    results = {}
    id_pattern = re.compile(r'id:\s*[\'\"]([A-D]-\d)[\'\"]')
    blocks = id_pattern.split(content)
    
    target_ids = ['A-1', 'B-3', 'D-2', 'D-3', 'D-5']
    
    for i in range(1, len(blocks), 2):
        fid = blocks[i]
        if fid in target_ids:
            block = blocks[i+1]
            just_match = re.search(r'justification:\s*[\'\"](.*?)[\'\"]', block, re.DOTALL)
            verdict_match = re.search(r'verdict:\s*[\'\"](.*?)[\'\"]', block)
            if just_match and verdict_match:
                results[fid] = {
                    'verdict': verdict_match.group(1),
                    'justification': just_match.group(1).replace('\n', ' ').strip()
                }
    return results

q_res = get_disputed(r'C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\scratch\layer_2_outputs\qwen3.8\src\data\findings.ts')
f_res = get_disputed(r'C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\scratch\layer_2_outputs\Flash3.7\src\data\auditFindings.ts')

print("=== DISPUTED FINDINGS ===")
for fid in ['A-1', 'B-3', 'D-2', 'D-3', 'D-5']:
    print(f"\n{fid}:")
    print(f"QWEN 3.8 ({q_res.get(fid, {}).get('verdict', 'N/A')}): {q_res.get(fid, {}).get('justification', 'N/A')[:200]}...")
    print(f"FLASH 3.7 ({f_res.get(fid, {}).get('verdict', 'N/A')}): {f_res.get(fid, {}).get('justification', 'N/A')[:200]}...")
