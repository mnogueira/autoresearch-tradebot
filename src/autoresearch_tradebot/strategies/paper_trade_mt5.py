from __future__ import annotations

import argparse
import json
import time as time_module
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from ..common.paths import artifact_output_dir
from .ema_wdo import (
    EmaStrategyParams,
    IndicatorCache,
    add_session_columns,
    current_strategy_baseline_params,
    generate_raw_positions,
    parse_clock_time,
)

try:
    import MetaTrader5 as mt5
except ImportError:  # pragma: no cover
    mt5 = None


@dataclass
class EngineConfig:
    mode: str
    contracts: int
    poll_seconds: int
    max_daily_loss_brl: float
    output_dir: Path
    symbol: str | None
    params_summary: Path | None
    once: bool
    deviation: int
    kill_switch_path: Path


def ensure_mt5():
    if mt5 is None:
        raise RuntimeError("MetaTrader5 package is not installed.")
    if not mt5.initialize():
        raise RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}")
    account = mt5.account_info()
    if account is None:
        raise RuntimeError("Could not read MT5 account info.")
    return account


def log_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, default=str) + "\n")


def load_params(summary_path: Path | None) -> EmaStrategyParams:
    if summary_path is None or not summary_path.exists():
        return current_strategy_baseline_params()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    best_params = payload.get("optimized_holdout", {}).get("best_params")
    if not best_params:
        return current_strategy_baseline_params()
    return EmaStrategyParams(**best_params)


def front_contract_from_mt5(prefix: str = "WDO") -> str:
    symbols = mt5.symbols_get(f"*{prefix}*") or []
    now = datetime.now()
    candidates: list[tuple[int, str]] = []
    for symbol in symbols:
        if not symbol.name.startswith(prefix):
            continue
        if getattr(symbol, "trade_mode", 0) != mt5.SYMBOL_TRADE_MODE_FULL:
            continue
        expiration = getattr(symbol, "expiration_time", 0)
        if expiration and datetime.fromtimestamp(expiration) <= now:
            continue
        mt5.symbol_select(symbol.name, True)
        rates = mt5.copy_rates_range(symbol.name, mt5.TIMEFRAME_M1, now - timedelta(days=5), now)
        recent_volume = 0 if rates is None else int(sum(rate["tick_volume"] for rate in rates))
        candidates.append((recent_volume, symbol.name))
    if not candidates:
        raise RuntimeError("No tradable WDO contract found in MT5.")
    candidates.sort(reverse=True)
    return candidates[0][1]


def current_net_position(symbol: str) -> int:
    positions = mt5.positions_get(symbol=symbol) or []
    net = 0
    for position in positions:
        if position.type == mt5.POSITION_TYPE_BUY:
            net += int(position.volume)
        elif position.type == mt5.POSITION_TYPE_SELL:
            net -= int(position.volume)
    return net


def fetch_recent_bars(symbol: str, count: int = 1600) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No M5 bars returned for {symbol}.")
    frame = pd.DataFrame(rates)
    frame["time"] = pd.to_datetime(frame["time"], unit="s")
    frame = frame.set_index("time")
    frame = frame.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "tick_volume": "Volume",
        }
    )
    frame = frame[["Open", "High", "Low", "Close", "Volume"]].copy()
    return add_session_columns(frame)


def last_completed_bar_open(now: datetime) -> pd.Timestamp:
    current_open_minute = now.minute - (now.minute % 5)
    current_bar_open = now.replace(minute=current_open_minute, second=0, microsecond=0)
    return pd.Timestamp(current_bar_open - timedelta(minutes=5))


def desired_position_now(frame: pd.DataFrame, params: EmaStrategyParams, now: datetime) -> int:
    completed_cutoff = last_completed_bar_open(now)
    completed = frame[frame.index <= completed_cutoff].copy()
    if completed.empty:
        return 0
    raw = generate_raw_positions(completed, params=params, cache=IndicatorCache(completed))
    desired = int(raw.iloc[-1])
    if now.time() >= parse_clock_time(params.flat_after_bar_time):
        return 0
    return desired


def determine_order_delta(current_position: int, desired_position: int, contracts: int) -> int:
    target = desired_position * contracts
    return target - current_position


