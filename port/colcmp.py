import json, sys, numpy as np
from ztrender import State
TB=0x12EF26
def game_cols(jf):
    """final (topmost) draw per column: (h, top tid, top col, bot tid, bot col)"""
    out={}
    for r in json.load(open(jf)):
        d=r[:8]; a=r[8:]
        col=((a[4]&0xFFFFFF)-0xFF6126)//2
        h=(d[2]>>8)&0xFFFF
        if h>=0x8000: continue
        t1=(a[1]&0xFFFFFF)-TB; t2=(a[2]&0xFFFFFF)-TB
        prev=out.get(col)
        if prev is None or h>=prev[0]: out[col]=(h, t1//512, (t1%512)//32, t2//512, (t2%512)//32)
    return out
if __name__=="__main__":
    out=game_cols(sys.argv[1])
    for c in sorted(out)[:: max(1,len(out)//16)]: print(c, out[c])
