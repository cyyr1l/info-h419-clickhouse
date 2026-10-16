"""Create test data to check that compare.py works.

Usage:  python test_compare.py   then   python compare.py t_ref t_res
Expected output: OK, OK (different order), MISMATCH values, MISMATCH rows/cols, MISSING
"""
from pathlib import Path

import pandas as pd

ref, res = Path("t_ref"), Path("t_res")
ref.mkdir(exist_ok=True)
res.mkdir(exist_ok=True)
df = pd.DataFrame({"item": ["a", "b", "c"], "total": [10.001, 20.5, None]})

df.to_csv(ref / "q01.csv", index=False); df.to_csv(res / "q01.csv", index=False)                              # OK
df.to_csv(ref / "q02.csv", index=False); df.iloc[::-1].to_csv(res / "q02.csv", index=False)                   # OK (different order)
df.to_csv(ref / "q03.csv", index=False); df.assign(total=[10, 99, None]).to_csv(res / "q03.csv", index=False) # MISMATCH values
df.to_csv(ref / "q04.csv", index=False); df.head(2).to_csv(res / "q04.csv", index=False)                      # MISMATCH rows
df.to_csv(ref / "q05.csv", index=False)                                                                       # MISSING
print("Test data created in t_ref/ and t_res/")
