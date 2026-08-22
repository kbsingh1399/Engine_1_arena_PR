import os

with open('scratch/condensed_layer2.md', 'r', encoding='utf-8') as f:
    debate = f.read()

prompt = f"""# Layer 3: The Supreme Judge (Final Synthesis)

You are the Supreme Judge (Layer 3) of this adversarial code audit. 
In Layer 1, attack models flagged vulnerabilities in `Engine_1.py` and related files.
In Layer 2, two elite defenders (Qwen 3.8 and Flash 3.7) independently reviewed the codebase and the attacks, confirming or rejecting them, and proposing patches for the confirmed ones.

Below is the condensed synthesis of their debate. 

**Your Objective:**
1. Review the agreements and disagreements for each finding.
2. Formulate the ultimate correct patch for each CONFIRMED finding, combining the best logic from both defenders.
3. Output the final remediation as a raw JSON array of patches.

---

## Synthesized Debate

{debate}

---

**Output Requirement:**
Output ONLY a JSON array containing the final, unified patches. Do not include markdown formatting or explanations outside the JSON array.
Format:
[
  {{
    "file": "filename.py",
    "diffCode": "exact unified diff patch"
  }}
]
"""

with open('layer_3_synthesis_prompt.md', 'w', encoding='utf-8') as f:
    f.write(prompt)
print('Updated layer_3_synthesis_prompt.md')
