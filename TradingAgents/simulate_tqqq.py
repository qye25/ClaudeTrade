import math
from datetime import datetime, timedelta

import pandas as pd
from stockstats import wrap

from tradingagents.dataflows.stockstats_utils import load_ohlcv


def simulate(symbol: str, curr_date: str, lookback_days: int = 252, max_hold: int = 20, risk_per_trade: float = 100.0):
    df = load_ohlcv(symbol, curr_date)
    if df.empty:
        print("No data")
        return

    df = df.sort_values("Date").reset_index(drop=True)
    # Normalize common column name casing (yfinance/cached CSVs sometimes use lower-case)
    rename_map = {}
    for c in df.columns:
        lc = c.lower()
        if lc in ("open", "high", "low", "close", "volume", "date"):
            rename_map[c] = lc.title()
    if rename_map:
        df = df.rename(columns=rename_map)
    # limit to lookback window
    if len(df) > lookback_days:
        df = df.iloc[-lookback_days:].reset_index(drop=True)

    s = wrap(df.copy())
    # trigger indicators
    s["close_10_ema"]
    s["close_50_sma"]
    s["atr"]

    trades = []

    for i in range(len(s) - 1):
        row = s.iloc[i]
        next_row = s.iloc[i + 1]

        date = pd.to_datetime(row["Date"]).date()

        # Pullback entry: intraday low touches 10EMA
        try:
            ema10 = float(row["close_10_ema"])
            atr = float(row["atr"])
        except Exception:
            continue

        # ensure numeric price columns (stockstats wrap uses lowercase names)
        open_next = float(next_row["open"])
        high_next = float(next_row["high"])
        low_next = float(next_row["low"])
        close_next = float(next_row["close"])

        # Strategy A: Pullback
        if float(row["low"]) <= ema10:
            entry = open_next
            stop = entry - 1.5 * atr
            if stop >= entry:
                # degenerate
                pass
            else:
                risk_per_share = entry - stop
                if risk_per_share <= 0:
                    pass
                else:
                    shares = math.floor(risk_per_trade / risk_per_share)
                    if shares >= 1:
                        t1 = entry * 1.05
                        t2 = entry * 1.10
                        # search forward up to max_hold days
                        exited = False
                        for j in range(i + 1, min(i + 1 + max_hold, len(s))):
                            dj = s.iloc[j]
                            high_j = float(dj["high"])
                            low_j = float(dj["low"])
                            close_j = float(dj["close"])
                            # target hit
                            if high_j >= t1:
                                pnl = (t1 - entry) * shares
                                trades.append({"type": "pullback", "entry_date": date, "entry": entry, "exit_date": pd.to_datetime(dj["Date"]).date(), "exit": t1, "pnl": pnl})
                                exited = True
                                break
                            if low_j <= stop:
                                pnl = (stop - entry) * shares
                                trades.append({"type": "pullback", "entry_date": date, "entry": entry, "exit_date": pd.to_datetime(dj["Date"]).date(), "exit": stop, "pnl": pnl})
                                exited = True
                                break
                        if not exited:
                            # exit at close of last day
                            last = s.iloc[min(i + max_hold, len(s) - 1)]
                            pnl = (float(last["close"]) - entry) * shares
                            trades.append({"type": "pullback", "entry_date": date, "entry": entry, "exit_date": pd.to_datetime(last["Date"]).date(), "exit": float(last["close"]), "pnl": pnl})

        # Strategy B: Breakout confirmed close above 50SMA
        try:
            sma50 = float(row["close_50_sma"])
        except Exception:
            sma50 = None

        # breakout condition: today's close > 50SMA and yesterday's close <= yesterday's 50SMA
        if i >= 1 and sma50 is not None:
            prev = s.iloc[i - 1]
            try:
                prev_close = float(prev["close"]) if "close" in prev else None
                prev_sma = float(prev["close_50_sma"]) if "close_50_sma" in prev else None
            except Exception:
                prev_close = None
                prev_sma = None

            if float(row["close"]) > sma50 and (prev_close is None or prev_close <= (prev_sma or 0)):
                entry = open_next
                stop = entry - 1.5 * atr
                if stop < entry:
                    risk_per_share = entry - stop
                    shares = math.floor(risk_per_trade / risk_per_share) if risk_per_share > 0 else 0
                    if shares >= 1:
                        t1 = entry * 1.05
                        exited = False
                        for j in range(i + 1, min(i + 1 + max_hold, len(s))):
                            dj = s.iloc[j]
                            high_j = float(dj["high"])
                            low_j = float(dj["low"])
                            if high_j >= t1:
                                pnl = (t1 - entry) * shares
                                trades.append({"type": "breakout", "entry_date": date, "entry": entry, "exit_date": pd.to_datetime(dj["Date"]).date(), "exit": t1, "pnl": pnl})
                                exited = True
                                break
                            if low_j <= stop:
                                pnl = (stop - entry) * shares
                                trades.append({"type": "breakout", "entry_date": date, "entry": entry, "exit_date": pd.to_datetime(dj["Date"]).date(), "exit": stop, "pnl": pnl})
                                exited = True
                                break
                        if not exited:
                            last = s.iloc[min(i + max_hold, len(s) - 1)]
                            pnl = (float(last["close"]) - entry) * shares
                            trades.append({"type": "breakout", "entry_date": date, "entry": entry, "exit_date": pd.to_datetime(last["Date"]).date(), "exit": float(last["close"]), "pnl": pnl})

    # Summarize
    df_trades = pd.DataFrame(trades)
    if df_trades.empty:
        print("No trades simulated")
        return

    total_pnl = df_trades["pnl"].sum()
    wins = df_trades[df_trades["pnl"] > 0]
    win_rate = len(wins) / len(df_trades) if len(df_trades) else 0
    avg_pnl = df_trades["pnl"].mean()

    print(f"Simulated {len(df_trades)} trades for {symbol} over last {len(df)} days")
    print(f"Total PnL: ${total_pnl:,.2f}")
    print(f"Win rate: {win_rate:.2%} ({len(wins)}/{len(df_trades)})")
    print(f"Avg PnL per trade: ${avg_pnl:,.2f}")

    # show sample trades
    print('\nSample trades:')
    print(df_trades.head(10).to_string(index=False))


if __name__ == "__main__":
    today = datetime.today().strftime("%Y-%m-%d")
    simulate("TQQQ", today, lookback_days=252, max_hold=20, risk_per_trade=100.0)
