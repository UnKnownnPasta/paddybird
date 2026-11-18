import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch
plt.rcParams['font.family'] = 'Times New Roman'
NAVY = '#1d2b53'
rows = [  # top to bottom, drawn as 5 at top
    (5, 'TOOL', 'what officers and field staff use', 'event board, unit calls, route view, field entry, evidence card', '#e8f0fb', 'built, to extend'),
    (4, 'FIELD PLANNING', 'which checks, which roads', 'next check = largest expected drop in wrong calls; flood-aware routes', '#fde9d9', 'simulated'),
    (3, 'ESTIMATION', 'map plus checks into a unit call', 'stratified corrected share, call above/below 25%, probability P', '#fde9d9', 'simulated'),
    (2, 'MAPPING', 'the quick guess', 'radar threshold, U-Net, terrain priors, paddy mask, duration', '#fff4d6', 'part built'),
    (1, 'DATA AND PLATFORM', 'scenes, units, roads, receipts', 'STAC search, tiling, queue, receipts, unit boundaries, road graph', '#e6f2e0', 'mostly built'),
]
fig, ax = plt.subplots(figsize=(8.2, 6.4), dpi=220)
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis('off')
h, gap = 16.5, 3.4
for i, (n, name, sub, det, fc, st) in enumerate(rows):
    y = 100 - (i + 1) * h - i * gap
    ax.add_patch(FancyBboxPatch((1.5, y), 97, h, boxstyle='round,pad=0,rounding_size=2.2', fc=fc, ec=NAVY, lw=1.4))
    ax.add_patch(Circle((7, y + h / 2), 3.1, fc=NAVY))
    ax.text(7, y + h / 2 - 0.2, str(n), ha='center', va='center', color='white', fontsize=16, fontweight='bold')
    ax.text(13, y + h - 4.2, name, fontsize=15, fontweight='bold', color=NAVY, va='center')
    ax.text(13, y + h / 2 - 0.6, sub, fontsize=11.5, style='italic', color='#333', va='center')
    ax.text(13, y + 3.6, det, fontsize=11.5, color='#222', va='center')
    ax.text(96.5, y + h - 4.2, st, fontsize=10, color=NAVY, ha='right', va='center', bbox=dict(boxstyle='round,pad=0.25', fc='white', ec=NAVY, lw=0.8))
    if i < 4:
        ax.add_patch(FancyArrowPatch((50, y - 0.2), (50, y - gap + 0.2), arrowstyle='<|-', mutation_scale=14, lw=1.8, color=NAVY))
fig.savefig('fig_layers.png', bbox_inches='tight', pad_inches=0.05)
from PIL import Image
print(Image.open('fig_layers.png').size)
