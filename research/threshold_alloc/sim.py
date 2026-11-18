"""Wrong-call rate vs field checks for the 25% unit decision (synthetic).

Every method answers every unit: call = (estimate > TAU), P = Phi((est-TAU)/sd).
Methods (same estimator, only the allocation of field checks differs):
  map_only   : raw map flooded fraction, no checks
  field_only : simple random sample inside each unit, no map
  strat_equal: stratified by map (flooded/dry), equal split, same n per unit
  neyman     : adaptive, greedy total-variance reduction (decision-blind baseline)
  target     : adaptive, greedy expected drop in P(wrong call) (decision-aware)

Run: python sim.py   (writes results.json and ../../docs/figures/wrong_call_vs_checks.png)
Limits (ponytail): pixels iid inside a unit (no spatial clustering); adaptive
allocation uses plain stratum means, not importance-weighted ones, so bias is
measured (column `bias`), not guaranteed.
"""
import json, pathlib, sys
import numpy as np
from scipy.special import ndtr

TAU, U, N, M = 0.25, 200, 1500, 2.0          # threshold, units, pixels/unit, prior strength
BUDGETS = [0, 2, 4, 6, 8, 12, 16, 24, 32]     # mean field checks per unit
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 40
GX, GW = np.polynomial.hermite_e.hermegauss(15)
GW = GW / GW.sum()


def make(rng):
    th = rng.beta(2.5, 7.5, U)                       # true flooded share, mean .25
    sens, fpr = rng.beta(15, 5, U), rng.beta(2, 22, U)  # per-unit map error (event bias)
    Y = rng.random((U, N)) < th[:, None]
    f = np.where(Y, rng.random((U, N)) < sens[:, None], rng.random((U, N)) < fpr[:, None])
    return Y, f


class Survey:
    """Sampling without replacement inside each (unit, map stratum)."""

    def __init__(self, Y, f, rng):
        self.Y, self.f = Y, f
        self.Nh = np.stack([(~f).sum(1), f.sum(1)], 1)          # stratum sizes (dry, flooded)
        self.W = self.Nh / N
        self.n = np.zeros((U, 2)); self.k = np.zeros((U, 2))
        self.order = [[rng.permutation(np.flatnonzero(f[u] == h)) for h in (0, 1)] for u in range(U)]

    def label(self, u, h):
        if self.n[u, h] >= self.Nh[u, h]:
            return
        i = self.order[u][h][int(self.n[u, h])]
        self.n[u, h] += 1; self.k[u, h] += self.Y[u, i]

    def prior(self):                                   # pooled stratum rate (borrowing across units)
        return (self.k.sum(0) + 0.5 * M) / (self.n.sum(0) + M)

    def var_h(self, n, p):
        return self.W ** 2 * p * (1 - p) / (n + M + 1)

    def estimate(self):
        p = (self.k + M * self.prior()) / (self.n + M)
        fpc = np.where(self.Nh > 0, 1 - self.n / np.maximum(self.Nh, 1), 0)
        return (self.W * p).sum(1), np.sqrt((self.var_h(self.n, p) * fpc).sum(1) + 1e-12), p


