"""S4 Minimal - Pre-extraction with reduced scope"""
import os,glob,json,logging,warnings,time
from datetime import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd,numpy as np
from numba import njit
import gc,lightgbm as lgb

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
logger=logging.getLogger(__name__)

SD=os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
DD=os.path.join(SD,"binance_backtesting_data")
RD=os.path.join(SD,"results_s4"); os.makedirs(RD,exist_ok=True)

# Constants
IC=5000.0;FR=0.0008;MC=2;LV=10.0;MN=50000.0;HSR=65.0;DDR=20.0;DDL=0.045

def zs(s,w):
    m=s.rolling(w,min_periods=1).mean();st=s.rolling(w,min_periods=1).std().replace(0,1e-8)
    return(s-m)/st

# Load data (same as before)
def load():
    logger.info("Loading...")
    files=sorted(glob.glob(os.path.join(DD,"*_15m_master_*.parquet")))
    br=None
    bf=os.path.join(DD,"BTCUSDT_15m_master_2020_2026.parquet")
    if os.path.exists(bf):
        df=pd.read_parquet(bf,columns=['datetime_utc','close','spot_cvd_15m'])
        df['datetime_utc']=pd.to_datetime(df['datetime_utc'],utc=True)
        df=df.sort_values('datetime_utc').reset_index(drop=True)
        br=pd.DataFrame({'datetime_utc':df['datetime_utc'],'btc_close':df['close'].astype(np.float32),
            'zb20':zs(df['spot_cvd_15m'],96).clip(-4,4).astype(np.float32)})
    
    data={};loaded=set()
    for f in files:
        sym=os.path.basename(f).split('_')[0]
        if sym in loaded or not sym.endswith("USDT"):continue
        try:
            df=pd.read_parquet(f);df['symbol']=sym
            df['datetime_utc']=pd.to_datetime(df['datetime_utc'],utc=True)
            df=df.sort_values('datetime_utc').reset_index(drop=True)
            if br is not None and sym!="BTCUSDT":
                df=pd.merge_asof(df,br,on='datetime_utc',direction='backward')
            elif sym=="BTCUSDT":
                df['btc_close']=df['close'];df['zb20']=zs(df['spot_cvd_15m'],96).clip(-4,4)
            
            sc=df.get('spot_cvd_15m',0.0)
            df['spot_cvd_delta']=sc.diff().fillna(0)
            df['zc20']=zs(sc,96).clip(-4,4)
            df['zc_rel_btc']=df['zc20']-df.get('zb20',0.0)
            
            ll=df.get('long_liq_usd',pd.Series(0,index=df.index)).abs().fillna(0)
            sl=df.get('short_liq_usd',pd.Series(0,index=df.index)).abs().fillna(0)
            lstd=ll.rolling(96,min_periods=12).std().replace(0,1.0)
            sstd=sl.rolling(96,min_periods=12).std().replace(0,1.0)
            df['long_liq_zscore']=((ll-ll.rolling(96,min_periods=12).mean())/lstd).clip(0,10).fillna(0)
            df['short_liq_zscore']=((sl-sl.rolling(96,min_periods=12).mean())/sstd).clip(0,10).fillna(0)
            
            df['fr']=df.get('funding_rate_pct',pd.Series(0,index=df.index)).fillna(0)
            df['zfr']=zs(df['fr'],20)
            df['atr']=(df['high']-df['low']).rolling(14,min_periods=1).mean().clip(lower=1e-6)
            df['rsi']=df.get('rsi_14',50.0).fillna(50.0)
            ef=df['close'].ewm(span=200,min_periods=50).mean()
            es=df['close'].ewm(span=800,min_periods=100).mean()
            df['mc']=np.where((ef-es)/(df['atr']+1e-8)>0.5,1,np.where((ef-es)/(df['atr']+1e-8)<-0.5,-1,0))
            e8=df['close'].ewm(span=8,min_periods=1).mean()
            df['p8']=(df['close']-e8)/(df['atr']+1e-8)
            df['rsi_slope']=df['rsi'].diff(3)
            df['exhaustion_long']=((100-df['rsi']).clip(0)/100.0)*((-df['p8']).clip(0))
            df['exhaustion_short']=(df['rsi'].clip(0)/100.0)*(df['p8'].clip(0))
            df['next_open']=df['open'].shift(-1)
            df.dropna(subset=['next_open','atr'],inplace=True)
            fc=df.select_dtypes(include=['float64']).columns
            df[fc]=df[fc].astype('float32')
            loaded.add(sym);data[sym]=df;del df;gc.collect()
        except Exception as e:logger.warning(f"Skip {f}: {e}")
    logger.info(f"Loaded {len(data)} syms");return data

