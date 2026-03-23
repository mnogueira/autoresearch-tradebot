"""
ml_strategy.py — LightGBM-based strategy for WDO day trading.
Train on train period, predict on test period. Honest execution (1-bar delay).

Features derived from indicators we know work:
- EMA crossover state and distance
- RSI value and momentum
- ADX trend strength
- ATR volatility
- Price relative to trend
- Bar-of-day / time features
"""
import numpy as np
import pandas as pd
import ta
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT


def build_features(df):
    """Build feature matrix from OHLCV data. All features are look-back only."""
    f = pd.DataFrame(index=df.index)

    # Core indicators (same as our best strategy)
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema200 = ta.trend.ema_indicator(df["Close"], window=200)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    rsi14 = ta.momentum.rsi(df["Close"], window=14)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)

    # EMA crossover features
    f["ema_diff"] = (ema8 - ema34) / df["Close"] * 100  # normalized EMA gap
    f["ema_diff_prev"] = f["ema_diff"].shift(1)
    f["ema_cross"] = ((ema8 > ema34).astype(int) - (ema8.shift(1) > ema34.shift(1)).astype(int))
    f["ema_above"] = (ema8 > ema34).astype(int)

    # Trend
    f["close_vs_ema200"] = (df["Close"] - ema200) / df["Close"] * 100
    f["ema200_slope"] = (ema200 - ema200.shift(5)) / ema200.shift(5) * 100

    # Momentum
    f["rsi7"] = rsi7
    f["rsi14"] = rsi14
    f["rsi7_delta"] = rsi7 - rsi7.shift(1)
    f["rsi7_above_65"] = (rsi7 > 65).astype(int)
    f["rsi7_below_45"] = (rsi7 < 45).astype(int)

    # Trend strength
    f["adx14"] = adx14
    f["adx_rising"] = (adx14 > adx14.shift(3)).astype(int)

    # Volatility
    f["atr20"] = atr20
    f["atr_ratio"] = atr20 / df["Close"] * 100  # normalized ATR
    f["atr_expanding"] = (atr20 > atr20.shift(5)).astype(int)

    # Price action
    f["bar_range"] = (df["High"] - df["Low"]) / df["Close"] * 100
    f["close_position"] = (df["Close"] - df["Low"]) / (df["High"] - df["Low"]).replace(0, np.nan)
    f["green_bar"] = (df["Close"] > df["Open"]).astype(int)

    # Returns
    f["ret_1"] = df["Close"].pct_change(1) * 100
    f["ret_5"] = df["Close"].pct_change(5) * 100
    f["ret_10"] = df["Close"].pct_change(10) * 100

    # Volume
    vol_sma = df["Volume"].rolling(20).mean()
    f["vol_ratio"] = df["Volume"] / vol_sma

    # Time features
    f["bar_of_day"] = df["bar_of_day"]
    f["hour"] = df["time"].apply(lambda t: t.hour if hasattr(t, 'hour') else 0)
    f["bars_remaining"] = df["bars_remaining"]

    # MACD
    macd = ta.trend.macd_diff(df["Close"])
    f["macd"] = macd
    f["macd_signal"] = ta.trend.macd_signal(df["Close"])

    # Bollinger width
    bb_h = ta.volatility.bollinger_hband(df["Close"], window=20, window_dev=2)
    bb_l = ta.volatility.bollinger_lband(df["Close"], window=20, window_dev=2)
    f["bb_width"] = (bb_h - bb_l) / df["Close"] * 100
    f["bb_position"] = (df["Close"] - bb_l) / (bb_h - bb_l).replace(0, np.nan)

    return f


def build_labels(df, lookahead=1):
    """
    Labels: direction of next-bar return (after 1-bar delay).
    Since we have 1-bar delay in execution, signal at bar i executes at bar i+1.
    So the relevant return is from bar i+1 open to bar i+2 open (or close).
    We simplify: label = sign of Close[i+1] - Open[i+1] (next bar's direction).

    But CRITICAL: we must shift within each day (no cross-day labels).
    """
    # Next bar's return (from Open to Close)
    next_ret = (df["Close"].shift(-1) - df["Open"].shift(-1))

    # Zero out cross-day labels
    same_day = df["date"] == df["date"].shift(-1)
    next_ret = next_ret.where(same_day, 0)

    # Labels: +1 if positive, -1 if negative, 0 if negligible
    labels = np.sign(next_ret)
    return labels


