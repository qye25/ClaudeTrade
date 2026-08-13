import math
from datetime import datetime

import yfinance as yf
import pandas as pd


def scan_puts(symbol: str, min_dte=20, max_dte=40, targets=(0.15, 0.2)):
    tk = yf.Ticker(symbol)
    today = datetime.utcnow().date()
    chain_dates = tk.options
    if not chain_dates:
        print('No options data')
        return

    last = tk.history(period='1d')
    if last.empty:
        print('No price data')
        return
    price = float(last['Close'].iloc[-1])
    out = []

    for d in chain_dates:
        exp = datetime.fromisoformat(d).date()
        dte = (exp - today).days
        if dte < min_dte or dte > max_dte:
            continue
        opt = tk.option_chain(d)
        puts = opt.puts
        if puts is None or puts.empty:
            continue

        for targ in targets:
            target_strike = price * (1 - targ)
            # choose nearest strike <= target_strike
            candidates = puts[puts['strike'] <= target_strike]
            if candidates.empty:
                # pick lowest available
                candidates = puts
            candidates = candidates.sort_values('strike', ascending=False)
            row = candidates.iloc[0]
            bid = row.get('bid', 0.0) or 0.0
            ask = row.get('ask', 0.0) or 0.0
            mid = (bid + ask) / 2 if (bid > 0 or ask > 0) else row.get('lastPrice', 0.0) or 0.0
            strike = float(row['strike'])
            premium_per_share = mid
            cash_required = strike * 100
            roi = (premium_per_share * 100) / cash_required if cash_required > 0 else 0.0
            annualized = roi * (365 / max(dte, 1))
            breakeven = strike - premium_per_share
            iv = row.get('impliedVolatility', None)
            out.append({
                'expiry': d,
                'dte': dte,
                'target_pct': targ,
                'strike': strike,
                'mid': mid,
                'premium_contract': mid * 100,
                'cash_required': cash_required,
                'roi_pct': roi * 100,
                'annualized_pct': annualized * 100,
                'breakeven': breakeven,
                'impliedVol': iv,
            })

    if not out:
        print('No matching options found')
        return

    df = pd.DataFrame(out).sort_values(['target_pct', 'dte'])
    pd.set_option('display.float_format', lambda x: f"{x:.2f}")
    print(f"Underlying {symbol} last: {price:.2f}")
    print(df.to_string(index=False))


if __name__ == '__main__':
    scan_puts('TQQQ', min_dte=20, max_dte=40, targets=(0.15, 0.2))
