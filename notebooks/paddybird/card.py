"""Layer 5 evidence card for one insurance unit. Adapted from the deprecated Paddybird card
(earlier receipt.py and frontend renderCard) with one deliberate change: there is no abstain or
"not enough evidence" state. Every unit gets a call (above or below tau) and P_u.

P_u = P(true flooded-paddy share > tau) = Phi((theta_u - tau) / s_u).
P(call right) = P_u when the call is above, 1 - P_u when it is below.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
from typing import Any, Iterable, Optional

METHOD_VERSION = "paddybird-tool/0.1"
CALLS = ("above", "below")


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def _r(x, n=6):
    return None if x is None else round(float(x), n)


def build_card(unit: dict, scenes: Iterable[dict], checks: Optional[Iterable[dict]] = None, tau: float = 0.25,
               params: Optional[dict] = None, sources: Optional[dict] = None) -> dict:
    """unit needs unit_id, theta, s, P_u, n_checks. The call is derived from theta, never withheld."""
    theta, s, P = float(unit["theta"]), float(unit["s"]), float(unit["P_u"])
    if not (0.0 <= P <= 1.0) or math.isnan(theta):
        raise ValueError(f"unit {unit.get('unit_id')}: invalid estimate")
    call = "above" if theta > tau else "below"
    p_right = P if call == "above" else 1.0 - P
    lo, hi = max(0.0, theta - 1.96 * s), min(1.0, theta + 1.96 * s)
    scenes = sorted(({"id": str(x["id"]), "date": str(x.get("date", "")), "sensor": str(x.get("sensor", ""))} for x in scenes),
                    key=lambda x: (x["date"], x["id"]))
    def _chk_hash(c):
        h = c.get("entry_hash")
        if isinstance(h, str) and h:
            return h
        return digest({k: c.get(k) for k in ("unit_id", "stratum", "flooded", "pi", "ts")})[:16]
    chk = sorted(_chk_hash(c) for c in (checks or []))
    inputs = {"unit_id": str(unit["unit_id"]), "theta": _r(theta), "s": _r(s), "P_u": _r(P),
              "n_checks": int(unit.get("n_checks", 0)), "check_hashes": chk, "scene_ids": [x["id"] for x in scenes],
              "tau": tau, "params": params or {}, "method": METHOD_VERSION, "sources": sources or {}}
    output = {"call": call, "theta": _r(theta, 4), "P_u": _r(P, 4), "p_call_right": _r(p_right, 4),
              "range95": [_r(lo, 4), _r(hi, 4)]}
    receipt = {"schema": "paddybird.receipt/1", "inputs": inputs, "output": output,
               "output_hash": digest({"inputs": inputs, "output": output})}
    receipt["receipt_id"] = digest(receipt)[:16]
    pct = lambda x: f"{100 * x:.1f}%"
    answer = (f"{unit.get('name', unit['unit_id'])}: flooded paddy share {pct(theta)} (95% range {pct(lo)} to {pct(hi)}). "
              f"Call: {call} the {int(round(100 * tau))}% loss line. Probability the call is right: {p_right:.2f}.")
    return {"unit_id": str(unit["unit_id"]), "name": str(unit.get("name", unit["unit_id"])), "call": call, "tau": tau,
            "theta": theta, "s": s, "range95": [lo, hi], "P_u": P, "p_call_right": p_right,
            "n_checks": int(unit.get("n_checks", 0)), "scenes": scenes, "answer_text": answer,
            "method": ("Stratified estimate from the calibrated flood map, corrected by field checks weighted by "
                       "their known inclusion probabilities; the call is always given and P_u says how far to trust it."),
            "caveats": ["Share of paddy area flooded is a proxy: insured-plot records are not public.",
                        "P_u assumes the stated variance; spatial clustering inside a unit can widen it."],
            "receipt": receipt, "receipt_id": receipt["receipt_id"]}


def verify_receipt(receipt: dict) -> bool:
    """Re-derive both hashes from the stored inputs and outputs."""
    body = {k: receipt[k] for k in ("schema", "inputs", "output")}
    if digest({"inputs": body["inputs"], "output": body["output"]}) != receipt["output_hash"]:
        return False
    body["output_hash"] = receipt["output_hash"]
    return digest(body)[:16] == receipt["receipt_id"]


CARD_CSS = """
<style>
.pb-card{font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:640px;border:1px solid #d6d3e8;border-radius:14px;
 padding:14px 16px;background:#fbfaff;color:#1f1d2b;box-shadow:0 2px 6px rgba(60,50,120,.08)}
.pb-card h3{margin:2px 0 6px;font-size:17px}
.pb-badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;color:#fff}
.pb-above{background:#2b6cb0}.pb-below{background:#2f855a}
.pb-head{font-size:28px;font-weight:700;margin:4px 0}.pb-head small{font-size:13px;color:#555;font-weight:400}
.pb-meter{position:relative;height:10px;border-radius:6px;background:#e6e3f3;margin:8px 0 2px}
.pb-fill{position:absolute;left:0;top:0;bottom:0;border-radius:6px;background:#5b4bd6}
.pb-mark{position:absolute;top:-3px;bottom:-3px;width:2px;background:#c53030}
.pb-chips{list-style:none;padding:0;margin:8px 0;display:flex;flex-wrap:wrap;gap:6px}
.pb-chips li{font-size:12px;padding:2px 8px;border-radius:8px;background:#eef;border:1px solid #d6d3e8}
.pb-muted{color:#666;font-size:12px}.pb-card code{font-size:12px}
</style>"""


def card_html(card: dict) -> str:
    e = html.escape
    th, lo, hi = card["theta"], *card["range95"]
    chips = "".join(f"<li title='{e(s['id'])}'><b>{e(s.get('sensor') or 'scene')}</b> {e(s['date'])} <code>{e(s['id'])}</code></li>"
                    for s in card["scenes"])
    chips += f"<li>{card['n_checks']} field checks</li>"
    return (CARD_CSS + f"<div class='pb-card'><span class='pb-badge pb-{card['call']}'>Call: {card['call']} "
            f"{int(round(100 * card['tau']))}%</span><h3>{e(card['name'])}</h3>"
            f"<div class='pb-head'>{100 * th:.1f}% <small>flooded paddy share (95% range {100 * lo:.1f} to {100 * hi:.1f}%)</small></div>"
            f"<div class='pb-meter' role='img' aria-label='theta {100 * th:.1f} percent, line at {100 * card['tau']:.0f} percent'>"
            f"<div class='pb-fill' style='width:{max(1.0, 100 * th):.1f}%'></div><div class='pb-mark' style='left:{100 * card['tau']:.1f}%'></div></div>"
            f"<div class='pb-muted'>Red marker: the {100 * card['tau']:.0f}% loss line.</div>"
            f"<p>{e(card['answer_text'])}</p>"
            f"<p><b>P_u</b> (unit truly above) = {card['P_u']:.3f}; probability the call is right = {card['p_call_right']:.3f}.</p>"
            f"<ul class='pb-chips'>{chips}</ul>"
            f"<p class='pb-muted'>{e(card['method'])}</p>"
            f"<p class='pb-muted'>Receipt <code>{card['receipt_id']}</code>, output hash <code>{card['receipt']['output_hash'][:16]}</code>.</p></div>")


def card_text(card: dict) -> str:
    lines = [f"[{card['call'].upper()} {int(round(100 * card['tau']))}%] {card['answer_text']}",
             f"  P_u = {card['P_u']:.3f}, checks = {card['n_checks']}",
             *[f"  scene {s['date']} {s['id']}" for s in card["scenes"]],
             f"  receipt {card['receipt_id']} (output hash {card['receipt']['output_hash'][:16]})"]
    return "\n".join(lines)
