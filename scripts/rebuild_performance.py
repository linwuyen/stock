#!/usr/bin/env python3
import argparse,json
from datetime import date,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
H=[1,4,13,26,52]

def load(p):return json.loads((ROOT/p).read_text())
def price(snapshot,ticker):
    if ticker=='2330':
        b=snapshot.get('benchmark_asset') or snapshot.get('benchmark') or snapshot.get('tsmc') or {}
        return b.get('reference_price')
    s=next((x for x in snapshot.get('stocks',[]) if x.get('ticker')==ticker),None)
    return None if not s else s.get('reference_price')

def nearest(snaps,target,max_days=5):
    pairs=[(abs((date.fromisoformat(s['meta']['as_of'])-target).days),s) for s in snaps]
    if not pairs:return None
    d,s=min(pairs,key=lambda x:x[0]);return s if d<=max_days else None

def build():
    idx=load(Path('data/history/index.json')); snaps=[load(Path(e['path'])) for e in idx['snapshots']]; snaps.sort(key=lambda s:s['meta']['as_of'])
    samples={w:[] for w in H}
    for entry in snaps:
        d0=date.fromisoformat(entry['meta']['as_of']); b0=price(entry,'2330')
        if not b0:continue
        for s in entry.get('stocks',[]):
            if not (s.get('grade')=='A' or s.get('action')=='BUY CANDIDATE'):continue
            p0=s.get('reference_price')
            if not p0:continue
            for w in H:
                end=nearest(snaps,d0+timedelta(weeks=w))
                if not end:continue
                p1=price(end,s['ticker']);b1=price(end,'2330')
                if p1 and b1:samples[w].append((p1/p0-1-(b1/b0-1))*100)
    out=load(Path('data/performance.json'))
    for h in out['horizons']:
        arr=samples[h['weeks']];h['sample_size']=len(arr);h['mean_excess_return_pct']=round(sum(arr)/len(arr),2) if arr else None
    total=max((x['sample_size'] for x in out['horizons']),default=0);out['meta']['status']='CALIBRATED' if total>=out['minimum_samples_for_calibration'] else 'INSUFFICIENT_HISTORY';out['meta']['as_of']=idx['latest'];return out
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');a=ap.parse_args();built=build();path=ROOT/'data/performance.json'
    if a.check:
        current=json.loads(path.read_text());assert current==built,'performance.json is stale; run rebuild_performance.py';print('performance PASS')
    else:path.write_text(json.dumps(built,ensure_ascii=False,indent=2)+"\n");print(path)
