import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt, numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle, Polygon, FancyArrowPatch, Ellipse
plt.rcParams['font.family']='Liberation Serif'
NAVY='#1d2b53'; FL='#2f7fc1'; UN='#f2b84b'; DR='#7bb661'; RED='#c0392b'
fig,ax=plt.subplots(figsize=(8.2,8.8),dpi=220)
ax.set_xlim(0,100);ax.set_ylim(0,107);ax.axis('off');ax.set_aspect('equal')
def rbox(x,y,w,h,fc,ec=NAVY,lw=1.3,r=1.8,z=1,alpha=1):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle=f"round,pad=0,rounding_size={r}",fc=fc,ec=ec,lw=lw,zorder=z,alpha=alpha))
def band(y,h,fc,n,title,sub,sx=0):
    rbox(1.5,y,97,h,fc,lw=1.4,r=2.5)
    ax.add_patch(Circle((6.2,y+h-4.2),2.6,fc=NAVY,zorder=3))
    ax.text(6.2,y+h-4.25,str(n),ha='center',va='center',color='white',fontsize=15,fontweight='bold',zorder=4)
    ax.text(10.5,y+h-4.2,title,ha='left',va='center',fontsize=15.5,fontweight='bold',color=NAVY,zorder=4)
    ax.text(sx,y+h-4.35,sub,ha='left',va='center',fontsize=12.5,style='italic',color='#333',zorder=4)
def arrow(x1,y1,x2,y2,c=NAVY,lw=2.2,ms=18):
    ax.add_patch(FancyArrowPatch((x1,y1),(x2,y2),arrowstyle='-|>',mutation_scale=ms,lw=lw,color=c,zorder=6))
# flood field (10x6), deterministic
rng=np.random.RandomState(4)
cols,rows=10,6
P=np.zeros((rows,cols))
for r in range(rows):
    for c in range(cols):
        d=abs(c-(3.2+0.55*r))   # river-like diagonal
        P[r,c]=np.clip(1.15-d/2.6+rng.normal(0,0.12),0,1)
cls=np.where(P>0.65,2,np.where(P>0.35,1,0))   # 2 flooded, 1 unsure, 0 dry
colmap={2:FL,1:UN,0:DR}
def grid(x0,y0,cw,ch,sample=None,z=3):
    for r in range(rows):
        for c in range(cols):
            ax.add_patch(Rectangle((x0+c*cw,y0+(rows-1-r)*ch),cw,ch,fc=colmap[cls[r,c]],ec='white',lw=1.1,zorder=z))
            if sample is not None and sample[r,c]:
                ax.add_patch(Circle((x0+c*cw+cw/2,y0+(rows-1-r)*ch+ch/2),min(cw,ch)*0.36,fc='white',ec='black',lw=1.6,zorder=z+1))
                ax.add_patch(Circle((x0+c*cw+cw/2,y0+(rows-1-r)*ch+ch/2),min(cw,ch)*0.13,fc='black',zorder=z+2))
    ax.add_patch(Rectangle((x0,y0),cols*cw,rows*ch,fc='none',ec=NAVY,lw=1.6,zorder=z+3))
# ---------- band 1 MAP ----------
band(72,34,'#fff4d6',1,'MAP','the satellite guesses',24)
# satellite
sx,sy=18,91.5
ax.add_patch(Rectangle((sx-3,sy-2.5),6,5,fc='#cfd8e8',ec=NAVY,lw=1.5,zorder=4))
for dx in (-12,6.5):
    ax.add_patch(Rectangle((sx+dx,sy-1.8),5.6,3.6,fc='#3a5ba0',ec=NAVY,lw=1.2,zorder=4))
    for k in range(1,3): ax.plot([sx+dx+k*1.87]*2,[sy-1.8,sy+1.8],color='white',lw=0.8,zorder=5)
ax.plot([sx,sx],[sy+2.5,sy+5],color=NAVY,lw=1.5,zorder=4); ax.add_patch(Circle((sx,sy+5.4),0.9,fc=RED,ec=NAVY,zorder=4))
# beam
ax.add_patch(Polygon([[sx-1.5,sy-2.5],[sx+1.5,sy-2.5],[46,77.5],[46,95.5]],closed=True,fc='#8fc1ea',alpha=0.45,ec='none',zorder=2))
ax.text(sx,sy-5.0,'Sentinel-1 radar sees\nthrough clouds',ha='center',va='top',fontsize=11,color=NAVY)
# cloud
for dx,dy,r in [(-3,0,1.9),(0,0.8,2.4),(3,0,1.9)]:
    ax.add_patch(Circle((27+dx,98.2+dy-1.2),r,fc='#e6e9ef',ec='#b9c0cf',lw=0.8,zorder=3))