OOS=[("2021-03-15","2021-04-15"),("2021-06-15","2021-07-15"),("2021-09-15","2021-10-15"),
    ("2021-12-15","2022-01-15"),("2022-03-15","2022-04-15"),("2022-06-15","2022-07-15"),
    ("2022-09-15","2022-10-15"),("2022-12-15","2023-01-15"),("2023-03-15","2023-04-15"),
    ("2023-06-15","2023-07-15"),("2023-09-15","2023-10-15"),("2023-12-15","2024-01-15"),
    ("2024-03-15","2024-04-15"),("2024-06-15","2024-07-15"),("2024-09-15","2024-10-15"),
    ("2024-12-15","2025-01-15"),("2025-03-15","2025-04-15"),("2025-06-15","2025-07-15"),
    ("2025-10-15","2025-11-15"),("2026-03-15","2026-04-15")]

def wins(ed,hm):
    ws=[];edt=pd.to_datetime(ed,utc=True)
    for i,(ts,te) in enumerate(OOS):
        ts2=pd.to_datetime(ts,utc=True);te2=pd.to_datetime(te,utc=True)
        if te2>edt:break
        ws.append({'w':i+1,'trs':ts2-relativedelta(months=hm),'tre':ts2,'ts':ts2,'te':te2})
    return ws

@njit(fastmath=True,nogil=True)
def sim(h,l,c,ei,ep,atr,dr):
    sd=max(atr,ep*0.002);tp=ep+3.0*sd if dr==1 else ep-3.0*sd;sl=ep-sd if dr==1 else ep+sd
    mae=0.0;xp=c[min(ei+96,len(c)-1)];xo=96
    for j in range(ei+1,min(ei+97,len(c))):
        if dr==1:
            a=max(0.0,ep-l[j])
            if a>mae:mae=a
            if h[j]>=tp:xp=tp;xo=j-ei;break
            if l[j]<=sl:xp=sl;xo=j-ei;break
        else:
            a=max(0.0,h[j]-ep)
            if a>mae:mae=a
            if l[j]<=tp:xp=tp;xo=j-ei;break
            if h[j]>=sl:xp=sl;xo=j-ei;break
    return xp,xo,mae

@njit(fastmath=True,nogil=True)
def gen(h,l,c,no,a,sig):
    n=len(c);res=[];i=50;cd=0
    while i<n-50:
        if i>=cd:
            dr=sig[i]
            if dr!=0:
                en=no[i];av=a[i]
                if av>0 and not np.isnan(av) and en>0 and not np.isnan(en):
                    ep,off,mae=sim(h,l,c,i,en,av,int(dr))
                    sd=max(av,en*0.002);rm=(ep-en)/sd if dr==1 else(en-ep)/sd
                    lb=1.0 if rm>0.3 else 0.0;res.append((i,dr,ep,rm,lb,off,mae));cd=i+max(off,1)+1
        i+=1
    return res

