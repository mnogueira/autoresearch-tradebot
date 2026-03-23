"""test_ensemble.py — Regime-switching ensemble: trend + mean-reversion."""
import numpy as np, pandas as pd, ta

from ..prepare import load_data, split_data, add_session_markers
from ..sweep_params import fast_backtest

def rolling_hurst(close, window=100):
    def hurst_rs(series):
        ts=np.array(series); returns=np.diff(ts)/ts[:-1]
        if len(returns)<10: return 0.5
        mean_r=returns.mean(); deviate=np.cumsum(returns-mean_r)
        r=deviate.max()-deviate.min(); s=returns.std(ddof=1)
        if s==0 or r==0: return 0.5
        return np.log(r/s)/np.log(len(returns))
    return close.rolling(window).apply(hurst_rs, raw=True)

def gen_ensemble(df, mr_rsi_long=30, mr_rsi_short=70, mr_rsi_exit=50,
                 mr_bb_std=2.0, mr_type='rsi_bounce'):
    ema8=ta.trend.ema_indicator(df['Close'],window=8)
    ema34=ta.trend.ema_indicator(df['Close'],window=34)
    ema220=ta.trend.ema_indicator(df['Close'],window=220)
    rsi7=ta.momentum.rsi(df['Close'],window=7)
    rsi14=ta.momentum.rsi(df['Close'],window=14)
    adx14=ta.trend.adx(df['High'],df['Low'],df['Close'],window=14)
    atr20=ta.volatility.average_true_range(df['High'],df['Low'],df['Close'],window=20)
    trix12=ta.trend.trix(df['Close'],window=12)
    hurst=rolling_hurst(df['Close'],window=100)
    trix_med=trix12.rolling(500,min_periods=100).median().shift(1)
    ret=df['Close'].pct_change()
    vr=ret.rolling(3).std()/ret.rolling(20).std()
    typical=(df['High']+df['Low']+df['Close'])/3
    cum_tp=(typical*df['Volume']).groupby(df.index.date).cumsum()
    cum_v=df['Volume'].groupby(df.index.date).cumsum().replace(0,np.nan)
    vwap=cum_tp/cum_v
    bb_mid=df['Close'].rolling(20).mean()
    bb_std_v=df['Close'].rolling(20).std()
    bb_upper=bb_mid+mr_bb_std*bb_std_v
    bb_lower=bb_mid-mr_bb_std*bb_std_v

    c=df['Close'].values;e8=ema8.values;e34=ema34.values;rv7=rsi7.values;rv14=rsi14.values
    tv=ema220.values;av=adx14.values;at_=atr20.values;txv=trix12.values;tmv=trix_med.values
    hv=hurst.values;vrv=vr.values;vwv=vwap.values;bbu=bb_upper.values;bbl=bb_lower.values
    il=df['is_last_30min'].values;ib=df['is_first_bar'].values
    dates=df['date'].values;times=df['time'].values

    sig=np.zeros(len(df),dtype=np.int64);pos=0;pd2=None;pk=0.0;etype=None

    for i in range(len(df)):
        d=dates[i]
        if ib[i] or d!=pd2: pos=0;pd2=d;etype=None;continue
        if il[i]: sig[i]=0;pos=0;pd2=d;continue
        if np.isnan(at_[i]): sig[i]=pos;pd2=d;continue
        h=hv[i] if not np.isnan(hv[i]) else 0.5
        trending = h >= 0.50

        if pos!=0:
            ca=at_[i] if not np.isnan(at_[i]) else 0
            if etype=='trend':
                tm=tmv[i] if not np.isnan(tmv[i]) else 0
                fv=txv[i] if not np.isnan(txv[i]) else tm
                fp=txv[i-1] if i>0 and not np.isnan(txv[i-1]) else tm
                te=(pos==1 and fv<tm and fp>=tm) or (pos==-1 and fv>tm and fp<=tm)
                if te: sig[i]=0;pos=0;etype=None
                elif pos==1:
                    pk=max(pk,c[i])
                    if ca>0 and c[i]<pk-2*ca: sig[i]=0;pos=0;etype=None
                    else: sig[i]=pos
                elif pos==-1:
                    pk=min(pk,c[i])
                    if ca>0 and c[i]>pk+2*ca: sig[i]=0;pos=0;etype=None
                    else: sig[i]=pos
            elif etype=='mr':
                r14=rv14[i] if not np.isnan(rv14[i]) else 50
                mr_exit=(pos==1 and r14>mr_rsi_exit) or (pos==-1 and r14<mr_rsi_exit)
                if mr_exit: sig[i]=0;pos=0;etype=None
                elif pos==1:
                    pk=max(pk,c[i])
                    if ca>0 and c[i]<pk-1.5*ca: sig[i]=0;pos=0;etype=None
                    else: sig[i]=pos
                elif pos==-1:
                    pk=min(pk,c[i])
                    if ca>0 and c[i]>pk+1.5*ca: sig[i]=0;pos=0;etype=None
                    else: sig[i]=pos
            pd2=d;continue

        ct=times[i]
        if hasattr(ct,'hour') and ct.hour in (12,13): pd2=d;continue
        if hasattr(ct,'hour') and (ct.hour>14 or (ct.hour==14 and ct.minute>=55)): pd2=d;continue

        if trending:
            if np.isnan(e8[i]) or np.isnan(e34[i]) or np.isnan(tv[i]): pd2=d;continue
            if av[i]<20: pd2=d;continue
            v=vrv[i]
            if not np.isnan(v) and v>2.0: pd2=d;continue
            r=rv7[i] if not np.isnan(rv7[i]) else 50
            vw=vwv[i] if not np.isnan(vwv[i]) else c[i]
            if i>0 and not np.isnan(e8[i-1]) and not np.isnan(e34[i-1]):
                cu=e8[i]>e34[i] and e8[i-1]<=e34[i-1]
                cd=e8[i]<e34[i] and e8[i-1]>=e34[i-1]
                if cu and c[i]>tv[i] and r>65 and c[i]>vw:
                    sig[i]=1;pos=1;pk=c[i];etype='trend'
                elif cd and c[i]<tv[i] and r<40 and c[i]<vw:
                    sig[i]=-1;pos=-1;pk=c[i];etype='trend'
        else:
            r14=rv14[i] if not np.isnan(rv14[i]) else 50
            if mr_type=='rsi_bounce':
                if r14<mr_rsi_long and not np.isnan(bbl[i]) and c[i]<=bbl[i]:
                    sig[i]=1;pos=1;pk=c[i];etype='mr'
                elif r14>mr_rsi_short and not np.isnan(bbu[i]) and c[i]>=bbu[i]:
                    sig[i]=-1;pos=-1;pk=c[i];etype='mr'
            elif mr_type=='rsi_cross':
                if i>0 and not np.isnan(rv14[i-1]):
                    if rv14[i-1]<mr_rsi_long and r14>=mr_rsi_long:
                        sig[i]=1;pos=1;pk=c[i];etype='mr'
                    elif rv14[i-1]>mr_rsi_short and r14<=mr_rsi_short:
                        sig[i]=-1;pos=-1;pk=c[i];etype='mr'
        pd2=d

    signals=pd.Series(sig,index=df.index)
    signals=signals.groupby(df['date']).shift(1).fillna(0).astype(int)
    return signals