# chips: terrain / paddy mask
rbox(5,75.0,26,4.6,'white',lw=1,r=1,z=4); ax.text(18,77.3,'+ terrain & paddy mask',ha='center',va='center',fontsize=10.5,color=NAVY,zorder=5)
grid(46,75.5,4.6,3.15)
ax.text(69,72.8,'',fontsize=1)
# legend
lx=47.5
for lab,c in [('flooded',FL),('unsure',UN),('dry',DR)]:
    ax.add_patch(Rectangle((lx,73.0),2.2,1.8,fc=c,ec='white',zorder=5)); ax.text(lx+3,73.9,lab,va='center',fontsize=10.5,color='#222'); lx+=15
ax.text(5,73.9,'each square = one paddy plot',ha='left',va='center',fontsize=10,style='italic',color='#333')
arrow(50,72.2,50,69.8)
# ---------- band 2 CHECK ----------
band(36,34,'#e3f4e4',2,'CHECK','a few people check',31)
samp=np.zeros((rows,cols),bool)
picks=[(0,3),(1,2),(1,6),(2,1),(2,4),(2,7),(3,3),(3,5),(4,2),(4,8),(5,1),(5,6),(1,4),(3,8)]
for r,c in picks: samp[r,c]=True
grid(4.5,41.0,3.9,2.9,sample=samp)
ax.text(24,39.9,'visit a random few plots in each colour group',ha='center',va='top',fontsize=10.5,style='italic',color='#222')
# person
px,py=49,47
ax.add_patch(Circle((px,py+8.2),1.7,fc='#f0c9a0',ec=NAVY,lw=1.2,zorder=5))
ax.add_patch(Polygon([[px-3,py],[px+3,py],[px+2.2,py+6.2],[px-2.2,py+6.2]],closed=True,fc='#e8793a',ec=NAVY,lw=1.2,zorder=5))
ax.add_patch(Rectangle((px+1.6,py+1.2),3.6,4.6,fc='white',ec=NAVY,lw=1.1,zorder=6))
for k in range(3): ax.plot([px+2.2,px+4.6],[py+2.2+k*1.1]*2,color=NAVY,lw=0.8,zorder=7)
arrow(55,49,58,49,lw=2.0,ms=14)
# chart
cx0,cy0,cw,ch=61,44,35,19
ax.add_patch(Rectangle((cx0-2,cy0-6.3),cw+3.5,ch+9.3,fc='white',ec='#9aa7bb',lw=1,zorder=3))
ymin,ymax=15,45
def yv(v): return cy0+(v-ymin)/(ymax-ymin)*ch
ax.plot([cx0+5,cx0+5],[cy0,cy0+ch],color='#555',lw=1,zorder=4)
for v in (20,30,40):
    ax.plot([cx0+4,cx0+5],[yv(v)]*2,color='#555',lw=1,zorder=4); ax.text(cx0+3.2,yv(v),f'{v}%',ha='right',va='center',fontsize=9.5,color='#333',zorder=4)
ax.plot([cx0+5,cx0+cw],[yv(25)]*2,color=RED,lw=1.8,ls=(0,(4,3)),zorder=5)
ax.text(cx0+cw-0.5,yv(25)+0.5,'25% line',ha='right',va='bottom',fontsize=10.5,color=RED,fontweight='bold',zorder=6)
# raw map bar
ax.add_patch(Rectangle((cx0+5,yv(ymin)),8,yv(30)-yv(ymin),fc='#b9c0cf',ec=NAVY,lw=1.1,zorder=4))
ax.text(cx0+9,yv(ymin)-0.6,'map count\n30%',ha='center',va='top',fontsize=10,color='#222',zorder=4)
# corrected bar + interval
ax.add_patch(Rectangle((cx0+15,yv(ymin)),8,yv(34)-yv(ymin),fc=FL,ec=NAVY,lw=1.1,zorder=4))
xe=cx0+19
ax.plot([xe,xe],[yv(28.1),yv(39.9)],color='black',lw=2,zorder=6)
for v in (28.1,39.9): ax.plot([xe-2,xe+2],[yv(v)]*2,color='black',lw=2,zorder=6)
ax.text(xe,yv(ymin)-0.6,'corrected\n34% ± 6',ha='center',va='top',fontsize=10,fontweight='bold',color=NAVY,zorder=4)
ax.text(cx0+cw/2+0.5,cy0+ch+1.4,'whole interval is above the line',ha='center',va='center',fontsize=10,color=NAVY,style='italic',zorder=6)
arrow(50,36.2,50,33.8)
# ---------- band 3 TOOL ----------
band(2,32,'#f1e6f6',3,'TOOL','the officer decides and plans',24)
def screen(x,y,w=15,h=13):
    rbox(x,y,w,h,'white',lw=1.2,r=1,z=4)
    ax.add_patch(Rectangle((x,y+h-2.2),w,2.2,fc=NAVY,ec=NAVY,zorder=5))
    for k in range(3): ax.add_patch(Circle((x+1.5+k*1.6,y+h-1.1),0.4,fc='white',zorder=6))
