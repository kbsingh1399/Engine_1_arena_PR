#!/usr/bin/env python3 -u
"""Six-strategy, 20-window walk-forward backtest.

The OOS threshold for each window is learned only from trades whose exits were
known before that window. Position size is bounded by both stop risk and a hard
notional cap, and invalid/placeholder ATR values never enter the trade set.
"""
import os,sys,gc,json,time,warnings; warnings.filterwarnings('ignore')
from pathlib import Path; from datetime import datetime; import numpy as np; import pandas as pd
from numba import njit
# FIX (Fable5-4.1): Import canonical signal definitions from shared module.
from signals_shared import STRAT_MAP, atr
STRATS = list(STRAT_MAP.items())

os.environ.update({k:"2" for k in ["OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS"]})
ROOT=Path('.'); DATA=ROOT/'backtesting_data'
SYMBOLS=["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","ADAUSDT","AVAXUSDT","DOGEUSDT","DOTUSDT","LINKUSDT","LTCUSDT","NEARUSDT","SUIUSDT","TRXUSDT"]
MONTHS=[("2020-03-18","2020-04-18"),("2020-11-07","2020-12-07"),("2021-01-24","2021-02-24"),("2021-06-13","2021-07-13"),("2021-10-29","2021-11-29"),("2022-02-08","2022-03-08"),("2022-05-21","2022-06-21"),("2022-09-14","2022-10-14"),("2022-12-03","2023-01-03"),("2023-04-17","2023-05-17"),("2023-08-25","2023-09-25"),("2023-11-10","2023-12-10"),("2024-02-19","2024-03-19"),("2024-07-06","2024-08-06"),("2024-10-28","2024-11-28"),("2025-01-15","2025-02-15"),("2025-05-03","2025-06-03"),("2025-09-22","2025-10-22"),("2026-02-11","2026-03-11"),("2026-06-09","2026-07-09")]

# FEE CHANGE: Unified via risk_config (F-03 Parity)
from risk_config import (
    FEE_RT as FEE, CAP, RSK, MAX_NOTIONAL, ATR_EPSILON,
    TWR, TROI, TDD, MINTR, TP, TRA, MAXTR,
)
def log(m): print(f"[{datetime.now().strftime('%H:%M:%S')}] {m}",flush=True)

@njit(nogil=True)
def sim(h,l,c,entry_idx,entry,atr,dr):
    """Simulate one trade with finite, bounded position sizing.

    ``atr()`` deliberately maps zero-range candles to ``ATR_EPSILON``.  The
    old strict ``atr < 1e-6`` check therefore let the sentinel through and
    sized ``RSK / 1e-6`` units.  Values at the floor are invalid.  A notional
    cap also makes every finite near-zero ATR safe rather than relying on one
    magic epsilon to bound leverage.
    """
    if (not np.isfinite(atr)) or (not np.isfinite(entry)) or atr<=ATR_EPSILON or entry<=0.0:
        return 0.0,0.0,0.0,0.0,0.0
    n=len(c); sd=atr; td=TP*atr; trd=TRA*atr
    st=entry-sd if dr==1 else entry+sd; cs=st; bp=entry; ns=st
    mx=min(entry_idx+288+1,n); ep=c[mx-1]; bh=mx-1-entry_idx
    mae=0.0
    for j in range(entry_idx+1,mx):
        if dr==1:
            if l[j]<=cs:
                # The simulator assumes a fill at the stop. Do not measure MAE
                # at a later, unknowable point inside the same OHLC candle.
                ae=max(0.0,entry-cs)
                if ae>mae: mae=ae
                ep=cs; bh=j-entry_idx; break
            ae=max(0.0,entry-l[j])
            if ae>mae: mae=ae
            if h[j]>bp: bp=h[j]
            if (bp-entry)>=td: ns=bp-trd
            if ns>cs: cs=ns
        else:
            if h[j]>=cs:
                ae=max(0.0,cs-entry)
                if ae>mae: mae=ae
                ep=cs; bh=j-entry_idx; break
            ae=max(0.0,h[j]-entry)
            if ae>mae: mae=ae
            if l[j]<bp: bp=l[j]
            if (entry-bp)>=td: ns=bp+trd
            if ns<cs: cs=ns
    u=min(RSK/sd,MAX_NOTIONAL/entry)
    g=u*(ep-entry) if dr==1 else u*(entry-ep)
    f=u*entry*FEE/2.0+u*abs(ep)*FEE/2.0; npnl=g-f; r=npnl/RSK; lb=1.0 if npnl>0 else 0.0
    mae_dollar=u*mae
    return npnl,r,lb,bh,mae_dollar

