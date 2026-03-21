"""
prepare.py — Data preparation for WDO autoresearch.
READ-ONLY: The AI agent must NOT modify this file.

Downloads WDO$N (continuous mini dollar) historical data from MetaTrader 5,
caches to parquet, and provides loading utilities.
"""

import sys
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

# ── WDO Contract Specifications ──────────────────────────────────────────────
SYMBOL = "WDO$N"                # MT5 continuous series
TICK_SIZE = 0.5                 # minimum price increment (points)
POINT_VALUE = 10.0              # BRL per point
TICK_VALUE = TICK_SIZE * POINT_VALUE  # = BRL 5.00 per tick
COST_PER_CONTRACT_RT = 1.00     # XP day-trade roundtrip commission (BRL)
SLIPPAGE_TICKS = 1              # assumed slippage per side (conservative)
SLIPPAGE_COST_RT = 2 * SLIPPAGE_TICKS * TICK_VALUE  # = BRL 10.00
TOTAL_COST_RT = COST_PER_CONTRACT_RT + SLIPPAGE_COST_RT  # = BRL 11.00

# ── Trading Session ──────────────────────────────────────────────────────────
SESSION_START = dt.time(9, 0)   # B3 mini dollar open
SESSION_END = dt.time(17, 55)   # day-trade close (5 min before official close)

# ── Data Configuration ───────────────────────────────────────────────────────
DATA_DIR = Path("data")
TIMEFRAMES = {
    "M1": 1,    # TIMEFRAME_M1
    "M5": 5,    # TIMEFRAME_M5
    "M15": 15,  # TIMEFRAME_M15
    "H1": 16385,  # TIMEFRAME_H1
}
DEFAULT_TIMEFRAME = "M5"
DEFAULT_YEARS_BACK = 3


def connect_mt5() -> None:
    """Initialize connection to MetaTrader 5 terminal."""
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("ERROR: MetaTrader5 package not installed. Run: pip install MetaTrader5")
        sys.exit(1)

    if not mt5.initialize():
        print(f"ERROR: MT5 initialize() failed — error code {mt5.last_error()}")
        print("Make sure MetaTrader 5 is running and logged in.")
        sys.exit(1)

    info = mt5.account_info()
    if info is None:
        print("ERROR: Could not get account info.")
        mt5.shutdown()
        sys.exit(1)

    print(f"Connected to MT5: {info.server} | Account: {info.login} | "
          f"Balance: {info.balance:.2f} {info.currency}")
    return mt5


def download_data(timeframe: str = DEFAULT_TIMEFRAME, years_back: int = DEFAULT_YEARS_BACK) -> pd.DataFrame:
    """
    Download WDO$N historical data from MT5 and save to parquet.

    Returns DataFrame with columns: Open, High, Low, Close, Volume, Spread
    Index: DatetimeIndex (UTC-3 / Brasilia time)
    """
    mt5 = connect_mt5()

    # Ensure symbol is available
    if not mt5.symbol_select(SYMBOL, True):
        print(f"ERROR: Symbol {SYMBOL} not available in MT5. "
              "Make sure it's visible in Market Watch.")
        mt5.shutdown()
        sys.exit(1)

    sym_info = mt5.symbol_info(SYMBOL)
    print(f"Symbol: {sym_info.name} | Point: {sym_info.point} | "
          f"Tick size: {sym_info.trade_tick_size} | Tick value: {sym_info.trade_tick_value}")

    # Determine timeframe constant
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
    }
    mt5_tf = tf_map.get(timeframe)
    if mt5_tf is None:
        print(f"ERROR: Unknown timeframe '{timeframe}'. Use one of: {list(tf_map.keys())}")
        mt5.shutdown()
        sys.exit(1)

    # MT5 API requires timezone-aware UTC datetimes
    import pytz
    utc = pytz.utc
    date_to = dt.datetime.now(tz=utc)
    date_from = date_to - dt.timedelta(days=years_back * 365)

    print(f"Downloading {SYMBOL} {timeframe} from {date_from.date()} to {date_to.date()}...")

    # Download in chunks — MT5 has internal limits on single requests.
    # For 5-min bars: ~108 bars/day × 252 days × 3 years ≈ 82k bars.
    # Request in batches of 50k to stay safe.
    CHUNK_SIZE = 50_000
    all_rates = []
    offset = 0

    while True:
        chunk = mt5.copy_rates_from_pos(SYMBOL, mt5_tf, offset, CHUNK_SIZE)
        if chunk is None or len(chunk) == 0:
            break
        all_rates.append(chunk)
        print(f"  Fetched {len(chunk):,} bars (offset={offset:,})")
        if len(chunk) < CHUNK_SIZE:
            break  # no more data
        offset += CHUNK_SIZE

    mt5.shutdown()

    if not all_rates:
        print("ERROR: No data returned from MT5.")
        sys.exit(1)

    import numpy as np
    rates = np.concatenate(all_rates)

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df.rename(columns={
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "tick_volume": "Volume",
        "spread": "Spread",
    }, inplace=True)
    df.drop(columns=["real_volume"], errors="ignore", inplace=True)
    df.sort_index(inplace=True)

    # Filter to trading hours only
    df = filter_session(df)

    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"wdo_{timeframe.lower()}.parquet"
    df.to_parquet(path)
    print(f"Saved {len(df):,} bars to {path}")
    print(f"Date range: {df.index[0]} -> {df.index[-1]}")
    print(f"Trading days: {df.index.normalize().nunique()}")

    return df