xs=[4.5,23.0,41.5,60.0,78.5]
labs=['Event board','Village triage','Survey plan','Field entry','Village dossier']
for x,l in zip(xs,labs):
    screen(x,8.5); ax.text(x+7.5,6.8,l,ha='center',va='top',fontsize=11.5,fontweight='bold',color=NAVY)
# 1 board: map blob + pins
x=xs[0]; ax.add_patch(Polygon([[x+2,y0] for y0 in [10.5]]+[[x+5,9.8],[x+11,10.4],[x+13.2,13.5],[x+11,17.5],[x+6,18.3],[x+2.6,15.5]],closed=True,fc='#cfe6f7',ec=FL,lw=1,zorder=5))
for (a,b,c) in [(6,13.5,RED),(9.5,15.5,UN),(10.5,12,DR)]: ax.add_patch(Circle((x+a,b),0.95,fc=c,ec=NAVY,lw=0.8,zorder=6))
# 2 triage rows
x=xs[1]
for k,(c,wd) in enumerate([(RED,9),(UN,6.5),(DR,4)]):
    yy=17.2-k*3.0; ax.add_patch(Circle((x+2.4,yy),0.95,fc=c,ec=NAVY,lw=0.8,zorder=6)); ax.add_patch(Rectangle((x+4.4,yy-0.55),wd,1.1,fc='#c8cfdd',zorder=6))
# 3 checklist
x=xs[2]
for k in range(3):
    yy=17.2-k*3.0; ax.add_patch(Rectangle((x+2,yy-0.9),1.8,1.8,fc='white',ec=NAVY,lw=0.9,zorder=6))
    if k<2: ax.plot([x+2.3,x+2.8,x+3.5],[yy,yy-0.6,yy+0.7],color=DR,lw=1.5,zorder=7)
    ax.add_patch(Rectangle((x+5,yy-0.55),7.5,1.1,fc='#c8cfdd',zorder=6))
# 4 phone w/ yes/no
x=xs[3]
ax.add_patch(Rectangle((x+1.5,10.2),12,7.2,fc='#eef1f7',ec='none',zorder=5))
ax.text(x+7.5,16.0,'Plot 17: flooded?',ha='center',va='center',fontsize=9.5,color=NAVY,zorder=7)
rbox(x+2.5,11.0,4.8,3.2,DR,ec=NAVY,lw=0.8,r=0.6,z=6); ax.text(x+4.9,12.6,'Yes',ha='center',va='center',fontsize=10,color='white',fontweight='bold',zorder=7)
rbox(x+8.0,11.0,4.8,3.2,RED,ec=NAVY,lw=0.8,r=0.6,z=6); ax.text(x+10.4,12.6,'No',ha='center',va='center',fontsize=10,color='white',fontweight='bold',zorder=7)
# 5 dossier: mini interval + lines
x=xs[4]
ax.add_patch(Rectangle((x+2,10.0),4.2,5.4,fc=FL,zorder=6)); ax.plot([x+4.1]*2,[13.5,17.3],color='black',lw=1.4,zorder=7)
ax.plot([x+1.5,x+9],[14.2]*2,color=RED,lw=1,ls=(0,(3,2)),zorder=7)
for k in range(3): ax.add_patch(Rectangle((x+8,16.3-k*2.3),5,0.9,fc='#c8cfdd',zorder=6))
# arrows between screens
for a,b in zip(xs[:-1],xs[1:]): arrow(a+15.4,15,b-0.4,15,lw=1.4,ms=11)
fig.savefig('fig_arch.png',bbox_inches='tight',pad_inches=0.05,facecolor='white')
print(fig.get_size_inches())