@njit(nogil=True)
def gen_trades_numba(h,l,c,o,a,sig):
    n=len(c); results=[]; i=200; cd=0
    while i<n-100:
        if i>=cd:
            dr=sig[i]
            if dr!=0:
                entry=o[i+1] if i+1<n else c[i]; av=a[i]
                # Check before sim so rejected dead candles are not appended as
                # zero-PnL losses and do not alter the strategy cooldown.
                if np.isfinite(av) and np.isfinite(entry) and av>ATR_EPSILON and entry>0.0:
                    net,r,lb,bh,mae=sim(h,l,c,i,entry,av,int(dr))
                    results.append((i,dr,net,r,lb,bh,mae)); cd=i+bh+2
        i+=1
    return results

def _normalise_exchange_timestamps(df, column):
    """Parse the parquet's IST wall-clock timestamps into naive UTC.

    New pipeline rows omit the literal ``" IST"`` suffix but are still written
    after the pipeline's +05:30 conversion.  Treating only suffixed rows as IST
    creates a discontinuity.  Patch runs can also leave both spellings of the
    same candle; prefer the newer, suffix-free row and retain one UTC bar.
    """
    text=df[column].astype(str)
    df=df.copy()
    df["_suffix_legacy"]=text.str.endswith(" IST")
    df["ts"]=pd.to_datetime(text.str.replace(" IST","",regex=False),errors="coerce")-pd.Timedelta(hours=5,minutes=30)
    df=df.dropna(subset=["ts"])
    df=df.sort_values(["ts","_suffix_legacy"],kind="stable").drop_duplicates("ts",keep="first")
    return df.drop(columns=["_suffix_legacy"])

def load(sym):
    sp=DATA/f"Master_{sym}_15m_Final_Summary.parquet"; fp=DATA/f"Master_{sym}_15m_Final_Footprint.parquet"
    if not sp.exists(): return pd.DataFrame()
    df=pd.read_parquet(sp)
    tc="TimeStamp" if "TimeStamp" in df.columns else "Timestamp"
    df=_normalise_exchange_timestamps(df,tc)
    if fp.exists():
        df_f=pd.read_parquet(fp); tcf="TimeStamp" if "TimeStamp" in df_f.columns else "Timestamp"
        df_f=_normalise_exchange_timestamps(df_f,tcf)
        dc=[c for c in ["Symbol","POC Price","Candle #","Timestamp","TimeStamp","time","Is POC"] if c in df_f.columns]
        if dc: df_f=df_f.drop(columns=dc,errors="ignore")
        df=pd.merge_asof(df.sort_values("ts"),df_f.sort_values("ts"),on="ts",direction="backward",tolerance=pd.Timedelta(minutes=5))
    else: df=df.sort_values("ts")
    dc=[c for c in ["Symbol","POC Price","Candle #","Timestamp","TimeStamp","time","Is POC"] if c in df.columns]
    if dc: df=df.drop(columns=dc,errors="ignore")
    for c in df.columns:
        if c!="ts": df[c]=pd.to_numeric(df[c],errors="coerce")
    # Historical rows store notional volume while new patch rows store base
    # quantity.  Detect the latter from the causal candle fields and normalize
    # to notional so rolling volume features do not see a unit-regime break.
    if all(c in df.columns for c in ["Volume","Buy Qty","Sell Qty","Close"]):
        qty=df["Buy Qty"].fillna(0)+df["Sell Qty"].fillna(0)
        implied=df["Volume"]/(qty.replace(0,np.nan))
        base_qty=implied.abs()<(df["Close"].abs()*0.1)
        df.loc[base_qty,"Volume"]=df.loc[base_qty,"Volume"]*df.loc[base_qty,"Close"].abs()
    for c in df.columns:
        if c!="ts": df[c]=df[c].astype(np.float32)
    return df.set_index("ts")

def zs(s,w): return (s-s.rolling(w,min_periods=1).mean())/s.rolling(w,min_periods=1).std().replace(0,1e-10)

