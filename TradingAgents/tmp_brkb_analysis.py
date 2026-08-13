from tradingagents.dataflows.symbol_utils import normalize_symbol
from tradingagents.dataflows.stockstats_utils import load_ohlcv
from tradingagents.dataflows.stocktwits import fetch_stocktwits_messages
from stockstats import wrap
import pandas as pd

RAW = 'BRK-B'
DATE = '2026-08-10'

try:
    canon = normalize_symbol(RAW)
    print('RAW:', RAW)
    print('Canonical:', canon)

    df = load_ohlcv(RAW, DATE)
    print('Rows:', len(df), 'LastDate:', df['Date'].max().strftime('%Y-%m-%d'))
    last = df.sort_values('Date').iloc[-1]
    print('LastClose:', float(last['Close']))

    w = wrap(df.copy())
    w['Date'] = pd.to_datetime(w['Date']).dt.strftime('%Y-%m-%d')
    inds = ['close_10_ema','close_50_sma','close_200_sma','rsi','macdh','atr']
    for ind in inds:
        try:
            _ = w[ind]
            val = w.iloc[-1][ind]
            print(f"{ind}: {val}")
        except Exception as e:
            print(f"{ind}: error {e}")

    if len(df) >= 21:
        p20 = float(df.sort_values('Date').iloc[-1]['Close']) / float(df.sort_values('Date').iloc[-21]['Close']) - 1
        print('20d_return_pct:', round(p20*100,2))

    try:
        vol = df.sort_values('Date')['Volume']
        print('Vol_last:', int(vol.iloc[-1]), 'Vol_20avg:', int(vol.tail(21).iloc[:-1].mean()))
    except Exception:
        pass

    try:
        st = fetch_stocktwits_messages(RAW, limit=30)
        print('\nStockTwits summary (first lines):')
        for i, line in enumerate(st.split('\n')):
            if i >= 6:
                break
            print(line)
    except Exception as e:
        print('ST_FETCH_ERROR', e)

except Exception as e:
    print('ERROR', e)
