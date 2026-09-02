"""
data_loader.py — load backtesting OHLC files from a folder.

A "data folder" may contain one or more .csv / .tsv / .txt / .dat / .npz files.
Every file must hold bars with open, high, low, close columns
(timestamp column optional, volume ignored).

Column detection:
  * with header row  : names are matched case-insensitively
                       (open/o, high/h, low/l, close/c/last; date/time/...)
  * without header   : the first column that does not parse as a number is
                       treated as the timestamp; the first four numeric
                       columns are taken as open, high, low, close.
Multiple files are concatenated chronologically (by timestamp when every
file carries timestamps, otherwise by filename order).
The protocol uses the MOST RECENT 17,520 one-hour bars of the merged series.
"""
import os
import csv
import math
from datetime import datetime
import numpy as np

REQUIRED_BARS = 17520  # keep in sync with strategy_engine.TOTAL_BARS

_TS_NAMES = {'date', 'time', 'datetime', 'timestamp', 'ts', 'date_time',
             'date/time', 'open_time', 'opentime', 't', 'local_time', 'unix_time'}
_O_NAMES = {'open', 'o', 'open_price', 'price_open'}
_H_NAMES = {'high', 'h', 'high_price', 'price_high'}
_L_NAMES = {'low', 'l', 'low_price', 'price_low'}
_C_NAMES = {'close', 'c', 'close_price', 'price_close', 'last', 'close_last',
            'adj_close'}

_TS_FORMATS = ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M',
               '%Y-%m-%d', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M',
               '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M', '%d/%m/%Y %H:%M:%S',
               '%d.%m.%Y %H:%M:%S', '%Y.%m.%d %H:%M:%S', '%Y%m%d %H:%M:%S',
               '%Y-%m-%d %H:%M:%S.%f')


def _parse_ts(s):
    s = s.strip().strip('"').strip("'")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def _to_float(s):
    try:
        v = float(s.strip().strip('"').strip("'").replace(',', ''))
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def _sniff_delimiter(line):
    best, best_n = ',', -1
    for d in (',', ';', '\t', '|'):
        n = line.count(d)
        if n > best_n:
            best, best_n = d, n
    return best


def _read_rows(path):
    with open(path, 'r', newline='') as f:
        sample = f.readline()
        f.seek(0)
        delim = _sniff_delimiter(sample)
        rows = [r for r in csv.reader(f, delimiter=delim) if r]
    return rows


def _parse_file(path):
    """Return (ts or None, o, h, l, c) numpy float64 arrays for one file."""
    rows = _read_rows(path)
    if not rows:
        return None, None, None, None, None
    # header detection: first cell of row 0 not parseable as float
    header = None
    start = 0
    if _to_float(rows[0][0]) is None and len(rows) > 1:
        header = [x.strip().lower().strip('"').strip("'") for x in rows[0]]
        start = 1
    data = rows[start:]
    if not data:
        return None, None, None, None, None

    i_o = i_h = i_l = i_c = i_ts = None
    if header is not None:
        for j, nm in enumerate(header):
            if nm in _TS_NAMES and i_ts is None:
                i_ts = j
            elif nm in _O_NAMES and i_o is None:
                i_o = j
            elif nm in _H_NAMES and i_h is None:
                i_h = j
            elif nm in _L_NAMES and i_l is None:
                i_l = j
            elif nm in _C_NAMES and i_c is None:
                i_c = j
    if None in (i_o, i_h, i_l, i_c):
        # positional fallback on the first data row
        first = data[0]
        num_cols = [j for j, cell in enumerate(first) if _to_float(cell) is not None]
        i_ts2 = [j for j in range(len(first)) if j not in set(num_cols)]
        if len(num_cols) < 4:
            raise ValueError(f'{path}: cannot locate open/high/low/close columns')
        i_o, i_h, i_l, i_c = num_cols[0], num_cols[1], num_cols[2], num_cols[3]
        if i_ts is None and i_ts2:
            i_ts = i_ts2[0]

    ts_all, bad_ts = [], 0
    o_l, h_l, l_l, c_l = [], [], [], []
    dropped = 0
    for r in data:
        if len(r) <= max(i_o, i_h, i_l, i_c):
            dropped += 1
            continue
        vo, vh, vl, vc = (_to_float(r[i_o]), _to_float(r[i_h]),
                          _to_float(r[i_l]), _to_float(r[i_c]))
        if vo is None or vh is None or vl is None or vc is None \
                or min(vo, vh, vl, vc) <= 0 or vh < vl or max(vo, vc) > vh + 1e-12 \
                or min(vo, vc) < vl - 1e-12:
            dropped += 1
            continue
        o_l.append(vo); h_l.append(vh); l_l.append(vl); c_l.append(vc)
        if i_ts is not None and i_ts < len(r):
            v = _parse_ts(r[i_ts])
            if v is None:
                bad_ts += 1
            ts_all.append(v)
        else:
            ts_all.append(None)
    if ts_all and bad_ts > 0.05 * len(ts_all):
        ts_all = [None] * len(ts_all)  # unreliable timestamps -> ignore
    arr = lambda x: np.asarray(x, dtype=np.float64)
    if dropped:
        print(f'  [{os.path.basename(path)}] dropped {dropped} malformed rows')
    return (np.asarray(ts_all, dtype=np.float64)
            if ts_all and ts_all[0] is not None else None,
            arr(o_l), arr(h_l), arr(l_l), arr(c_l))


