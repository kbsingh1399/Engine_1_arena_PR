import re

def get_verdicts(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    verdicts = {}
    id_pattern = re.compile(r'id:\s*[\'\"]([A-D]-\d)[\'\"]')
    verdict_pattern = re.compile(r'verdict:\s*[\'\"](CONFIRMED|REJECTED)[\'\"]')
    
    blocks = id_pattern.split(content)
    for i in range(1, len(blocks), 2):
        finding_id = blocks[i]
        block_content = blocks[i+1]
        v_match = verdict_pattern.search(block_content)
        if v_match:
            verdicts[finding_id] = v_match.group(1)
            
    return verdicts

q_verdicts = get_verdicts(r'C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\scratch\layer_2_outputs\qwen3.8\src\data\findings.ts')
f_verdicts = get_verdicts(r'C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\scratch\layer_2_outputs\Flash3.7\src\data\auditFindings.ts')

print('Finding | Qwen 3.8 | Flash 3.7')
print('---|---|---')
all_keys = sorted(list(set(list(q_verdicts.keys()) + list(f_verdicts.keys()))))
for k in all_keys:
    q = q_verdicts.get(k, 'MISSING')
    f = f_verdicts.get(k, 'MISSING')
    print(f'{k} | {q} | {f}')
