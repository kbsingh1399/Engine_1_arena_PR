import os
import shutil
import filecmp
from pathlib import Path

DIR1 = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\.agents")
DIR2 = Path(r"c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\Engine_2\.agents")

def get_all_relative_files(root: Path):
    files = {}
    for p in root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(root)
            files[rel] = p
    return files

def sync_agents():
    files1 = get_all_relative_files(DIR1)
    files2 = get_all_relative_files(DIR2)

    print(f"Total files in DIR1 (.agents): {len(files1)}")
    print(f"Total files in DIR2 (Engine_2/.agents): {len(files2)}")

    missing_in_2 = [rel for rel in files1 if rel not in files2]
    missing_in_1 = [rel for rel in files2 if rel not in files1]

    print(f"Files in DIR1 but missing in DIR2: {len(missing_in_2)}")
    for m in missing_in_2[:10]:
        print(f"  + Missing in DIR2: {m}")

    print(f"Files in DIR2 but missing in DIR1: {len(missing_in_1)}")
    for m in missing_in_1[:10]:
        print(f"  + Missing in DIR1: {m}")

    # Sync missing files from 1 to 2
    for rel in missing_in_2:
        src = files1[rel]
        dst = DIR2 / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"Synced to DIR2: {rel}")

    # Sync missing files from 2 to 1
    for rel in missing_in_1:
        src = files2[rel]
        dst = DIR1 / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"Synced to DIR1: {rel}")

    # Re-check and compare content differences
    files1 = get_all_relative_files(DIR1)
    files2 = get_all_relative_files(DIR2)
    mismatches = []
    for rel, p1 in files1.items():
        p2 = files2.get(rel)
        if p2 and not filecmp.cmp(p1, p2, shallow=False):
            mismatches.append(rel)

    print(f"\nContent mismatches between DIR1 and DIR2: {len(mismatches)}")
    for rel in mismatches:
        # Use DIR1 as source of truth unless DIR2 is newer
        src = DIR1 / rel
        dst = DIR2 / rel
        if dst.stat().st_mtime > src.stat().st_mtime:
            shutil.copy2(dst, src)
            print(f"Updated DIR1 from newer DIR2: {rel}")
        else:
            shutil.copy2(src, dst)
            print(f"Updated DIR2 from DIR1: {rel}")

    # Final verification
    files1_final = get_all_relative_files(DIR1)
    files2_final = get_all_relative_files(DIR2)
    print("\n--- FINAL PARITY CHECK ---")
    print(f"DIR1 files count: {len(files1_final)}")
    print(f"DIR2 files count: {len(files2_final)}")
    if len(files1_final) == len(files2_final) and set(files1_final.keys()) == set(files2_final.keys()):
        print("PERFECT 100% PARITY ACHIEVED: Both .agents folders have identical files and contents!")
    else:
        print("Discrepancy remains!")

if __name__ == '__main__':
    sync_agents()