def run_ml_strategy(train_df, test_df, params=None):
    """Train LightGBM on train, predict on test, generate signals."""
    # Build features and labels
    train_feat = build_features(train_df)
    test_feat = build_features(test_df)
    train_labels = build_labels(train_df)

    # Drop NaN rows
    valid_train = train_feat.dropna().index.intersection(train_labels.dropna().index)
    # Also filter: not first bar, not last 30min, not 13h, ADX > 20
    mask = (
        ~train_df.loc[valid_train, "is_first_bar"] &
        ~train_df.loc[valid_train, "is_last_30min"] &
        (train_df.loc[valid_train, "bars_remaining"] > 36)
    )
    valid_train = valid_train[mask]

    X_train = train_feat.loc[valid_train]
    y_train = train_labels.loc[valid_train]

    # Remove 0 labels (flat periods)
    nonzero = y_train != 0
    X_train = X_train[nonzero]
    y_train = y_train[nonzero]

    # Convert to binary: 1 = long, 0 = short
    y_train_binary = (y_train > 0).astype(int)

    if params is None:
        params = {
            'objective': 'binary',
            'metric': 'binary_logloss',
            'num_leaves': 15,
            'max_depth': 4,
            'learning_rate': 0.05,
            'n_estimators': 200,
            'min_child_samples': 50,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'reg_alpha': 1.0,
            'reg_lambda': 1.0,
            'verbose': -1,
        }

    model = lgb.LGBMClassifier(**params)
    model.fit(X_train, y_train_binary)

    # Feature importance
    importances = pd.Series(model.feature_importances_, index=X_train.columns)
    print("\nTop 10 features:")
    for feat, imp in importances.sort_values(ascending=False).head(10).items():
        print(f"  {feat}: {imp}")

    # Predict on test
    valid_test = test_feat.dropna().index
    X_test = test_feat.loc[valid_test]
    probs = model.predict_proba(X_test)[:, 1]  # P(long)

    # Convert to signals with threshold
    signals = pd.Series(0, index=test_df.index)
    for threshold in [0.55, 0.60, 0.65, 0.70]:
        sigs = pd.Series(0, index=test_df.index)
        for idx, p in zip(valid_test, probs):
            if p > threshold:
                sigs.loc[idx] = 1
            elif p < (1 - threshold):
                sigs.loc[idx] = -1

        # Apply filters
        sigs.loc[test_df["is_first_bar"]] = 0
        sigs.loc[test_df["is_last_30min"]] = 0

        # Add 1-bar delay
        sigs = sigs.groupby(test_df["date"]).shift(1).fillna(0).astype(int)

        # Quick backtest
        result = quick_bt(test_df, sigs)
        print(f"  Threshold {threshold}: sharpe={result[0]:>7.4f}, trades={result[3]}, net={result[4]:>8.0f}")

    return model


def quick_bt(df, signals):
    """Quick backtest."""
    signals = signals.reindex(df.index).fillna(0).astype(int).clip(-1, 1)
    day_last = df.groupby("date").tail(1).index
    signals.loc[day_last] = 0

    position = 0; trades = []; entry_price = 0.0
    for i in range(len(df)):
        signal = signals.iloc[i]
        fill_price = df["Open"].iloc[i]
        if i > 0 and df["date"].iloc[i] != df["date"].iloc[i-1] and position != 0:
            pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
            trades.append(pnl); position = 0
        if signal != position:
            if position != 0:
                pnl = (fill_price - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
                trades.append(pnl)
            if signal != 0: entry_price = fill_price
            position = signal
    if position != 0:
        pnl = (df["Open"].iloc[-1] - entry_price) * position * POINT_VALUE - TOTAL_COST_RT
        trades.append(pnl)

    if len(trades) < 10:
        return 0, 0, 0, len(trades), 0

    arr = np.array(trades); n = len(arr)
    wins = arr[arr > 0]; losses = arr[arr < 0]
    net = arr.sum()
    gp = wins.sum() if len(wins) > 0 else 0
    gl = abs(losses.sum()) if len(losses) > 0 else 1e-9
    pf = gp / gl
    trading_days = df.index.normalize().nunique()
    if n > 1 and arr.std(ddof=1) > 0:
        tpd = n / max(trading_days, 1)
        sharpe = (arr.mean() / arr.std(ddof=1)) * np.sqrt(tpd * 252)
    else:
        sharpe = 0
    return round(sharpe, 4), round(pf, 4), round(n, 0), n, round(net, 2)


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    print("=" * 60)
    print("ML STRATEGY — LightGBM")
    print("=" * 60)

    # Test with different model complexities
    configs = [
        ("Conservative (depth=3, leaves=8)", dict(max_depth=3, num_leaves=8, n_estimators=100, min_child_samples=100)),
        ("Medium (depth=4, leaves=15)", dict(max_depth=4, num_leaves=15, n_estimators=200, min_child_samples=50)),
        ("Complex (depth=6, leaves=31)", dict(max_depth=6, num_leaves=31, n_estimators=300, min_child_samples=30)),
    ]

    for name, override in configs:
        print(f"\n{'='*60}")
        print(f"Config: {name}")
        print(f"{'='*60}")
        params = {
            'objective': 'binary', 'metric': 'binary_logloss',
            'learning_rate': 0.05, 'subsample': 0.8, 'colsample_bytree': 0.8,
            'reg_alpha': 1.0, 'reg_lambda': 1.0, 'verbose': -1,
        }
        params.update(override)
        run_ml_strategy(train_df, test_df, params)


if __name__ == "__main__":
    main()