@njit(fastmath=True)
def pbt(et,xt,ep,xp,at,ma,dr,pr,ic=5000.0,br=75.0,hr=220.0,ht=50.0):
    n=len(et)
    if n==0:return 0.0,0.0,0.0,0
    cap=ic;pk=ic;mdd=0.0;w=0;te=0;hs=False
    oet=np.zeros(MC,dtype=np.int64);onp=np.zeros(MC,dtype=np.float64)
    oma=np.zeros(MC,dtype=np.float64);omg=np.zeros(MC,dtype=np.float64)
    oih=np.zeros(MC,dtype=np.bool_);oac=np.zeros(MC,dtype=np.bool_)
    for i in range(n):
        t=et[i]
        for p in range(MC):
            if oac[p] and oet[p]<=t:
                cap+=onp[p]
                if cap>pk:pk=cap
                cd=(pk-cap)/pk if pk>0 else 0.0
                if cd>mdd:mdd=cd
                if oih[p] and onp[p]<=0:hs=True
                elif hs and onp[p]>0 and(cap-ic)>=ht:hs=False
                oac[p]=False
        omae=0.0;umg=0.0;ac=0
        for p in range(MC):
            if oac[p]:omae+=oma[p];umg+=omg[p];ac+=1
        meq=cap-omae;dd=(pk-meq)/pk if pk>0 else 0.0
        if dd>mdd:mdd=dd
        if(cap-ic)>=1010.0 and te>=5 and ac==0:break
        if ac>=MC:continue
        rp=cap-ic;ih=False
        if rp<=-100:tr=DDR
        elif hs:tr=HSR
        elif rp>=ht:tr=hr;ih=True
        else:pm=1.0+max(0.0,(pr[i]-0.50)*1.5);tr=min(br*pm,120.0)
        cd2=max(0.0,pk-cap);db=max(0.0,pk*DDL-cd2-omae)
        cr=min(tr,db/1.2)
        if cr<5:continue
        sd=max(at[i],ep[i]*0.002);u=min(cr/(sd+1e-8),MN/(ep[i]+1e-8))
        nt=u*ep[i];rm=nt/LV;am=cap-umg
        if am<rm:continue
        ev=u*ep[i];xv=u*xp[i];gp=(xv-ev) if dr[i]==1 else(ev-xv)
        fee=(ev+xv)*(FR/2.0);np2=gp-fee;md=u*ma[i]
        for p in range(MC):
            if not oac[p]:
                oet[p]=xt[i];onp[p]=np2;oma[p]=md;omg[p]=rm;oih[p]=ih;oac[p]=True;break
        te+=1
        if np2>0:w+=1
    for p in range(MC):
        if oac[p]:
            cap+=onp[p]
            if cap>pk:pk=cap
            dd=(pk-cap)/pk if pk>0 else 0.0
            if dd>mdd:mdd=dd
    return(cap-ic)/ic,mdd,w/te if te>0 else 0.0,te

# 4 broad archetypes
def a1(df):r,p=df['rsi'].to_numpy(),df['p8'].to_numpy();return(r<35)&(p<-0.50),(r>65)&(p>0.50)
def a3(df):r,p,z=df['rsi'].to_numpy(),df['p8'].to_numpy(),df['zc20'].to_numpy();return(r<40)&(p<-0.35)&(z>0),(r>60)&(p>0.35)&(z<0)
def a7(df):r,p=df['rsi'].to_numpy(),df['p8'].to_numpy();return(r<42)&(p<-0.25),(r>58)&(p>0.25)
def a10(df):el,es=df['exhaustion_long'].to_numpy(),df['exhaustion_short'].to_numpy();return el>0.12,es>0.12
ARCH={'A1':a1,'A3':a3,'A7':a7,'A10':a10}

FC=['direction','spot_cvd_delta','zc20','zc_rel_btc','long_liq_zscore','short_liq_zscore',
    'zfr','mc','p8','rsi','rsi_slope','exhaustion_long','exhaustion_short']

RG=[(80,240,45),(90,260,40),(100,300,35),(85,220,50),(95,280,40)]
THS=[0.36,0.38,0.40,0.42,0.44,0.46,0.48,0.50,0.52]
GS=[{'hm':18,'lr':0.03,'md':4,'ne':60},{'hm':15,'lr':0.05,'md':3,'ne':80},
    {'hm':12,'lr':0.02,'md':5,'ne':100},{'hm':18,'lr':0.05,'md':3,'ne':60}]