def order_request(symbol: str, delta: int, deviation: int) -> dict[str, Any]:
    side = mt5.ORDER_TYPE_BUY if delta > 0 else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if delta > 0 else tick.bid
    if not price:
        price = tick.last
    return {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(abs(delta)),
        "type": side,
        "price": price,
        "deviation": deviation,
        "magic": 20260322,
        "comment": "ema-paper",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }


def today_pnl_brl(symbol: str) -> float:
    now = datetime.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deals = mt5.history_deals_get(start, now, group=symbol) or []
    realized = 0.0
    for deal in deals:
        realized += float(getattr(deal, "profit", 0.0))
        realized += float(getattr(deal, "commission", 0.0))
        realized += float(getattr(deal, "fee", 0.0))
        realized += float(getattr(deal, "swap", 0.0))
    open_positions = mt5.positions_get(symbol=symbol) or []
    unrealized = sum(float(getattr(position, "profit", 0.0)) for position in open_positions)
    return realized + unrealized


def run_cycle(config: EngineConfig, params: EmaStrategyParams, event_log: Path) -> dict[str, Any]:
    now = datetime.now()
    symbol = config.symbol or front_contract_from_mt5()
    mt5.symbol_select(symbol, True)
    frame = fetch_recent_bars(symbol)
    desired = desired_position_now(frame, params, now)
    broker_position = current_net_position(symbol)
    delta = determine_order_delta(broker_position, desired, config.contracts)
    day_pnl = today_pnl_brl(symbol)
    kill_switch = config.kill_switch_path.exists()
    if kill_switch or day_pnl <= -abs(config.max_daily_loss_brl):
        desired = 0
        delta = determine_order_delta(broker_position, desired, config.contracts)

    event = {
        "timestamp": now.isoformat(),
        "mode": config.mode,
        "symbol": symbol,
        "desired_position": desired,
        "broker_position": broker_position,
        "delta": delta,
        "day_pnl_brl": round(day_pnl, 2),
        "kill_switch": kill_switch,
        "params": asdict(params),
    }

    if delta == 0:
        event["action"] = "hold"
        log_event(event_log, event)
        return event

    request = order_request(symbol, delta, config.deviation)
    event["request"] = request
    if config.mode == "shadow":
        event["action"] = "shadow_signal"
        log_event(event_log, event)
        return event

    result = mt5.order_send(request)
    event["action"] = "order_send"
    event["result"] = None if result is None else result._asdict()
    log_event(event_log, event)
    return event


def main() -> None:
    parser = argparse.ArgumentParser(description="MT5 paper trader for the EMA WDO strategy.")
    parser.add_argument("--mode", choices=["shadow", "demo"], default="shadow")
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--max-daily-loss-brl", type=float, default=1000.0)
    parser.add_argument("--output-dir", type=Path, default=artifact_output_dir("paper_ema_mt5"))
    parser.add_argument("--symbol", default=None, help="Optional explicit tradable symbol, e.g. WDOJ26.")
    parser.add_argument(
        "--params-summary",
        type=Path,
        default=artifact_output_dir("ema_wdo_full", "summary.json"),
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--deviation", type=int, default=20)
    parser.add_argument(
        "--kill-switch-path",
        type=Path,
        default=artifact_output_dir("paper_ema_mt5", "KILL_SWITCH"),
    )
    args = parser.parse_args()

    account = ensure_mt5()
    params = load_params(args.params_summary)
    config = EngineConfig(
        mode=args.mode,
        contracts=args.contracts,
        poll_seconds=args.poll_seconds,
        max_daily_loss_brl=args.max_daily_loss_brl,
        output_dir=args.output_dir,
        symbol=args.symbol,
        params_summary=args.params_summary,
        once=args.once,
        deviation=args.deviation,
        kill_switch_path=args.kill_switch_path,
    )
    config.output_dir.mkdir(parents=True, exist_ok=True)
    event_log = config.output_dir / "events.jsonl"
    print(f"Connected: {account.server} account={account.login} mode={config.mode}")
    try:
        while True:
            event = run_cycle(config, params, event_log)
            print(json.dumps(event, default=str))
            if config.once:
                break
            time_module.sleep(max(1, config.poll_seconds))
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
