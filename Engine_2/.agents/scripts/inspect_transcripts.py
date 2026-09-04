import json

with open(r'c:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\.agents\memory\architecture\raw_transcripts.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

categories = {
    "LIQUIDATION & HEATMAPS": ["qFwvTRATC-c", "2hZVGM4tnc0", "nBwzqWUbRDA", "AjiOviqjMG4", "pWzrnKwDptw", "OA43peERruM", "FsJYCE0ju-A"],
    "VWAP & ANCHORED VWAP": ["R5L890juvRw", "VumVuGnCcFM", "D2P-0xh6aEM", "1HFoStW_wsc", "qJ5bt_pgmCY"],
    "OPEN INTEREST & CVD DYNAMICS": ["7jxuUKJRSQ0", "hsjQxRDDsIA"],
    "WALK-FORWARD & ROBUSTNESS": ["bfwhXTnQgMI", "9m987swadQU", "shBaQzNsLRA"]
}

for cat in ["LIQUIDATION & HEATMAPS"]:
    vids = categories[cat]
    print(f"\n==================== {cat} ====================")
    for v in vids:
        if v in d:
            title = d[v]["title"]
            text = d[v]["text"]
            print(f"\n--- [{v}] {title} (Length: {len(text)}) ---")
            print("BEGINNING:")
            print(text[:450] + "...")
            mid = len(text) // 2
            print("CORE DETAIL:")
            print(text[mid:mid+450] + "...")