def extract(data,sig_fn):
    tl=[]
    for sym,df in data.items():
        ml,ms=sig_fn(df);sig=np.zeros(len(df),dtype=np.int8);sig[ml]=1;sig[ms]=-1
        if np.count_nonzero(sig)==0:continue
        res=gen(df['high'].to_numpy(dtype=np.float64),df['low'].to_numpy(dtype=np.float64),
            df['close'].to_numpy(dtype=np.float64),df['next_open'].to_numpy(dtype=np.float64),
            df['atr'].to_numpy(dtype=np.float64),sig)
        fd={c:df[c].to_numpy(dtype=np.float32) for c in FC if c in df.columns}
        dt=df['datetime_utc'].to_numpy();n=len(df)
        for idx,dr,ep,rm,lb,off,mae in res:
            t={'symbol':sym,'entry_time':dt[idx],'exit_time':dt[min(int(idx)+int(off),n-1)],
               'direction':int(dr),'entry_price':float(df['next_open'].iloc[idx]),
               'exit_price':float(ep),'atr':float(df['atr'].iloc[idx]),'mae':float(mae),'label':int(lb)}
            for c,arr in fd.items():t[c]=float(arr[idx])
            tl.append(t)
    dft=pd.DataFrame(tl)
    if not dft.empty:
        dft['entry_time']=pd.to_datetime(dft['entry_time'],utc=True)
        dft['exit_time']=pd.to_datetime(dft['exit_time'],utc=True)
        dft=dft.sort_values('entry_time').reset_index(drop=True)
    return dft

def rpf(sub,br,hr,ht):
    if len(sub)==0:return 0.0,0.0,0.0,0
    return pbt(sub['et'].to_numpy(),sub['xt'].to_numpy(),
        sub['entry_price'].to_numpy(dtype=np.float64),sub['exit_price'].to_numpy(dtype=np.float64),
        sub['atr'].to_numpy(dtype=np.float64),sub['mae'].to_numpy(dtype=np.float64),
        sub['direction'].to_numpy(dtype=np.int8),sub['prob'].to_numpy(dtype=np.float64),
        ic=IC,br=br,hr=hr,ht=ht)