def featurize(df,br=None):
    if br is not None:
        cj=[c for c in br.columns if c not in df.columns]
        if cj: df=df.join(br[cj],how="left")
        if "btc_CVD" in df.columns: df["btc_CVD"]=df["btc_CVD"].ffill().fillna(0)
    df["atr"]=atr(df, 14)
    if "CVD" in df.columns:
        df["cvd_d"]=df["CVD"].diff(5)
        for k in [4,10,20]: df[f"zc{k}"]=zs(df["CVD"],k)
    else: df["cvd_d"]=0.0
    for k in [4,10,20]: df[f"zc{k}"]=df.get(f"zc{k}",pd.Series(0,index=df.index))
    df["bcvm"]=df["btc_CVD"].diff(2) if "btc_CVD" in df.columns else 0.0
    for k in [4,10,20]: df[f"zb{k}"]=zs(df["btc_CVD"],k) if "btc_CVD" in df.columns else 0.0
    df["ef"]=df["Close"].ewm(span=200,min_periods=50).mean(); df["es"]=df["Close"].ewm(span=800,min_periods=100).mean()
    df["mc"]=np.where((df["ef"]-df["es"])/df["atr"].replace(0,1e-10)>0.5,1,np.where((df["ef"]-df["es"])/df["atr"].replace(0,1e-10)<-0.5,-1,0))
    for s,n in [(8,"e8"),(21,"e21"),(50,"e50")]: df[n]=df["Close"].ewm(span=s,min_periods=1).mean()
    atrs=df["atr"].replace(0,1e-10); df["p8"]=(df["Close"]-df["e8"])/atrs; df["p21"]=(df["Close"]-df["e21"])/atrs; df["p50"]=(df["Close"]-df["e50"])/atrs
    d=df["Close"].diff(); g=d.clip(lower=0).rolling(14,min_periods=1).mean(); l=(-d.clip(upper=0)).rolling(14,min_periods=1).mean()
    df["rsi"]=100-(100/(1+g/l.replace(0,1e-10)))
    df["vr"]=zs(df["atr"],100)
    for s,c in [("l","Agg. Liq Long"),("s","Agg. Liq Short")]:
        if c in df.columns:
            df[f"liq{s}"]=pd.to_numeric(df[c],errors="coerce").fillna(0).rolling(5,min_periods=1).sum()
            df[f"liq{s}m"]=df[f"liq{s}"].rolling(100,min_periods=1).mean()
        else: df[f"liq{s}"]=0.0; df[f"liq{s}m"]=0.0
    if "Agg. OI" in df.columns:
        oi=pd.to_numeric(df["Agg. OI"],errors="coerce").ffill(); df["zoi"]=zs(oi,100); df["oid"]=oi.diff(5)/(oi.shift(5)+1e-10)
        df["oicc"]=np.sign(df["oid"].fillna(0))*np.sign(df["cvd_d"].fillna(0))
    else: df["zoi"]=0.0; df["oid"]=0.0; df["oicc"]=0.0
    if "Long/Short Ratio (Account)" in df.columns: df["zls"]=zs(pd.to_numeric(df["Long/Short Ratio (Account)"],errors="coerce").ffill(),100)
    else: df["zls"]=0.0
    if "Agg. Funding Rate" in df.columns:
        fr=pd.to_numeric(df["Agg. Funding Rate"],errors="coerce").fillna(0); df["fr"]=fr; df["zfr"]=zs(fr,20)
    else: df["fr"]=0.0; df["zfr"]=0.0
    for c in ["Bid Qty","Ask Qty","Delta Qty","Bid Trades","Ask Trades"]:
        if c in df.columns: df[c]=pd.to_numeric(df[c],errors="coerce").fillna(0); df[f"z{c.replace(' ','_').lower()}"]=zs(df[c],10)
    if "Buy Qty" in df.columns and "Sell Qty" in df.columns:
        df["bsr"]=pd.to_numeric(df["Buy Qty"],errors="coerce").fillna(0)/(pd.to_numeric(df["Buy Qty"],errors="coerce").fillna(0)+pd.to_numeric(df["Sell Qty"],errors="coerce").fillna(0)+1e-10)
    else: df["bsr"]=0.5
    df["vr5"]=df["Volume"]/(df["Volume"].rolling(20,min_periods=1).mean()+1e-10)
    df=df.fillna(0).replace([np.inf,-np.inf],0)
    return df

