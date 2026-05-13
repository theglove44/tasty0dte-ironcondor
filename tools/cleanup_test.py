import pandas as pd

import _bootstrap  # noqa: F401
from project_paths import PAPER_TRADES_CSV

file_path = str(PAPER_TRADES_CSV)

# Read
df = pd.read_csv(file_path)

# Drop last row if it is the test row
if not df.empty and df.iloc[-1]['Symbol'] == 'SPX' and df.iloc[-1]['Short Call'] == 'TEST_SC':
    print("Removing test entry...")
    df = df.iloc[:-1]
    df.to_csv(file_path, index=False)
    print("Removed.")
else:
    print("No test entry found to remove or it doesn't match expected values.")
