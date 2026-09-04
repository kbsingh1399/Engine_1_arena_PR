import json
import shutil
from pathlib import Path

def structure_memory(base_dir: Path):
    if not base_dir.exists():
        print(f"Directory {base_dir} does not exist.")
        return

    # Create subdirectories
    subdirs = {
        "invariants": base_dir / "invariants",
        "architecture": base_dir / "architecture",
        "protocols": base_dir / "protocols",
        "graph": base_dir / "graph"
    }
    for sd in subdirs.values():
        sd.mkdir(parents=True, exist_ok=True)

    # File mappings (copy to subdirs for clean categorized access)
    mappings = {
        "invariants": [
            "coinglass_login_and_layout_invariant.md",
            "quant_best_practices.md",
            "project-conventions.md"
        ],
        "architecture": [
            "claude_code_leaked_official_architecture.md",
            "claude_code_directives.md",
            "deepseek_harness_architecture.md",
            "system_prompts_leaks_summary.md",
            "deepseek_v3_reasoning_core.md"
        ],
        "protocols": [
            "autonomous_loop_protocol.md",
            "orchestration_preference.md",
            "browser_preview_preference.md",
            "security_threat_model_prompt.md",
            "skills_stack.md"
        ]
    }

    for cat, files in mappings.items():
        dest_dir = subdirs[cat]
        for f in files:
            src_file = base_dir / f
            if src_file.exists():
                shutil.copy2(src_file, dest_dir / f)

    # Save snapshot of MCP graph memory into graph/
    # Read the memory graph from the MCP step output if available
    graph_snapshot_src = Path(r"C:\Users\SIGMA\.gemini\antigravity-ide\brain\0cde74c0-35f6-4fbf-98c5-70553681380f\.system_generated\steps\10885\output.txt")
    if graph_snapshot_src.exists():
        with open(graph_snapshot_src, 'r', encoding='utf-8') as f:
            data = json.load(f)
        with open(subdirs["graph"] / "mcp_graph_memory.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"Saved mcp_graph_memory.json in {subdirs['graph']}")

    print(f"Memory directory {base_dir} structured successfully.")

if __name__ == '__main__':
    structure_memory(Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\.agents\memory"))
    structure_memory(Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\.agents\memory"))
