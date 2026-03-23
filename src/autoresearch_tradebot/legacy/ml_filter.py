"""
ml_filter.py — ML model as a quality filter on EMA crossover signals.
Instead of predicting every bar, the model only runs when an EMA crossover occurs
and predicts whether THIS specific crossover will be profitable.
"""
import numpy as np
import pandas as pd
import ta
import lightgbm as lgb

from .prepare import load_data, split_data, add_session_markers, POINT_VALUE, TOTAL_COST_RT


def extract_crossover_features(df):
    """Extract features at EMA crossover points only."""
    ema8 = ta.trend.ema_indicator(df["Close"], window=8)
    ema34 = ta.trend.ema_indicator(df["Close"], window=34)
    ema200 = ta.trend.ema_indicator(df["Close"], window=200)
    rsi7 = ta.momentum.rsi(df["Close"], window=7)
    adx14 = ta.trend.adx(df["High"], df["Low"], df["Close"], window=14)
    atr20 = ta.volatility.average_true_range(df["High"], df["Low"], df["Close"], window=20)

    close = df["Close"]
    e8 = ema8; e34 = ema34

    # Detect crossovers
    cross_up = (e8 > e34) & (e8.shift(1) <= e34.shift(1))
    cross_dn = (e8 < e34) & (e8.shift(1) >= e34.shift(1))
    crossovers = cross_up | cross_dn

    # Features at crossover points
    feats = pd.DataFrame(index=df.index)
    feats["direction"] = 0
    feats.loc[cross_up, "direction"] = 1
    feats.loc[cross_dn, "direction"] = -1

    feats["ema_gap"] = abs(e8 - e34) / close * 100
    feats["close_vs_ema200"] = (close - ema200) / close * 100
    feats["ema200_slope5"] = (ema200 - ema200.shift(5)) / ema200.shift(5) * 100
    feats["rsi7"] = rsi7
    feats["rsi7_slope"] = rsi7 - rsi7.shift(3)
    feats["adx14"] = adx14
    feats["adx_slope"] = adx14 - adx14.shift(3)
    feats["atr_ratio"] = atr20 / close * 100
    feats["bar_of_day"] = df["bar_of_day"]
    feats["vol_ratio"] = df["Volume"] / df["Volume"].rolling(20).mean()
    feats["ret_5bar"] = close.pct_change(5) * 100
    feats["ret_10bar"] = close.pct_change(10) * 100
    feats["bar_range"] = (df["High"] - df["Low"]) / close * 100
    feats["close_pos"] = (close - df["Low"]) / (df["High"] - df["Low"]).replace(0, np.nan)
    feats["bars_remaining"] = df["bars_remaining"]

    # Only keep crossover rows
    cross_feats = feats[crossovers].copy()
    return cross_feats, crossovers


def label_crossovers(df, crossovers, horizon=10):
    """
    Label each crossover: was the trade profitable?
    Look ahead `horizon` bars at the max favorable excursion.
    If the next `horizon` bars show profit > R$11 (cost), label as 1.
    """
    labels = pd.Series(np.nan, index=df.index)
    close = df["Close"].values
    dates = df["date"].values

    cross_indices = np.where(crossovers.values)[0]
    for ci in cross_indices:
        if ci + 2 >= len(df):
            continue
        # Direction of crossover
        entry_price = df["Open"].values[ci + 1]  # fill at next bar open (1-bar delay)
        direction = 1 if df.iloc[ci].name in crossovers[crossovers].index and \
                        ta.trend.ema_indicator(df["Close"], window=8).iloc[ci] > \
                        ta.trend.ema_indicator(df["Close"], window=34).iloc[ci] else -1

        # Max favorable excursion in next `horizon` bars (same day only)
        best_pnl = 0
        for j in range(1, horizon + 1):
            if ci + 1 + j >= len(df):
                break
            if dates[ci + 1 + j] != dates[ci + 1]:
                break
            price = close[ci + 1 + j]
            pnl = (price - entry_price) * direction * POINT_VALUE - TOTAL_COST_RT
            best_pnl = max(best_pnl, pnl)

        labels.iloc[ci] = 1 if best_pnl > 0 else 0

    return labels


