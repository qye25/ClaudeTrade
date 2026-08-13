import math
from datetime import datetime

import numpy as np
import pandas as pd

from tradingagents.dataflows.stockstats_utils import load_ohlcv


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put_price(S, K, T, sigma, r=0.03):
    if T <= 0 or sigma <= 0:
        return max(0.0, K - S)  # intrinsic
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)
    return max(0.0, put)


def simulate_csp(symbol: str, curr_date: str, lookback_days=365, dte_list=(24, 31, 38), targets=(0.15, 0.20)):
    df = load_ohlcv(symbol, curr_date)
    if df.empty:
        print('No price data')
        return

    df = df.sort_values('Date').reset_index(drop=True)
    if len(df) > lookback_days:
        df = df.iloc[-lookback_days:].reset_index(drop=True)

    results = []

    # Precompute daily log-returns
    df['logret'] = np.log(df['Close'] / df['Close'].shift(1))

    for i in range(30, len(df) - max(dte_list) - 1):
        sale_date = pd.to_datetime(df.loc[i, 'Date']).date()
        S = float(df.loc[i, 'Close'])

        # estimate vol from prior 21 trading days
        window = df.loc[max(1, i - 21):i, 'logret'].dropna()
        if len(window) < 5:
            continue
        sigma_daily = window.std()
        sigma_annual = sigma_daily * math.sqrt(252)

        for dte in dte_list:
            exp_idx = i + dte
            if exp_idx >= len(df):
                continue
            T = dte / 252.0

            for targ in targets:
                strike = S * (1 - targ)
                # price via BS using historical vol
                prem = bs_put_price(S, strike, T, sigma_annual)
                premium_contract = prem * 100
                cash_required = strike * 100

                expiry_close = float(df.loc[exp_idx, 'Close'])
                if expiry_close < strike:
                    # assigned: pay (strike - expiry_close)*100, net = premium - loss
                    loss = (strike - expiry_close) * 100
                    pnl = premium_contract - loss
                    assigned = True
                else:
                    pnl = premium_contract
                    assigned = False

                results.append({
                    'sale_date': sale_date,
                    'dte': dte,
                    'target_pct': targ,
                    'strike': round(strike, 2),
                    'premium': round(premium_contract, 2),
                    'cash_required': round(cash_required, 2),
                    'expiry_date': pd.to_datetime(df.loc[exp_idx, 'Date']).date(),
                    'expiry_close': round(expiry_close, 2),
                    'pnl': round(pnl, 2),
                    'assigned': assigned,
                })

    df_res = pd.DataFrame(results)
    if df_res.empty:
        print('No simulated trades')
        return

    summary = df_res.groupby(['target_pct', 'dte']).agg(
        trades=('pnl', 'count'),
        total_pnl=('pnl', 'sum'),
        win_rate=('pnl', lambda x: (x > 0).sum() / len(x)),
        avg_pnl=('pnl', 'mean'),
        assignments=('assigned', 'sum'),
    ).reset_index()

    pd.set_option('display.float_format', lambda x: f"{x:.2f}")
    print(f"Simulated CSPs for {symbol} over {len(df)} days (lookback={lookback_days})")
    print(summary.to_string(index=False))

    return df_res, summary


if __name__ == '__main__':
    today = datetime.today().strftime('%Y-%m-%d')
    simulate_csp('TQQQ', today, lookback_days=365, dte_list=(24, 31, 38), targets=(0.15, 0.20))
