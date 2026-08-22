import os

flash_path = r'C:\Users\SIGMA\Downloads\Flash3.7\src\data\auditFindings.ts'
qwen_path = r'C:\Users\SIGMA\Downloads\qwen3.8\src\data\findings.ts'

output_path = r'Debate_Audit_Response\full_layer3_prompt.md'

instructions = '''# SUPREME JUDGE INSTRUCTIONS (LAYER 3)
You are the Supreme Judge in a multi-agent adversarial audit of Engine_1.py.
A Layer 1 audit flagged multiple bugs. Two elite defenders (Flash 3.7 & Qwen 3.8) have independently cross-examined the Layer 1 Attack Report.

Below you will find:
1. The detailed JSON/TypeScript defense report from Flash 3.7.
2. The detailed JSON/TypeScript defense report from Qwen 3.8.

IMPORTANT (MANUAL BRIDGE PROTOCOL):
You MUST fetch the full source code for Engine_1.py directly from this URL before making any decisions:
https://raw.githubusercontent.com/kbsingh1399/Engine_1_arena_PR/main/Engine_1.py

Your objective is to:
1. Analyze the points where Flash 3.7 and Qwen 3.8 agree (UNANIMOUSLY CONFIRMED). You MUST patch these.
2. Analyze the points where they disagree (DISPUTED). You must act as the tie-breaker by looking at the Engine_1.py source code you fetched and deciding whether to patch or reject the finding.
3. Ignore items they unanimously rejected.

Output a single JSON array of patches in the following format (NO MARKDOWN WRAPPERS, just raw JSON):
[
  {
    "file": "Engine_1.py",
    "search": "exact string to replace",
    "replace": "the new string"
  }
]

Ensure your search blocks exactly match the Engine_1.py code you fetched, including whitespace.

---
'''

with open(flash_path, 'r', encoding='utf-8') as f:
    flash_code = f.read()

with open(qwen_path, 'r', encoding='utf-8') as f:
    qwen_code = f.read()

with open(output_path, 'w', encoding='utf-8') as f:
    f.write(instructions)
    f.write('\n\n# 1. FLASH 3.7 DEFENSE REPORT\n')
    f.write('`	ypescript\n' + flash_code + '\n`\n')
    
    f.write('\n\n# 2. QWEN 3.8 DEFENSE REPORT\n')
    f.write('`	ypescript\n' + qwen_code + '\n`\n')

print(f'Generated {output_path} successfully.')