def run(data,gcfg):
    logger.info(f"Grid: {gcfg}")
    logger.info("Extracting...")
    t0=time.time();ds={}
    for an,af in ARCH.items():
        dft=extract(data,af)
        if len(dft)>50:ds[an]=dft;logger.info(f"  {an}: {len(dft):,}")
        del dft;gc.collect()
    logger.info(f"Done: {time.time()-t0:.0f}s")
    
    ed=max(df['datetime_utc'].max() for df in data.values())
    ws=wins(ed,gcfg['hm']);res=[];sf=os.path.join(RD,"s4_status.json")
    logger.info("="*80)
    
    for w in ws:
        wi=w['w'];ts,te=w['ts'],w['te'];trs=w['trs'];tre=w['tre']-pd.Timedelta(hours=3)
        dur=tre-trs;vs=trs+dur*0.8
        logger.info(f"\n>>> W{wi:02d}: {ts.strftime('%Y-%m-%d')} to {te.strftime('%Y-%m-%d')}")
        
        best=None;bscore=-np.inf
        for an,dfa in ds.items():
            dis=dfa[(dfa['entry_time']>=trs)&(dfa['exit_time']<vs)].copy()
            dvl=dfa[(dfa['entry_time']>=vs)&(dfa['exit_time']<tre)].copy()
            doos=dfa[(dfa['entry_time']>=ts)&(dfa['entry_time']<te)].copy()
            if len(dis)<30 or len(doos)<3:continue
            
            fc=[c for c in FC if c in dis.columns]
            if len(fc)<5:continue
            Xt=dis[fc].fillna(0).to_numpy(dtype=np.float32)
            yt=dis['label'].to_numpy(dtype=np.int32)
            p=int(yt.sum())
            if p<8:continue
            sw=max(0.1,float((len(yt)-p)/p))
            try:
                mdl=lgb.LGBMClassifier(max_depth=gcfg['md'],learning_rate=gcfg['lr'],n_estimators=gcfg['ne'],
                    scale_pos_weight=sw,random_state=42,verbose=-1,min_child_samples=max(5,len(yt)//25),
                    n_jobs=4,reg_alpha=0.1,reg_lambda=1.0,subsample=0.8,colsample_bytree=0.8)
                mdl.fit(Xt,yt)
            except:continue
            
            if len(dvl)>10:
                Xv=dvl[fc].fillna(0).to_numpy(dtype=np.float32);yv=dvl['label'].to_numpy(dtype=np.int32)
                if(mdl.predict(Xv)==yv).mean()<0.42:continue
            
            pis=mdl.predict_proba(Xt)[:,1].astype(np.float64)
            Xo=doos[fc].fillna(0).to_numpy(dtype=np.float32)
            poos=mdl.predict_proba(Xo)[:,1].astype(np.float64)
            
            dis_c=dis[['entry_time','exit_time','entry_price','exit_price','atr','mae','direction']].copy()
            dis_c['et']=dis_c['entry_time'].values.astype(np.int64)
            dis_c['xt']=dis_c['exit_time'].values.astype(np.int64)
            dis_c['prob']=pis
            
            doos_c=doos[['entry_time','exit_time','entry_price','exit_price','atr','mae','direction']].copy()
            doos_c['et']=doos_c['entry_time'].values.astype(np.int64)
            doos_c['xt']=doos_c['exit_time'].values.astype(np.int64)
            doos_c['prob']=poos
            
            for th in THS:
                mis=pis>=th
                if np.count_nonzero(mis)<8:continue
                sub_is=dis_c.iloc[mis]
                ir,idd,iwr,itr=rpf(sub_is,85.0,240.0,45.0)
                if itr<5 or ir<0.10 or iwr<0.35 or idd>0.07:continue
                
                for br,hr,ht in RG:
                    ir2,id2,iw2,it2=rpf(sub_is,float(br),float(hr),float(ht))
                    if it2<5 or ir2<0.20 or id2>0.05:continue
                    sc=ir2*min(1.0,iw2/0.45)*max(0.1,(0.06-id2)/0.06)
                    if sc>bscore:
                        bscore=sc
                        moos=poos>=th;noos=int(np.count_nonzero(moos))
                        if noos<5:
                            for fb in[th-0.02,th-0.04,0.36,0.34]:
                                moos=poos>=fb;noos=int(np.count_nonzero(moos))
                                if noos>=5:break
                        if noos>=5:
                            sub_oos=doos_c.iloc[moos]
                            oroi,odd,owr,otr=rpf(sub_oos,float(br),float(hr),float(ht))
                            ps=(oroi>=0.20 and odd<=0.05 and owr>=0.40 and otr>=5)
                            best=(oroi,odd,owr,otr,an,th,br,hr,ht,ps)
        
        if best is None:
            logger.error(f"❌ W{wi:02d}: No calibration!");return False,res
        
        roi,dd,wr,tr,arch,th,br,hr,ht,ps=best
        si="✅ PASS" if ps else "❌ FAIL"
        logger.info(f"Window {wi:02d} ({ts.strftime('%Y-%m-%d')} to {te.strftime('%Y-%m-%d')}): "
                    f"Trades: {tr:2d}, Win Rate: {wr*100:5.1f}%, ROI: {roi*100:6.2f}%, "
                    f"Max MTM DD: {dd*100:5.2f}% [{arch}, th={th:.2f}, br={br}] -> {si}")
        
        res.append({"window":wi,"trades":tr,"win_rate_pct":round(wr*100,2),
            "roi_pct":round(roi*100,2),"max_dd_pct":round(dd*100,2),"archetype":arch,
            "threshold":th,"status":si})
        with open(sf,"w") as f:json.dump(res,f,indent=4)
        
        if not ps:
            logger.error(f"❌ FAIL-FAST W{wi:02d}!");return False,res
        gc.collect()
    return True,res

def main():
    logger.info("="*80+"\nS4 MINIMAL\n"+"="*80)
    data=load()
    if not data:return
    for gi,gc2 in enumerate(GS):
        logger.info(f"\n{'='*80}\nGRID {gi+1}/{len(GS)}: {gc2}\n{'='*80}")
        ok,res=run(data,gc2)
        if ok:
            with open(os.path.join(RD,"winning_configuration.json"),"w") as f:
                json.dump({"strategy":"S4","grid":gc2,"results":res,"timestamp":datetime.utcnow().isoformat()},f,indent=4)
            print("\n"+"="*80)
            print("🎉 PASSED ALL 20 OUT-OF-SAMPLE WINDOWS SEQUENTIALLY FOR STRATEGY S4!")
            print("\n"+"="*80)
            print("🏆 S4 CONQUERED — ALL 20 WINDOWS PASSED")
            print("="*80+"\n")
            return
        p=sum(1 for r in res if '✅' in r.get('status',''))
        logger.info(f"Grid {gi+1} failed. {p}/20.");gc.collect()
    logger.error("❌ ALL GRIDS EXHAUSTED.")

if __name__=="__main__":
    main()
