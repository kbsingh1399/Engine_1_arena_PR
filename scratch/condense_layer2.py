import re
import json

qwen_path = r'C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\scratch\layer_2_outputs\qwen3.8\src\data\findings.ts'
flash_path = r'C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\scratch\layer_2_outputs\Flash3.7\src\data\auditFindings.ts'

def extract_findings(text):
    findings = []
    blocks = re.split(r'id:\s*[\'\"]', text)[1:]
    for b in blocks:
        id_match = re.search(r'^([A-D]-\d)[\'\"]', b)
        if not id_match: continue
        fid = id_match.group(1)
        
        v_match = re.search(r'verdict:\s*[\'\"](CONFIRMED|REJECTED)[\'\"]', b)
        verdict = v_match.group(1) if v_match else 'UNKNOWN'
        
        j_match = re.search(r'justification:\s*[\'\"](.*?)[\'\"]', b, re.DOTALL)
        justification = j_match.group(1).replace('\n', ' ') if j_match else ''
        
        patch_match = re.search(r'diffCode:\s*`([^`]+)`', b)
        patch = patch_match.group(1) if patch_match else ''
        
        if not patch:
            patch_lines = re.findall(r'\{\s*t:\s*[\'\"](.*?)[\'\"],\s*c:\s*[\'\"](.*?)[\'\"]', b)
            if patch_lines:
                patch = '\n'.join([f'{t}{c}' for t, c in patch_lines])
                
        findings.append({
            'id': fid,
            'verdict': verdict,
            'justification': justification,
            'patch': patch
        })
    return {f['id']: f for f in findings}

q_text = open(qwen_path, 'r', encoding='utf-8').read()
f_text = open(flash_path, 'r', encoding='utf-8').read()

q_findings = extract_findings(q_text)
f_findings = extract_findings(f_text)

all_ids = sorted(list(set(list(q_findings.keys()) + list(f_findings.keys()))))

out = []
for fid in all_ids:
    out.append(f'### Finding {fid}')
    if fid in f_findings:
        out.append(f'**Flash 3.7 Verdict:** {f_findings[fid]["verdict"]}')
        out.append(f'**Flash 3.7 Justification:** {f_findings[fid]["justification"]}')
    if fid in q_findings:
        out.append(f'**Qwen 3.8 Verdict:** {q_findings[fid]["verdict"]}')
        out.append(f'**Qwen 3.8 Justification:** {q_findings[fid]["justification"]}')
    
    if (fid in f_findings and f_findings[fid]['verdict'] == 'CONFIRMED' and f_findings[fid]['patch']):
        out.append(f'**Proposed Patch (Flash):**\n```diff\n{f_findings[fid]["patch"]}\n```')
    elif (fid in q_findings and q_findings[fid]['verdict'] == 'CONFIRMED' and q_findings[fid]['patch']):
        out.append(f'**Proposed Patch (Qwen):**\n```diff\n{q_findings[fid]["patch"]}\n```')
        
    out.append('')

summary = '\n'.join(out)
with open('scratch/condensed_layer2.md', 'w', encoding='utf-8') as f:
    f.write(summary)
print('Wrote condensed layer 2 to scratch/condensed_layer2.md')