# ======== 6 STRATEGY SIGNAL FUNCTIONS (PATCHED) ========
# All signals deleted and imported from signals_shared.py

import lightgbm as lgb
try:
    import xgboost as xgb
    HAS_XGB=True
except: HAS_XGB=False

def bmodel(tdf):
    excl=['symbol','entry_time','exit_time','strategy','direction','entry_price','net_pnl','r_multiple','label','prob','adj_pnl','mae_dollar']
    fcs=[c for c in tdf.columns if c not in excl and pd.api.types.is_numeric_dtype(tdf[c])]
    if len(tdf)<20 or tdf['label'].sum()<3 or (len(tdf)-tdf['label'].sum())<3: return None,fcs
    X=tdf[fcs].astype(np.float32); y=tdf['label'].astype(np.int32)
    p=y.sum(); sw=max(0.1,float((len(y)-p)/p)) if p>0 else 1.0
    sel=lgb.LGBMClassifier(n_estimators=30,max_depth=3,random_state=42,verbose=-1,n_jobs=1,max_bin=31)
    sel.fit(X,y); imps=sel.feature_importances_; cut=np.percentile(imps,15)
    sc=[c for c,im in zip(fcs,imps) if im>=cut]
    if len(sc)<3: sc=fcs
    models=[]
    m_lgb=lgb.LGBMClassifier(max_depth=5,learning_rate=0.02,n_estimators=200,scale_pos_weight=sw,
        random_state=42,n_jobs=1,verbose=-1,max_bin=63,min_child_samples=8,
        subsample=0.8,colsample_bytree=0.8,reg_alpha=0.1,reg_lambda=0.1)
    m_lgb.fit(X[sc],y); models.append(m_lgb)
    if HAS_XGB:
        m_xgb=xgb.XGBClassifier(max_depth=4,learning_rate=0.03,n_estimators=200,scale_pos_weight=sw,
            random_state=42,n_jobs=1,verbosity=0,subsample=0.8,colsample_bytree=0.8,reg_alpha=0.1)
        m_xgb.fit(X[sc],y); models.append(m_xgb)
    return models,sc

def pred(models,fcs,tdf):
    if len(tdf)==0: tdf=tdf.copy(); tdf['prob']=0.0; return tdf
    vc=[c for c in fcs if c in tdf.columns]; X=tdf[vc].astype(np.float32)
    tdf=tdf.copy()
    probs=[m.predict_proba(X)[:,1] for m in models]
    tdf['prob']=np.mean(probs,axis=0)
    return tdf

def closed_equity_drawdown(trades):
    """Realized max drawdown, including starting capital and exit ordering."""
    if trades.empty: return 0.0
    ordered=trades.sort_values("exit_time")
    # Simultaneous exits are one portfolio event; their arbitrary row order
    # must not manufacture an intra-timestamp peak or trough.
    pnl_by_exit=ordered.groupby("exit_time",sort=True)["net_pnl"].sum()
    equity=CAP+pnl_by_exit.cumsum()
    equity=pd.concat([pd.Series([CAP],dtype=float),equity.reset_index(drop=True)],ignore_index=True)
    peak=equity.cummax()
    return float(((peak-equity)/peak.clip(lower=1e-12)*100.0).max())

def mark_to_market_drawdown(trades):
    """Conservative causal MAE drawdown estimate relative to running peak."""
    if trades.empty or "mae_dollar" not in trades.columns: return closed_equity_drawdown(trades)
    equity=CAP; peak=CAP; worst_dd=0.0
    for row in trades.sort_values("entry_time").itertuples():
        worst_equity=equity-max(0.0,float(row.mae_dollar))
        worst_dd=max(worst_dd,(peak-worst_equity)/max(peak,1e-12)*100.0)
        equity+=float(row.net_pnl)
        peak=max(peak,equity)
    return float(worst_dd)

