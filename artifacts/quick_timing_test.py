import json
from pathlib import Path

import pandas as pd


root = Path(__file__).resolve().parents[1]
data_path = root / "data" / "wdo_m1_mt5_2021_2026.parquet"
output_path = root / "artifacts" / "timing_analysis.json"

df = pd.read_parquet(data_path)
if not isinstance(df.index, pd.DatetimeIndex):
    df.index = pd.to_datetime(df["time"])

df["hour"] = df.index.hour
df["dow"] = df.index.dayofweek
df["bar_range"] = df["High"] - df["Low"]
df["bar_return"] = df["Close"] - df["Open"]

by_day = (
    df.groupby("dow")
    .agg(
        bars=("Open", "size"),
        total_volume=("Volume", "sum"),
        avg_volume=("Volume", "mean"),
        avg_range=("bar_range", "mean"),
        avg_return=("bar_return", "mean"),
    )
    .reset_index()
)

by_hour = (
    df.groupby("hour")
    .agg(
        bars=("Open", "size"),
        total_volume=("Volume", "sum"),
        avg_volume=("Volume", "mean"),
        avg_range=("bar_range", "mean"),
        avg_return=("bar_return", "mean"),
    )
    .reset_index()
)

payload = {
    "data_path": str(data_path),
    "rows": int(len(df)),
    "start": str(df.index.min()),
    "end": str(df.index.max()),
    "by_day_of_week": by_day.to_dict(orient="records"),
    "by_hour": by_hour.to_dict(orient="records"),
}

output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps(payload, indent=2))
