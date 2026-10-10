import numpy as np, sys
from PIL import Image
from ztrender import State, render, game_fb
# palette from screenshot correspondence
def palette(ram, shot):
    g=game_fb(ram); im=Image.open(shot).convert('RGB'); pal={}
    for y in range(80):
        for x in range(256): pal.setdefault(g[y,x],{}).setdefault(im.getpixel((32+x,40+y)),0); pal[g[y,x]][im.getpixel((32+x,40+y))]+=1
    out=np.zeros((16,3),np.uint8)
    for i,d in pal.items(): out[i]=max(d,key=d.get)
    return out
files=sys.argv[2:]; kw=eval(sys.argv[1])
rows=[]
P=np.zeros((16,3),np.uint8)
for f in files:
    p=palette(open(f,'rb').read(), f.replace('.bin','.png'))
    for i in range(16):
        if p[i].any(): P[i]=p[i]
for f in files:
    ram=open(f,'rb').read(); g=game_fb(ram); img,mask=render(State(ram),**kw)
    diff=np.where(mask, np.where(img==g, 0, 255), 64).astype(np.uint8)
    row=np.concatenate([P[g],np.full((80,3,3),255,np.uint8),P[img],np.full((80,3,3),255,np.uint8),np.stack([diff]*3,-1)],1)
    rows+= [row, np.full((3,row.shape[1],3),128,np.uint8)]
Image.fromarray(np.concatenate(rows)).resize((row.shape[1]*2, sum(r.shape[0] for r in rows)*2), Image.NEAREST).save('images/cmp.png')
