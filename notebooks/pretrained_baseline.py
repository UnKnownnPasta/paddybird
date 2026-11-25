"""Published pretrained comparison for layer 2: the Sen1Floods11 authors' released S1 model (FCN-ResNet50,
VV and VH, trained on their hand-labelled split), run as released. No retraining, no tuning, no calibration.
Same chips, filter and metrics as deep_baseline.py. Test events scored once. Run: python pretrained_baseline.py
LEAKAGE: the model's training split includes India chips (8 of our 12 India test chips are in it, 1 more in
its validation split). Bolivia is the authors' own held-out event and is clean."""
import csv, io, json, sys, urllib.request
from pathlib import Path
import numpy as np, torch, torch.nn as nn
from torchvision.models.segmentation import fcn_resnet50
NB = Path(__file__).parent
sys.path.insert(0, str(NB))
from paddybird import water, calibrate, data

L1, OUT, CACHE = NB / "artifacts" / "layer1", NB / "artifacts" / "layer2", NB / "data"
CKPT = "v1.1/checkpoints/5e4_handlabeled_0_8_0.43163052201271057.cp"
SPLITS = {s: f"v1.1/splits/flood_handlabeled/flood_{s}_data.csv" for s in ("train", "valid", "test", "bolivia")}
GS = "https://storage.googleapis.com/sen1floods11/"

chips = water.load_chips(L1); water.assign_splits(chips)
for c in chips:
    c["domain"] = water.valid_mask(c) & ~water.perm_mask(c); c["y"] = c["label"] == 1
chips = [c for c in chips if c["domain"].mean() >= 0.3]       # same filter as 02_mapping.ipynb and deep_baseline.py
by = {s: [c for c in chips if c["split"] == s] for s in ("val", "test")}

# which official split each of our chips sat in when the published model was trained
official = {}
for s, path in SPLITS.items():
    for row in csv.reader(io.StringIO(urllib.request.urlopen(GS + path).read().decode())):
        official[row[0].replace("_S1Hand.tif", "")] = s

ck = CACHE / "sen1floods11_handlabeled.cp"
if not ck.exists(): urllib.request.urlretrieve(GS + CKPT, ck)
net = fcn_resnet50(weights=None, weights_backbone=None, num_classes=2, aux_loss=False)
net.backbone.conv1 = nn.Conv2d(2, 64, kernel_size=7, stride=2, padding=3, bias=False)
def bn_to_gn(m):  # as convertBNtoGN in the authors' Train.ipynb (16 groups)
    if isinstance(m, nn.BatchNorm2d): return nn.GroupNorm(16, m.num_features, eps=m.eps, affine=m.affine)
    for name, ch in m.named_children(): m.add_module(name, bn_to_gn(ch))
    return m
net = bn_to_gn(net)
net.load_state_dict(torch.load(ck, map_location="cpu", weights_only=True)); net.eval()
MEAN, STD = torch.tensor([0.6851, 0.5235])[:, None, None], torch.tensor([0.0820, 0.1102])[:, None, None]

def prob20(c):
    """Original 10 m S1Hand chip, preprocessed as in the authors' Train.ipynb (clip, scale, normalise, four
    256 px tiles), water softmax, then 2 x 2 mean to our 20 m grid and the same centre crop as layer 1."""
    s1 = data._read_tif(data._get(f"{data.BUCKET}/data/flood_events/HandLabeled/S1Hand/{c['chip']}_S1Hand.tif"))[0]
    x = (torch.tensor(np.clip(np.nan_to_num(s1[:2]), -50, 1)) + 50) / 51
    x = (x - MEAN) / STD
    H, W = x.shape[1:]
    p = torch.zeros(H, W)
    with torch.no_grad():
        for r in range(0, H, 256):
            for q in range(0, W, 256):
                p[r:r+256, q:q+256] = net(x[None, :, r:r+256, q:q+256])["out"].softmax(1)[0, 1]
    p = p.numpy()[:H // 2 * 2, :W // 2 * 2].reshape(H // 2, 2, W // 2, 2).mean((1, 3))
    h, w = c["y"].shape; r0, c0 = (p.shape[0] - h) // 2, (p.shape[1] - w) // 2
    return p[r0:r0 + h, c0:c0 + w]

def pix(cs, P): return np.concatenate([P[i][c["domain"]] for i, c in enumerate(cs)]), np.concatenate([c["y"][c["domain"]] for c in cs])
def by_event(cs, P):
    return {ev: calibrate.scores(*pix([c for c in cs if c["event"] == ev], [P[i] for i, c in enumerate(cs) if c["event"] == ev]))
            for ev in sorted({c["event"] for c in cs})}

res = {"model": "Sen1Floods11 authors' FCN-ResNet50 on S1 VV and VH, hand-labelled checkpoint, run as released, raw softmax, no calibration",
       "source": GS + CKPT, "code": "https://github.com/cloudtostreet/Sen1Floods11 (Train.ipynb preprocessing)",
       "official_split_of_our_chips": {s: {c["chip"]: official.get(c["chip"], "not listed") for c in by[s]} for s in by}}
Pv = [prob20(c) for c in by["val"]]
res["val"] = calibrate.scores(*pix(by["val"], Pv)); res["val_by_event"] = by_event(by["val"], Pv)
# ===== TEST: run once =====
Ps = [prob20(c) for c in by["test"]]
res["test"] = calibrate.scores(*pix(by["test"], Ps)); res["test_by_event"] = by_event(by["test"], Ps)
(OUT / "pretrained_baseline.json").write_text(json.dumps(res, indent=1, default=float))
for k in ("val", "test"): print(k, {a: round(res[k][a], 4) for a in ("iou", "ece", "brier", "area_ratio_expected")})
for ev, s in res["test_by_event"].items(): print(ev, {a: round(s[a], 4) for a in ("iou", "ece", "brier", "area_ratio_expected")})
