import json
import numpy as np
import collections

stats = collections.defaultdict(list)

with open('live_data/drift_dryrun_log.jsonl', 'r') as f:
    for line in f:
        data = json.loads(line)
        for k, v in data.get('feature_values', {}).items():
            if v is not None:
                stats[k].append(v)

print("Feature | Count | Min | Max | Mean | Std | 1% | 99%")
print("-" * 70)
for k, vals in stats.items():
    arr = np.array(vals)
    print(f"{k:10} | {len(arr):5d} | {np.min(arr):8.4f} | {np.max(arr):8.4f} | {np.mean(arr):8.4f} | {np.std(arr):8.4f} | {np.percentile(arr, 1):8.4f} | {np.percentile(arr, 99):8.4f}")

