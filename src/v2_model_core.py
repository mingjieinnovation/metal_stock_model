from __future__ import annotations
import numpy as np
import pandas as pd

VERSION='v2_fundamental_valuation_model'
_WINDOWS = {'daily': (63, 252, 756), 'weekly': (13, 52, 156), 'monthly': (3, 12, 36)}

def rolling_score(s, w): return s.rolling(w, min_periods=max(3, w // 4)).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)
def trend_score(s, short, long): return np.where(s.rolling(short, min_periods=short).mean() >= s.rolling(long, min_periods=long).mean(), .7, .3)
def signal(g): return np.where(g < -.12, 'undervalued', np.where(g > .12, 'overvalued', 'neutral'))
def _score(frame, name, default): return pd.to_numeric(frame.get(name, pd.Series(default, index=frame.index)), errors='coerce').fillna(default)

def chalco_demand(d, frequency='monthly'):
    short, long, score_window = _WINDOWS[frequency]; d=d.copy()
    d['inventory_score']=_score(d,'inventory_score',.5); d['grid_proxy_score']=_score(d,'grid_proxy_score',.55); d['nev_proxy_score']=_score(d,'nev_proxy_score',.55); d['property_proxy_score']=_score(d,'property_proxy_score',.45)
    d['al_price_trend_score']=trend_score(d.al_price,short,long); d['al_spread_score']=rolling_score(d.al_spread,score_window); d['pmi_score']=rolling_score(d.pmi,score_window).fillna(.5)
    d['demand_score']=.25*d.inventory_score+.2*d.al_price_trend_score+.15*d.al_spread_score.fillna(.5)+.15*d.grid_proxy_score+.1*d.nev_proxy_score+.1*d.pmi_score+.05*d.property_proxy_score
    return d

def zijin_demand(d, frequency='monthly'):
    short,long,score_window=_WINDOWS[frequency]; d=d.copy()
    d['cu_inventory_score']=_score(d,'cu_inventory_score',.5);d['power_grid_proxy_score']=_score(d,'power_grid_proxy_score',.55);d['risk_score']=_score(d,'risk_score',.5);d['real_rate_score']=_score(d,'real_rate_score',.5);d['central_bank_gold_proxy_score']=_score(d,'central_bank_gold_proxy_score',.6);d['gold_etf_proxy_score']=_score(d,'gold_etf_proxy_score',.55);d['usd_score']=_score(d,'usd_score',.5)
    d['cu_price_trend_score']=trend_score(d.cu_price,short,long);d['pmi_score']=rolling_score(d.pmi,score_window).fillna(.5)
    d['cu_demand_score']=.25*d.cu_inventory_score+.25*d.cu_price_trend_score+.2*d.power_grid_proxy_score+.15*d.pmi_score+.15*d.risk_score
    d['au_demand_score']=.3*d.real_rate_score+.25*d.central_bank_gold_proxy_score+.2*d.gold_etf_proxy_score+.15*d.usd_score+.1*d.risk_score
    d['demand_score']=.65*d.cu_demand_score+.35*d.au_demand_score;return d
