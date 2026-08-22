import os

os.makedirs('Debate_Audit_Response', exist_ok=True)

with open('Engine_1.py', 'r', encoding='utf-8') as f:
    engine_code = f.read()

l1_prompt = f'''# TASK CONTEXT: LAYER 1 AUDIT (ATTACK)

You are an elite autonomous code auditor. Your task is to review the following algorithmic trading engine source code (Engine_1.py) and identify critical logic, concurrency, and financial execution bugs. 

## INSTRUCTIONS
1. Analyze the codebase for critical vulnerabilities.
2. Provide a detailed explanation for each bug found.
3. Output your response STRICTLY as a Markdown file. 
4. Include any suggested code patches as standard Markdown code blocks (e.g. diff or python blocks). Do NOT output raw JSON arrays.

## ENGINE_1.py SOURCE CODE
`python
{engine_code}
`
'''
with open('Debate_Audit_Response/layer_1_prompt_template.md', 'w', encoding='utf-8') as f:
    f.write(l1_prompt)

l2_prompt = '''# TASK CONTEXT: LAYER 2 AUDIT (DEFENSE)

You are an elite code defender. A Layer 1 audit team has submitted vulnerability reports for Engine_1.py. 

Your task is to review their findings against the source code. For each finding:
1. State whether you CONFIRM or REJECT the bug.
2. Provide your reasoning and root cause analysis.
3. If confirmed, provide the remediated code patch.
4. Output your entire response STRICTLY in Markdown format, including code patches as Markdown code blocks. Do not use JSON.

[ORCHESTRATOR WILL INJECT LAYER 1 REPORTS AND ENGINE CODE HERE BEFORE YOU RUN THIS]
'''
with open('Debate_Audit_Response/layer_2_prompt_template.md', 'w', encoding='utf-8') as f:
    f.write(l2_prompt)

l3_prompt = '''# TASK CONTEXT: LAYER 3 AUDIT (SUPREME JUDGE)

You are the Supreme Judge in a multi-agent adversarial audit.
A Layer 1 team flagged bugs, and a Layer 2 team defended and disputed them. 

Your objective:
1. Resolve any disputes between Layer 1 and Layer 2.
2. Synthesize the unanimously confirmed bugs and your rulings on disputed bugs into a final master list.
3. Output the final, definitive code patches required to fix Engine_1.py.
4. Output everything STRICTLY in Markdown format, using Markdown diff or code blocks for the patches. Do NOT use JSON arrays.

[ORCHESTRATOR WILL INJECT PREVIOUS REPORTS AND ENGINE CODE HERE BEFORE YOU RUN THIS]
'''
with open('Debate_Audit_Response/layer_3_prompt_template.md', 'w', encoding='utf-8') as f:
    f.write(l3_prompt)

print("Generated prompt templates locally.")
