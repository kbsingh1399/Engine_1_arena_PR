import os, sys
import pandas as pd
import numpy as np

sys.path.append(os.path.join(os.getcwd(), "Engine_2"))
from run_optimal_regime_matrix import evaluate_champion_regime_matrix

# Let's inspect the exact candidates tested in W01, W03, W04, W10, W14, W17
print("Ready to run deep inspection on missed window trade trajectories.")