def main():
    df = load_data()
    train_df, test_df = split_data(df, train_ratio=0.70)
    train_df = add_session_markers(train_df)
    test_df = add_session_markers(test_df)

    print("Extracting crossover features...")
    train_feats, train_cross = extract_crossover_features(train_df)
    test_feats, test_cross = extract_crossover_features(test_df)

    print(f"Train crossovers: {len(train_feats)}")
    print(f"Test crossovers: {len(test_feats)}")

    # Simple labeling: was the trade profitable within 10 bars?
    print("Labeling crossovers (this is slow)...")

    # Simpler approach: instead of complex labeling, just check if
    # the price moved favorably by > 1 point within next 5 bars
    close = train_df["Close"].values
    dates = train_df["date"].values
    opens = train_df["Open"].values

    train_labels = pd.Series(np.nan, index=train_df.index)
    for idx in train_feats.index:
        i = train_df.index.get_loc(idx)
        if i + 6 >= len(train_df):
            continue
        direction = train_feats.loc[idx, "direction"]
        entry = opens[i + 1]  # 1-bar delay

        best_pnl = -999
        for j in range(2, 12):
            if i + j >= len(train_df) or dates[i + j] != dates[i]:
                break
            pnl = (close[i + j] - entry) * direction * POINT_VALUE - TOTAL_COST_RT
            best_pnl = max(best_pnl, pnl)

        train_labels.iloc[i] = 1 if best_pnl > 0 else 0

    # Filter to valid training samples
    valid = train_feats.index.intersection(train_labels.dropna().index)
    feature_cols = [c for c in train_feats.columns if c != "direction"]
    X_train = train_feats.loc[valid, feature_cols]
    y_train = train_labels.loc[valid]

    print(f"Training samples: {len(X_train)}, positive: {y_train.sum():.0f} ({y_train.mean()*100:.1f}%)")

    # Train model
    params = {
        'objective': 'binary', 'metric': 'binary_logloss',
        'num_leaves': 8, 'max_depth': 3, 'learning_rate': 0.05,
        'n_estimators': 100, 'min_child_samples': 20,
        'subsample': 0.8, 'colsample_bytree': 0.8,
        'reg_alpha': 2.0, 'reg_lambda': 2.0, 'verbose': -1,
    }
    model = lgb.LGBMClassifier(**params)
    model.fit(X_train, y_train)

    # Feature importance
    importances = pd.Series(model.feature_importances_, index=feature_cols)
    print("\nTop features:")
    for feat, imp in importances.sort_values(ascending=False).head(8).items():
        print(f"  {feat}: {imp}")

    # Predict on test crossovers
    X_test = test_feats[feature_cols].dropna()
    probs = model.predict_proba(X_test)[:, 1]

    # Generate signals: take crossover only if ML says > threshold
    print(f"\n{'Threshold':<12} {'test_sharpe':>12} {'trades':>8} {'net':>10}")
    print("-" * 45)

    for thresh in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65]:
        signals = pd.Series(0, index=test_df.index)
        for idx, p in zip(X_test.index, probs):
            if p > thresh:
                direction = test_feats.loc[idx, "direction"]
                signals.loc[idx] = direction

        # Apply filters
        signals.loc[test_df["is_first_bar"]] = 0
        signals.loc[test_df["is_last_30min"]] = 0

        # 1-bar delay
        signals = signals.groupby(test_df["date"]).shift(1).fillna(0).astype(int)

        # Quick backtest
        result = quick_bt(test_df, signals)
        print(f"  {thresh:<10} {result[0]:>12.4f} {result[3]:>8} {result[4]:>10.0f}")


def quick_bt(df, signals):
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
    if len(trades) < 5:
        return 0, 0, 0, len(trades), 0
    arr = np.array(trades); n = len(arr)
    net = arr.sum()
    trading_days = df.index.normalize().nunique()
    if n > 1 and arr.std(ddof=1) > 0:
        tpd = n / max(trading_days, 1)
        sharpe = (arr.mean() / arr.std(ddof=1)) * np.sqrt(tpd * 252)
    else:
        sharpe = 0
    return round(sharpe, 4), 0, 0, n, round(net, 2)


if __name__ == "__main__":
    main()