def best_thresh(pdf):
    """Choose a threshold on validation data only, using the live gates."""
    pdf=pdf.sort_values("entry_time")

    def choose(thresholds,min_n,max_n):
        best=None; best_score=-1e9
        for p in thresholds:
            c=pdf[pdf['prob']>=p]; n=len(c)
            if n<min_n or n>max_n: continue
            nw=(c['net_pnl']>0).sum(); wr=(nw/n)*100; tp=c['net_pnl'].sum(); roi=(tp/CAP)*100
            dd=max(closed_equity_drawdown(c),mark_to_market_drawdown(c))
            if wr>TWR and roi>0 and dd<TDD:
                score=roi*(wr/100)/max(dd,0.1)*np.log1p(n)
                if score>best_score: best=float(p); best_score=score
        return best

    # Primary calibration preserves a 2x trade-count safety margin on a fixed
    # grid and never observes OOS probability counts or outcomes.
    best=choose(np.arange(0.51,0.92,0.02),MINTR*2,MAXTR)
    if best is not None: return best

    # Some uncalibrated ensembles put all observations above 0.91, leaving no
    # fixed-grid candidate. Fall back to validation ranks with a wider 4x
    # count buffer rather than lowering a threshold after seeing OOS activity.
    probs=pdf["prob"].dropna().sort_values(ascending=False)
    rank_thresholds=[float(probs.iloc[k-1]) for k in range(MINTR*4,min(MAXTR*2,len(probs))+1,2)]
    return choose(rank_thresholds,MINTR*4,MAXTR*2)