def run_adaptive(S, budget, rule):
    S_left = U * budget - 0
    for u in range(U):                                 # pilot: one check per nonempty stratum
        for h in (0, 1):
            if S_left > 0 and S.Nh[u, h] > 0:
                S.label(u, h); S_left -= 1
    while S_left > 0:
        est, sd, p = S.estimate()
        v0 = S.var_h(S.n, p)
        v1 = S.var_h(S.n + 1, p)
        if rule == "neyman":
            gain = v0 - v1
        else:                                          # expected drop in P(wrong call)
            sig2 = (v0.sum(1))[:, None]
            sig2n = sig2 - v0 + v1
            d = (est - TAU)[:, None]
            tau = np.sqrt(np.maximum(sig2 - sig2n, 0))
            s1 = np.sqrt(sig2n)
            after = (ndtr(-np.abs(d[:, :, None] + tau[:, :, None] * GX) / s1[:, :, None]) * GW).sum(2)
            gain = ndtr(-np.abs(d) / np.sqrt(sig2)) - after
        gain = np.where(S.n < S.Nh, gain, -np.inf)
        k = min(U // 4, S_left)
        for flat in np.argsort(gain, axis=None)[::-1][:k]:
            if not np.isfinite(gain.flat[flat]):
                break
            S.label(*divmod(flat, 2)); S_left -= 1
        else:
            continue
        if S_left > 0 and not np.isfinite(gain).any():
            break


def run_equal(S, budget):
    for u in range(U):
        for h, c in ((1, (budget + 1) // 2), (0, budget // 2)):
            for _ in range(c):
                S.label(u, h)


def run_field_only(Y, b, rng):
    k = np.array([Y[u, rng.choice(N, b, replace=False)].sum() for u in range(U)]) if b else np.zeros(U)
    pr = (k.sum() + 0.5 * M) / (U * b + M)
    p = (k + M * pr) / (b + M)
    return p, np.sqrt(p * (1 - p) / (b + M + 1) * (1 - b / N) + 1e-12)


def score(est, sd, truth):
    call, P = est > TAU, ndtr((est - TAU) / sd)
    t = truth > TAU
    return dict(wrong=float((call != t).mean()), brier=float(((P - t) ** 2).mean()),
                mae=float(np.abs(est - truth).mean()), bias=float((est - truth).mean()))


def main():
    out = {m: {b: [] for b in BUDGETS} for m in ("map_only", "field_only", "strat_equal", "neyman", "target")}
    for r in range(REPS):
        rng = np.random.default_rng(1000 + r)
        Y, f = make(rng)
        truth = Y.mean(1)
        for b in BUDGETS:
            mo = f.mean(1)
            out["map_only"][b].append(score(mo, np.full(U, 0.1), truth))
            if b == 0:
                for m in ("field_only", "strat_equal", "neyman", "target"):
                    out[m][b].append(out["map_only"][b][-1])
                continue
            p, sd = run_field_only(Y, b, rng)
            out["field_only"][b].append(score(p, sd, truth))
            S = Survey(Y, f, rng); run_equal(S, b)
            e, s, _ = S.estimate(); out["strat_equal"][b].append(score(e, s, truth))
            for rule in ("neyman", "target"):
                S = Survey(Y, f, rng); run_adaptive(S, b, rule)
                e, s, _ = S.estimate(); out[rule][b].append(score(e, s, truth))
    res = {m: {b: {k: float(np.mean([x[k] for x in v])) for k in v[0]} for b, v in d.items()} for m, d in out.items()}
    here = pathlib.Path(__file__).parent
    (here / "results.json").write_text(json.dumps(res, indent=1))
    for m, d in res.items():
        print(f"{m:12s}", " ".join(f"{d[b]['wrong']:.3f}" for b in BUDGETS))
    print("budgets     ", BUDGETS)
    assert res["target"][32]["wrong"] < res["map_only"][32]["wrong"], "check beats map"
    try:
        import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(6.4, 4))
        for m, lab in (("map_only", "map only"), ("field_only", "field only"), ("strat_equal", "map + checks, equal split"),
                       ("neyman", "map + checks, variance-minimising"), ("target", "map + checks, decision-targeted")):
            ax.plot(BUDGETS, [100 * res[m][b]["wrong"] for b in BUDGETS], marker="o", label=lab)
        ax.set_xlabel("field checks per unit"); ax.set_ylabel("wrong 25% calls (%)")
        ax.set_title(f"{U} units, every unit answered, mean of {REPS} runs"); ax.legend(fontsize=8); ax.grid(alpha=.3)
        fig.tight_layout(); fig.savefig(here.parents[1] / "docs" / "figures" / "wrong_call_vs_checks.png", dpi=150)
    except ImportError:
        pass


if __name__ == "__main__":
    main()
