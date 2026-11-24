"""Deep baseline for layer 2: a small U-Net on VV/VH, trained on train events, model and threshold-free
(raw sigmoid) selection on validation events, test events scored once. Run: python deep_baseline.py [--no-test]"""
import json, sys, time
from pathlib import Path
import numpy as np, torch, torch.nn as nn, torch.nn.functional as Fn
NB = Path(__file__).parent
sys.path.insert(0, str(NB))
from paddybird import water, calibrate

SEED = 20261118
torch.manual_seed(SEED); rng = np.random.default_rng(SEED)
L1, OUT = NB / "artifacts" / "layer1", NB / "artifacts" / "layer2"

chips = water.load_chips(L1); water.assign_splits(chips)
for c in chips:
    c["domain"] = water.valid_mask(c) & ~water.perm_mask(c); c["y"] = c["label"] == 1
chips = [c for c in chips if c["domain"].mean() >= 0.3]       # same filter as 02_mapping.ipynb
by = {s: [c for c in chips if c["split"] == s] for s in ("train", "val", "test")}

def X(c):  # VV, VH scaled from dB to roughly [-1, 1]; nan -> 0
    return torch.tensor(np.nan_to_num(np.stack([(c["s1_vv"] + 12) / 8, (c["s1_vh"] + 20) / 8]), nan=0.0), dtype=torch.float32)
def tens(cs):
    return torch.stack([X(c) for c in cs]), torch.tensor(np.stack([c["y"] for c in cs]), dtype=torch.float32), torch.tensor(np.stack([c["domain"] for c in cs]), dtype=torch.float32)

def blk(i, o): return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(), nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU())
class UNet(nn.Module):
    def __init__(s, w=16):
        super().__init__()
        s.e1, s.e2, s.e3, s.b = blk(2, w), blk(w, 2*w), blk(2*w, 4*w), blk(4*w, 8*w)
        s.u3, s.d3 = nn.ConvTranspose2d(8*w, 4*w, 2, 2), blk(8*w, 4*w)
        s.u2, s.d2 = nn.ConvTranspose2d(4*w, 2*w, 2, 2), blk(4*w, 2*w)
        s.u1, s.d1 = nn.ConvTranspose2d(2*w, w, 2, 2), blk(2*w, w)
        s.out = nn.Conv2d(w, 1, 1)
    def forward(s, x):
        a = s.e1(x); b = s.e2(Fn.max_pool2d(a, 2)); c = s.e3(Fn.max_pool2d(b, 2)); d = s.b(Fn.max_pool2d(c, 2))
        d = s.d3(torch.cat([s.u3(d), c], 1)); d = s.d2(torch.cat([s.u2(d), b], 1)); d = s.d1(torch.cat([s.u1(d), a], 1))
        return s.out(d)[:, 0]

def predict(m, x):
    m.eval()
    with torch.no_grad(): return torch.sigmoid(torch.cat([m(x[i:i+16]) for i in range(0, len(x), 16)])).numpy()
def pix(cs, P): return np.concatenate([P[i][c["domain"]] for i, c in enumerate(cs)]), np.concatenate([c["y"][c["domain"]] for c in cs])

Xt, Yt, Mt = tens(by["train"]); Xv = tens(by["val"])[0]
m = UNet(); opt = torch.optim.AdamW(m.parameters(), 2e-3, weight_decay=1e-4)
best, best_state, t0, EP = (-1, None), None, time.time(), 60
for ep in range(EP):
    m.train(); perm = torch.randperm(len(Xt))
    for i in range(0, len(Xt), 8):
        j = perm[i:i+8]; x, y, w = Xt[j], Yt[j], Mt[j]
        k = int(rng.integers(4)); x, y, w = [torch.rot90(t, k, (-2, -1)) for t in (x, y, w)]
        if rng.random() < .5: x, y, w = [t.flip(-1) for t in (x, y, w)]
        loss = (Fn.binary_cross_entropy_with_logits(m(x), y, reduction="none") * w).sum() / w.sum()
        opt.zero_grad(); loss.backward(); opt.step()
    p, y = pix(by["val"], predict(m, Xv)); iou = calibrate.scores(p, y)["iou"]
    if iou > best[0]: best, best_state = (iou, ep), {k: v.clone() for k, v in m.state_dict().items()}
    if ep % 10 == 9: print(f"epoch {ep+1} val IoU {iou:.3f} (best {best[0]:.3f} @ {best[1]+1}) {time.time()-t0:.0f}s", flush=True)
m.load_state_dict(best_state)
res = {"model": "U-Net, 2 channels (VV, VH), 4 levels, width 16, raw sigmoid, no calibration", "best_epoch": best[1] + 1, "seed": SEED}
res["val"] = calibrate.scores(*pix(by["val"], predict(m, Xv)))
if "--no-test" not in sys.argv:
    # ===== TEST: run once =====
    Xs = tens(by["test"])[0]; Ps = predict(m, Xs)
    res["test"] = calibrate.scores(*pix(by["test"], Ps))
    res["test_by_event"] = {ev: calibrate.scores(*pix([c for c in by["test"] if c["event"] == ev], Ps[[i for i, c in enumerate(by["test"]) if c["event"] == ev]])) for ev in sorted({c["event"] for c in by["test"]})}
(OUT / ("deep_baseline_smoke.json" if "--no-test" in sys.argv else "deep_baseline.json")).write_text(json.dumps(res, indent=1, default=float))
print(json.dumps({k: (v if k not in ("val", "test") else {a: round(float(b), 4) for a, b in v.items() if a in ("iou", "ece", "brier", "area_ratio_expected")}) for k, v in res.items() if k != "test_by_event"}, indent=1))