def run_one(name,mksig):
    log(f"\n{'='*60}\nSTRATEGY: {name}\n{'='*60}")
    btc=load("BTCUSDT"); br=btc[["Close","CVD"]].copy(); br.columns=["btc_Close","btc_CVD"]; del btc; gc.collect()
    at={}
    er=['ts','Timestamp','TimeStamp','Symbol','POC Price','Candle #','time','Open','High','Low','Close','Volume','Trades','btc_Close','btc_CVD']
    for sym in SYMBOLS:
        df=load(sym)
        if df.empty: continue
        ref=br if sym!="BTCUSDT" else None
        dff=featurize(df.copy(),ref); sg=mksig(dff)
        h=dff["High"].values.astype(np.float64); l=dff["Low"].values.astype(np.float64)
        c=dff["Close"].values.astype(np.float64); o=dff["Open"].values.astype(np.float64)
        a=dff["atr"].values.astype(np.float64); ts=dff.index.values
        res=gen_trades_numba(h,l,c,o,a,sg)
        fc=[c for c in dff.columns if c not in er and pd.api.types.is_numeric_dtype(dff[c])]
        fa={c:dff[c].values.astype(np.float32) for c in fc}
        n2=len(ts)
        if res:
            rr=np.asarray(res,dtype=np.float64)
            idx=rr[:,0].astype(np.int64); dr=rr[:,1].astype(np.int32)
            net=rr[:,2].copy(); bh=rr[:,5].astype(np.int64); mae=rr[:,6].copy()
            entry_idx=np.minimum(idx+1,n2-1); exit_idx=np.minimum(idx+bh,n2-1)
            entry_price=o[entry_idx]
            atr_entry=a[idx]
            units=np.minimum(RSK/atr_entry,MAX_NOTIONAL/entry_price)
            # Expected funding accrual is linear in units.  Prefix sums retain
            # the old mean-rate approximation without an O(n_bars) allocation
            # inside every trade (the former runtime bottleneck).
            if "fr" in fa:
                fr=np.nan_to_num(fa["fr"].astype(np.float64),nan=0.0,posinf=0.0,neginf=0.0)
                fr_cs=np.concatenate((np.zeros(1),np.cumsum(fr)))
                lengths=(exit_idx-idx+1).astype(np.float64)
                avg_fr=(fr_cs[exit_idx+1]-fr_cs[idx])/np.maximum(lengths,1.0)
                funding_abs=np.abs(avg_fr)/32.0*entry_price*units*np.maximum(bh,0)
                pays=((dr==1)&(avg_fr>0))|((dr==-1)&(avg_fr<0))
                net-=np.where(pays,funding_abs,-funding_abs)
            data={
                "symbol":np.repeat(sym,len(idx)),"entry_time":ts[entry_idx],"exit_time":ts[exit_idx],
                "strategy":np.repeat(name,len(idx)),"direction":dr,"entry_price":entry_price,
                "net_pnl":net,"r_multiple":net/RSK,"label":(net>0).astype(np.int32),"mae_dollar":mae,
            }
            data.update({col:fa[col][idx] for col in fc})
            trades=pd.DataFrame(data)
        else:
            trades=pd.DataFrame()
        at[sym]=trades
        log(f"  {sym}: {len(trades)} trades")
        del dff,sg,h,l,c,o,a,fc,fa,res,trades; gc.collect()
    del br; gc.collect()
    log(f"\n--- WALK-FORWARD: {name} ---")
    res=[]
    for wi,(ss,se) in enumerate(MONTHS):
        ws=pd.Timestamp(ss); we=pd.Timestamp(se)
        log(f"  W{wi+1}/20: {ss}->{se}")
        pt=[]; tt=[]
        for sym,tdf in at.items():
            if tdf.empty: continue
            # Purge labels for positions that had not exited at the OOS boundary.
            pt.append(tdf[tdf['exit_time']<ws].copy())
            tt.append(tdf[(tdf['entry_time']>=ws)&(tdf['entry_time']<=we)].copy())
        tdf=pd.concat(tt,ignore_index=True).sort_values('entry_time') if tt else pd.DataFrame()
        if tdf.empty:
            log("    No test trades")
            res.append({'w':wi+1,'start':ss,'end':se,'threshold':None,'tr':0,'wins':0,'wr':0,'pnl':0,'roi':0,'dd':0,'mtm_dd':0,'passed':False,'verdict':'FAIL'})
            continue
        pdf=pd.concat(pt,ignore_index=True).sort_values('entry_time') if pt else pd.DataFrame()
        bp=None; bdf=pd.DataFrame(); deployed=None
        # Start with the most recent 30 days. If that prior-only calibration
        # regime has no safe threshold, expand to 60/90 days and retrain behind
        # the correspondingly purged boundary. No OOS count, feature, or outcome
        # participates in this fallback.
        for val_days in (30,60,90):
            vc=ws-pd.Timedelta(days=val_days)
            trdf=pdf[pdf['exit_time']<vc] if not pdf.empty else pd.DataFrame()
            vdf=pdf[(pdf['entry_time']>=vc)&(pdf['exit_time']<ws)] if not pdf.empty else pd.DataFrame()
            m,fcs=bmodel(trdf) if not trdf.empty else (None,[])
            if m is None or len(vdf)<MINTR: continue
            vp=pred(m,fcs,vdf); candidate=best_thresh(vp)
            if candidate is not None:
                bp=candidate; deployed=(m,fcs,vdf,val_days); break
        if deployed is None:
            log("    No prior-only calibration horizon produced a deployable threshold")
        else:
            m,fcs,vdf,val_days=deployed
            log(f"    Val:{len(vdf)} ({val_days}d)->th={bp:.2f}")
            tp=pred(m,fcs,tdf)
            # Applying a fixed threshold is blind to all OOS outcomes and
            # probability counts. A causal monthly exposure cap takes the
            # first MAXTR qualifying entries, just as live execution can.
            bdf=tp[tp['prob']>=bp].sort_values('entry_time').head(MAXTR).copy()
        nt=len(bdf)
        if nt==0:
            log("    No trades after fixed validation filter")
            res.append({'w':wi+1,'start':ss,'end':se,'threshold':bp,'tr':0,'wins':0,'wr':0,'pnl':0,'roi':0,'dd':0,'mtm_dd':0,'passed':False,'verdict':'FAIL'})
            continue
        nw=int((bdf['net_pnl']>0).sum()); wr=(nw/nt)*100; pnl=float(bdf['net_pnl'].sum()); roi=(pnl/CAP)*100
        dd=closed_equity_drawdown(bdf); mtm_dd=mark_to_market_drawdown(bdf)
        log(f"    Tr={nt} Wn={nw} WR={wr:.1f}% PnL=${pnl:,.0f} ROI={roi:.1f}% DD={dd:.1f}% MtM-DD={mtm_dd:.1f}%")
        passed=wr>TWR and roi>=TROI and max(dd,mtm_dd)<TDD and nt>=MINTR
        res.append({'w':wi+1,'start':ss,'end':se,'threshold':bp,'tr':nt,'wins':nw,'wr':wr,'pnl':pnl,'roi':roi,'dd':dd,'mtm_dd':mtm_dd,'passed':passed,'verdict':'PASS' if passed else 'FAIL'})
        if passed: log(f"    PASS")
        else: log(f"    ABORT! FAILED Window {wi+1}")
        # if not passed: break
    pw=sum(1 for r in res if r['passed']); tw=len(res); tp=sum(r['pnl'] for r in res); tt=sum(r['tr'] for r in res); twi=sum(r['wins'] for r in res)
    avg_mtm=np.mean([r['mtm_dd'] for r in res if r['mtm_dd']>0]) if any(r['mtm_dd']>0 for r in res) else 0
    log(f"\n  {name}: {pw}/{tw} PASSED | PnL=${tp:,.0f} | WR={twi/tt*100:.1f}% | Avg MtM-DD={avg_mtm:.1f}%" if tt>0 else f"\n  {name}: {pw}/{tw} PASSED | No trades")
    del at; gc.collect(); return res