def main():
    df=load_data()
    train_df,test_df=split_data(df,train_ratio=0.70)
    train_df=add_session_markers(train_df);test_df=add_session_markers(test_df)

    configs=[
        ('RSI bounce 30/70 BB2', dict(mr_rsi_long=30,mr_rsi_short=70,mr_bb_std=2.0)),
        ('RSI bounce 25/75 BB2', dict(mr_rsi_long=25,mr_rsi_short=75,mr_bb_std=2.0)),
        ('RSI bounce 20/80 BB2', dict(mr_rsi_long=20,mr_rsi_short=80,mr_bb_std=2.0)),
        ('RSI bounce 30/70 BB2.5', dict(mr_rsi_long=30,mr_rsi_short=70,mr_bb_std=2.5)),
        ('RSI bounce 35/65 BB1.5', dict(mr_rsi_long=35,mr_rsi_short=65,mr_bb_std=1.5)),
        ('RSI cross 30/70', dict(mr_rsi_long=30,mr_rsi_short=70,mr_type='rsi_cross')),
        ('RSI cross 25/75', dict(mr_rsi_long=25,mr_rsi_short=75,mr_type='rsi_cross')),
        ('RSI cross 20/80', dict(mr_rsi_long=20,mr_rsi_short=80,mr_type='rsi_cross')),
        ('RSI bounce 30/70 exit55', dict(mr_rsi_long=30,mr_rsi_short=70,mr_rsi_exit=55)),
        ('RSI bounce 30/70 exit45', dict(mr_rsi_long=30,mr_rsi_short=70,mr_rsi_exit=45)),
    ]

    print(f"{'Config':<30} {'test':>8} {'train':>8} {'PF':>6} {'n':>4} {'net':>8}")
    print('-'*70)
    for name, kw in configs:
        sig_tr=gen_ensemble(train_df,**kw);sig_te=gen_ensemble(test_df,**kw)
        tr=fast_backtest(train_df,sig_tr);te=fast_backtest(test_df,sig_te)
        both='OK' if tr[0]>0 and te[0]>0 else 'FAIL'
        beat='***' if te[0]>3.56 and tr[0]>0 and te[3]>=50 else ''
        print(f'  {name:<28} {te[0]:>8.4f} {tr[0]:>8.4f} {te[1]:>6.2f} {te[3]:>4} {te[4]:>8.0f} [{both}] {beat}')

if __name__=='__main__':
    main()
