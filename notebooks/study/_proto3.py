import numpy as np
from scipy.special import expit, ndtr
CUTS=(0.15,0.6); TAU=0.25
def make_region(seed, U=60, M=400, flood_shift=0.0, bias_shift=0.0, road_effect=0.9):
    r=np.random.default_rng(seed)
    unit=np.repeat(np.arange(U),M); road=r.exponential(1.0,U*M); near=np.exp(-road/0.6)
    a=r.normal(-1.6+flood_shift,0.8,U)
    y=(r.random(U*M)<expit(a[unit]+r.normal(0,1.3,U*M)-road_effect*near)).astype(float)
    z=(2*y-1)*1.3+bias_shift+r.normal(0,0.5,U)[unit]+r.normal(0,1.0,U*M)+0.9*near
    f=expit(z)
    return dict(U=U,unit=unit,road=road,y=y,f=f,h=np.searchsorted(CUTS,f,side="right"))
def truth(reg): return np.bincount(reg["unit"],weights=reg["y"])/np.bincount(reg["unit"])
def prep(reg):
    U=reg["U"]; g=reg["unit"]*3+reg["h"]; n=np.bincount(reg["unit"])
    W=np.bincount(g,minlength=U*3).reshape(U,3)/n[:,None]
    Fs=np.bincount(g,weights=reg["f"],minlength=U*3); cnt=np.bincount(g,minlength=U*3)
    Fb=np.where(cnt>0,Fs/np.maximum(cnt,1),0).reshape(U,3)
    reg.update(g=g,W=W,Fb=Fb,theta_map=np.bincount(reg["unit"],weights=reg["f"])/n)
def fit_Rpool(reg):
    e=reg["y"]-reg["f"]; return np.array([e[reg["h"]==j].mean() for j in range(3)])
def draw(reg,b,rng,design):
    U=reg["U"]; unit=reg["unit"]
    if b==0: return np.zeros(0,int),np.zeros(0)
    a=np.ones(len(unit)) if design=="random" else 0.05+np.exp(-reg["road"]/0.6)
    asum=np.bincount(unit,weights=a,minlength=U)
    pi=np.clip(b*a/asum[unit],0,1); sel=rng.random(len(unit))<pi
    return np.flatnonzero(sel),pi[sel]
def est(reg,idx,pi,Rpool,m=1.0,weighted=True):
    U=reg["U"]; e=(reg["y"]-reg["f"])[idx]; g=reg["g"][idx]
    a=(1/pi if weighted else np.ones(len(idx)))
    S=np.bincount(g,weights=a,minlength=U*3); S2=np.bincount(g,weights=a*a,minlength=U*3)
    R=np.bincount(g,weights=a*e,minlength=U*3)/np.maximum(S,1e-300)
    neff=np.where(S2>0,S*S/np.maximum(S2,1e-300),0)
    lam=(neff/(neff+m)).reshape(U,3); R=R.reshape(U,3)
    Rt=lam*R+(1-lam)*Rpool[None,:]
    return np.clip((reg["W"]*(reg["Fb"]+Rt)).sum(1),0,1)
def est_sample(reg,idx,pi,prior):
    U=reg["U"]; u=reg["unit"][idx]; a=1/pi
    S=np.bincount(u,weights=a,minlength=U); R=np.bincount(u,weights=a*reg["y"][idx],minlength=U)/np.maximum(S,1e-300)
    return np.where(S>0,R,prior)
tr=make_region(1,U=100,flood_shift=0.0,bias_shift=0.0); prep(tr); Rpool=fit_Rpool(tr); print("Rpool",Rpool.round(3))
# new region: different flood level and map bias (map over-reads more)
for design in ("random","route"):
    nr=make_region(2,U=60,flood_shift=0.3,bias_shift=-0.6); prep(nr); T=truth(nr)
    print("\n",design,"| truth mean %.3f, map mean %.3f, units above 25%%: %.2f"%(T.mean(),nr["theta_map"].mean(),(T>TAU).mean()))
    for b in (0,4,8,16,32,64):
        rng=np.random.default_rng(10+b); out={k:[] for k in("map","sample","ppi_naive","ppi_ipw")}
        for _ in range(60):
            idx,pi=draw(nr,b,rng,design)
            out["map"].append(nr["theta_map"]); out["sample"].append(est_sample(nr,idx,pi,tr["y"].mean()))
            out["ppi_naive"].append(est(nr,idx,pi,Rpool,weighted=False)); out["ppi_ipw"].append(est(nr,idx,pi,Rpool))
        row=[]
        for k,v in out.items():
            v=np.array(v); err=v-T[None]; row.append("%s bias %+.3f rmse %.3f wrong %.3f"%(k,err.mean(),np.sqrt((err**2).mean()),((v>TAU)!=(T>TAU)[None]).mean()))
        print(b," | ".join(row))