if __name__=="__main__":
    log("SIX-STRATEGY PURGED WALK-FORWARD RUNNER")
    log(f"Fee={FEE*100:.2f}% RT | ATR floor={ATR_EPSILON:g} | max notional=${MAX_NOTIONAL:,.0f}")
    requested={s.strip() for s in os.environ.get("BACKTEST_STRATEGIES","").split(",") if s.strip()}
    selected=[item for item in STRATS if not requested or item[0] in requested]
    unknown=requested-{name for name,_ in STRATS}
    if unknown: raise SystemExit(f"Unknown BACKTEST_STRATEGIES: {sorted(unknown)}")
    all_res={}
    for name,mksig in selected:
        t0=time.time(); all_res[name]=run_one(name,mksig)
        log(f"TIME {name}: {(time.time()-t0)/60:.1f}min\n"); gc.collect()
    log(f"\n{'='*100}"); log("FINAL SUMMARY (PATCHED)"); log(f"{'='*100}")
    log(f"{'Strategy':<22s} {'Pass':>5s} {'PnL':>14s} {'WR':>7s} {'Avg ROI':>8s} {'Avg MtM-DD':>10s}")
    for name,res in all_res.items():
        pw=sum(1 for r in res if r['passed']); tw=len(res); tp=sum(r['pnl'] for r in res); tt=sum(r['tr'] for r in res); twi=sum(r['wins'] for r in res)
        owr=f"{twi/tt*100:.1f}%" if tt>0 else "N/A"; aroi=f"{np.mean([r['roi'] for r in res]):.1f}%" if res else "N/A"
        amtm=f"{np.mean([r['mtm_dd'] for r in res if r['mtm_dd']>0]):.1f}%" if any(r['mtm_dd']>0 for r in res) else "N/A"
        log(f"  {name:<20s} {pw:>3d}/{tw:<2d}  ${tp:>12,.0f}  {owr:>6s}  {aroi:>7s}  {amtm:>9s}")
    log(f"{'='*100}")
    
    # Comparison table
    log("\nCOMPARISON: Original vs Patched")
    log(f"{'='*80}")
    orig={"S1_Liquidation":(51326,76.2),"S2_CVD_Momentum":(64864,76.5),"S3_Trend_Follow":(59601,79.5),
          "S4_Mean_Reversion":(75455,77.0),"S5_Vol_Breakout":(59750,78.9),"S6_OI_Coherence":(61925,79.5)}
    log(f"{'Strategy':<22s} {'Orig PnL':>12s} {'Patch PnL':>12s} {'Delta':>10s} {'Orig WR':>8s} {'Patch WR':>8s}")
    for name,res in all_res.items():
        pw=sum(1 for r in res if r['passed']); tw=len(res)
        tp=sum(r['pnl'] for r in res); tt=sum(r['tr'] for r in res); twi=sum(r['wins'] for r in res)
        owr=twi/tt*100 if tt>0 else 0
        op,ow=orig.get(name,(0,0))
        delta=tp-op
        log(f"  {name:<20s} ${op:>10,.0f}  ${tp:>10,.0f}  {'+' if delta>=0 else ''}{delta:>8,.0f}  {ow:>6.1f}%  {owr:>6.1f}%")
    log(f"{'='*80}")
    
    output=os.environ.get("BACKTEST_OUTPUT","all_6_results.json")
    with open(output,'w') as f: json.dump(all_res,f,indent=2,default=str)
    log(f"Saved: {output}")