def _load_npz(path):
    z = np.load(path)
    if not all(k in z.files for k in ('o', 'h', 'l', 'c')):
        raise ValueError(f'{path}: npz must contain o/h/l/c arrays')
    return None, z['o'].astype(np.float64), z['h'].astype(np.float64), \
        z['l'].astype(np.float64), z['c'].astype(np.float64)


def load_folder(folder, required_bars=REQUIRED_BARS, verbose=True):
    """Load and merge every OHLC file in `folder`; return (o, h, l, c).

    Keeps the most recent `required_bars` bars of the merged series.
    Raises ValueError if the folder holds fewer bars than required.
    """
    if not os.path.isdir(folder):
        raise FileNotFoundError(f'data folder not found: {folder}')
    files = sorted(
        f for f in os.listdir(folder)
        if f.lower().endswith(('.csv', '.tsv', '.txt', '.dat'))
        and not f.startswith(('result', 'run_', 'all_')))
    if not files:
        npz = sorted(f for f in os.listdir(folder) if f.lower().endswith('.npz'))
        if not npz:
            pq_files = sorted(f for f in os.listdir(folder) if f.lower().endswith('.parquet') and not f.lower().startswith('master_'))
            if not pq_files:
                raise FileNotFoundError(
                    f'no .csv/.tsv/.txt/.dat/.npz/.parquet data files found in {folder}')
            import pandas as pd
            sym = os.environ.get('BINANCE_SYMBOL', '').upper()
            target_pq = None
            if sym:
                for f in pq_files:
                    if f.upper().startswith(sym):
                        target_pq = f
                        break
            if not target_pq:
                for f in pq_files:
                    if 'BTCUSDT' in f.upper():
                        target_pq = f
                        break
            if not target_pq:
                target_pq = pq_files[0]
            
            target_path = os.path.join(folder, target_pq)
            df = pd.read_parquet(target_path)
            tf = os.environ.get('TIMEFRAME', '1h').lower()
            if tf == '1h' and 'datetime_utc' in df.columns:
                df['dt'] = pd.to_datetime(df['datetime_utc'], utc=True)
                df_agg = df.set_index('dt').resample('1h').agg({
                    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
                }).dropna()
                o = df_agg['open'].values.astype(np.float64)
                h = df_agg['high'].values.astype(np.float64)
                l = df_agg['low'].values.astype(np.float64)
                c = df_agg['close'].values.astype(np.float64)
            else:
                o = df['open'].values.astype(np.float64)
                h = df['high'].values.astype(np.float64)
                l = df['low'].values.astype(np.float64)
                c = df['close'].values.astype(np.float64)
            if verbose:
                print(f'data: parquet file {target_pq} from {folder}  |  {len(c):,} bars (timeframe={tf})')
            if len(c) < required_bars:
                raise ValueError(f'{folder}/{target_pq}: protocol needs >= {required_bars} bars, found {len(c)}.')
            return o[-required_bars:], h[-required_bars:], l[-required_bars:], c[-required_bars:]
        ts, o, h, l, c = _load_npz(os.path.join(folder, npz[0]))
        n_src = 1
    else:
        n_src = len(files)
        parts = []
        for fn in files:
            parts.append(_parse_file(os.path.join(folder, fn)))
        parts = [p for p in parts if p[1] is not None and p[1].size]
        if not parts:
            raise ValueError(f'no usable rows found in {folder}')
        if all(p[0] is not None for p in parts):
            ts = np.concatenate([p[0] for p in parts])
            order = np.argsort(ts, kind='stable')
            o = np.concatenate([p[1] for p in parts])[order]
            h = np.concatenate([p[2] for p in parts])[order]
            l = np.concatenate([p[3] for p in parts])[order]
            c = np.concatenate([p[4] for p in parts])[order]
            ts = ts[order]
            if ts.size > 1:
                keep = np.empty(ts.size, dtype=bool)
                keep[:-1] = ts[1:] != ts[:-1]
                keep[-1] = True           # duplicate timestamps: keep last
                o, h, l, c = o[keep], h[keep], l[keep], c[keep]
        else:
            ts = None
            o = np.concatenate([p[1] for p in parts])
            h = np.concatenate([p[2] for p in parts])
            l = np.concatenate([p[3] for p in parts])
            c = np.concatenate([p[4] for p in parts])

    n = c.shape[0]
    if verbose:
        rng = ''
        if ts is not None and n:
            try:
                t0 = datetime.fromtimestamp(float(ts[0]))
                t1 = datetime.fromtimestamp(float(ts[-1]))
                rng = f' | {t0:%Y-%m-%d %H:%M} .. {t1:%Y-%m-%d %H:%M}'
            except Exception:
                pass
        print(f'data: {n_src} file(s) from {folder}  |  {n:,} bars{rng}')
    if n < required_bars:
        raise ValueError(
            f'{folder}: protocol needs >= {required_bars} bars, found {n}. '
            f'Add more history (17,520 one-hour bars recommended).')
    return o[-required_bars:], h[-required_bars:], l[-required_bars:], c[-required_bars:]