def filter_session(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only bars within the WDO trading session."""
    mask = (df.index.time >= SESSION_START) & (df.index.time <= SESSION_END)
    return df[mask].copy()


def load_data(timeframe: str = DEFAULT_TIMEFRAME) -> pd.DataFrame:
    """Load cached data from parquet. Run prepare.py first to download."""
    path = DATA_DIR / f"wdo_{timeframe.lower()}.parquet"
    if not path.exists():
        print(f"ERROR: Data file not found at {path}")
        print("Run: python prepare.py")
        sys.exit(1)

    df = pd.read_parquet(path)
    print(f"Loaded {len(df):,} bars from {path}")
    print(f"Date range: {df.index[0]} -> {df.index[-1]}")
    return df


def split_data(df: pd.DataFrame, train_ratio: float = 0.70) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split data into train/test by date (not random).
    Walk-forward: train on past, test on future.
    """
    dates = df.index.normalize().unique().sort_values()
    split_idx = int(len(dates) * train_ratio)
    split_date = dates[split_idx]

    train = df[df.index < split_date].copy()
    test = df[df.index >= split_date].copy()

    print(f"Train: {len(train):,} bars ({train.index[0].date()} -> {train.index[-1].date()})")
    print(f"Test:  {len(test):,} bars ({test.index[0].date()} -> {test.index[-1].date()})")
    return train, test


def add_session_markers(df: pd.DataFrame) -> pd.DataFrame:
    """Add columns marking session boundaries (useful for strategies)."""
    df = df.copy()
    df["date"] = df.index.date
    df["time"] = df.index.time
    df["bar_of_day"] = df.groupby("date").cumcount()
    df["is_first_bar"] = df["bar_of_day"] == 0

    # Mark last N bars of session (for forced close logic)
    bars_per_day = df.groupby("date").transform("count")["Close"]
    df["bars_remaining"] = bars_per_day - df["bar_of_day"] - 1
    df["is_last_30min"] = df["bars_remaining"] <= 6  # 6 x 5min = 30min

    return df


def download_all_timeframes(years_back: int = DEFAULT_YEARS_BACK) -> None:
    """Download data for all available timeframes."""
    for tf in TIMEFRAMES:
        print(f"\n{'='*60}")
        print(f"Downloading {tf}...")
        print(f"{'='*60}")
        try:
            download_data(timeframe=tf, years_back=years_back)
        except SystemExit:
            print(f"WARNING: Failed to download {tf}, continuing...")


# ── Main: run to download data ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download WDO data from MT5")
    parser.add_argument("--timeframe", default=DEFAULT_TIMEFRAME,
                        choices=list(TIMEFRAMES.keys()), help="Bar timeframe")
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS_BACK,
                        help="Years of history to download")
    parser.add_argument("--all", action="store_true",
                        help="Download all timeframes (M1, M5, M15, H1)")
    args = parser.parse_args()

    if args.all:
        download_all_timeframes(years_back=args.years)
    else:
        download_data(timeframe=args.timeframe, years_back=args.years)
