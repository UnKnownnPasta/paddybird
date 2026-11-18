"""Layer 5 views: unit-calls table, unit map (matplotlib, optional folium), officer day-route
view with flooded roads in blue, and the three-step wizard (ipywidgets, with a static fallback
that renders the same three steps as plain HTML and figures under nbconvert)."""
from __future__ import annotations

import html
from typing import Callable, Optional

import numpy as np
import pandas as pd

ABOVE, BELOW, FLOOD_BLUE, ROAD_GREY = "#2b6cb0", "#2f855a", "#1f5fbf", "#c4c9d2"
OFFICER_COLORS = ("#c53030", "#6b46c1", "#d69e2e", "#2c7a7b")


def at_tau(units: pd.DataFrame, tau: float, base_tau: float = 0.25) -> pd.DataFrame:
    """Re-evaluate P_u = Phi((theta - tau)/s) when the officer moves the loss line away from the layer-3 value."""
    if abs(tau - base_tau) < 1e-12:
        return units
    from scipy.stats import norm
    t = units.copy()
    t["P_u"] = norm.cdf((t.theta - tau) / t.s.clip(lower=1e-9))
    return t


def unit_calls_table(units: pd.DataFrame, tau: float = 0.25) -> pd.DataFrame:
    """Every unit with a call; ordered by the chance the call is wrong, so attention goes where it helps."""
    t = at_tau(units, tau).copy()
    t["call"] = np.where(t.theta > tau, "above", "below")
    t["p_call_right"] = np.where(t.call == "above", t.P_u, 1 - t.P_u)
    t["p_wrong"] = 1 - t.p_call_right
    cols = [c for c in ("unit_id", "name", "theta", "s", "call", "P_u", "p_call_right", "n_checks", "p_wrong") if c in t]
    t = t[cols].sort_values("p_wrong", ascending=False).reset_index(drop=True)
    t.insert(0, "rank", np.arange(1, len(t) + 1))
    return t


def table_html(t: pd.DataFrame, max_rows: int = 30) -> str:
    f = {"theta": "{:.1%}".format, "s": "{:.3f}".format, "P_u": "{:.3f}".format,
         "p_call_right": "{:.3f}".format, "p_wrong": "{:.3f}".format}
    return t.head(max_rows).to_html(index=False, formatters={k: v for k, v in f.items() if k in t}, border=0,
                                    classes="pb-table")


def plot_unit_map(units: pd.DataFrame, ax=None, tau: float = 0.25, title: str = "", highlight: Optional[str] = None):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    if ax is None:
        _, ax = plt.subplots(figsize=(6.4, 5))
    units = at_tau(units, tau)
    half = units["half"].to_numpy() if "half" in units else np.full(len(units), 0.02)
    for (r, h) in zip(units.itertuples(), half):
        call = "above" if r.theta > tau else "below"
        right = r.P_u if call == "above" else 1 - r.P_u
        ax.add_patch(Rectangle((r.lon - h, r.lat - h), 2 * h, 2 * h, facecolor=ABOVE if call == "above" else BELOW,
                               alpha=0.25 + 0.65 * (right - 0.5) / 0.5, edgecolor="k" if r.unit_id == highlight else "white",
                               lw=2.5 if r.unit_id == highlight else 1))
        if len(units) <= 40:
            lbl = str(r.unit_id) if len(str(r.unit_id)) <= 10 else str(r.unit_id).replace("_u", "\nu")
            ax.text(r.lon, r.lat, f"{lbl}\n{100 * r.theta:.0f}%  P={r.P_u:.2f}", ha="center", va="center", fontsize=6)
        else:
            ax.text(r.lon, r.lat, f"{r.unit_id}", ha="center", va="center", fontsize=5)
    pad = float(np.max(half)) * 1.2
    ax.set_xlim(units.lon.min() - pad, units.lon.max() + pad); ax.set_ylim(units.lat.min() - pad, units.lat.max() + pad)
    ax.set_aspect("equal")
    if "schematic" in units and bool(units["schematic"].any()):          # schematic layout, not map coordinates
        ax.set_xticks([]); ax.set_yticks([]); ax.set_xlabel("schematic layout (not to scale)")
    else:
        ax.set_xlabel("longitude"); ax.set_ylabel("latitude")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=ABOVE, label=f"call: above {tau:.0%}"), Patch(color=BELOW, label=f"call: below {tau:.0%}")],
              loc="upper left", fontsize=8, framealpha=.9)
    ax.set_title(title or "Unit calls (shade = probability the call is right)", fontsize=10)
    return ax


def plot_route_view(nodes: pd.DataFrame, edges: pd.DataFrame, routes: list, units: Optional[pd.DataFrame] = None,
                    ax=None, title: str = "", depot: Optional[int] = None):
    """Officer day routes over the road graph. Flooded roads in blue, dry roads grey, one colour per officer."""
    import matplotlib.pyplot as plt
    if ax is None:
        _, ax = plt.subplots(figsize=(6.4, 5.4))
    xy = nodes.set_index("node")[["lon", "lat"]]
    for e in edges.itertuples():
        if e.a in xy.index and e.b in xy.index:
            (x0, y0), (x1, y1) = xy.loc[e.a], xy.loc[e.b]
            ax.plot([x0, x1], [y0, y1], color=FLOOD_BLUE if e.flooded else ROAD_GREY, lw=2.6 if e.flooded else 0.9, zorder=1)
    if units is not None:
        ax.scatter(units.lon, units.lat, c=np.minimum(units.P_u, 1 - units.P_u), cmap="Oranges", vmin=0, vmax=0.5,
                   s=60, edgecolor="k", lw=.5, zorder=4)
        uxy = units.set_index("unit_id")[["lon", "lat"]]
    for i, r in enumerate(routes):
        col = OFFICER_COLORS[i % len(OFFICER_COLORS)]
        pts = [tuple(xy.loc[n]) for n in r.get("nodes", []) if n in xy.index]
        if not pts and units is not None:
            pts = [tuple(uxy.loc[s]) for s in r.get("stops", []) if s in uxy.index]
        if pts:
            jit = (i - (len(routes) - 1) / 2) * 0.0012
            ax.plot([p[0] + jit for p in pts], [p[1] + jit for p in pts], color=col, lw=2.2, zorder=3,
                    label=f"{r['officer']}: {len(r.get('stops', []))} stops" + (f", {r['minutes']:.0f} min" if r.get("minutes") else ""))
        if units is not None:
            for k, s in enumerate(r.get("stops", [])):
                if s in uxy.index:
                    ax.annotate(f"{k + 1}", uxy.loc[s], xytext=(4, 4), textcoords="offset points", color=col, fontsize=8, weight="bold")
    d = depot if depot is not None else (routes[0]["nodes"][0] if routes and routes[0].get("nodes") else None)
    if d is not None and d in xy.index:
        ax.scatter(*xy.loc[d], marker="s", c="k", s=70, zorder=5, label="depot")
    ax.plot([], [], color=FLOOD_BLUE, lw=2.6, label="flooded road"); ax.plot([], [], color=ROAD_GREY, lw=0.9, label="dry road")
    ax.legend(fontsize=7, loc="lower right", framealpha=.9)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title or "Officer day routes (blue = flooded roads; dot shade = chance the call is wrong)", fontsize=10)
    return ax


def folium_map(units: pd.DataFrame, tau: float = 0.25, edges: Optional[pd.DataFrame] = None,
               nodes: Optional[pd.DataFrame] = None, tiles: Optional[str] = "OpenStreetMap"):
    """Leaflet map like the old UI. Base tiles load in a browser only; the overlays are self-contained."""
    import folium
    m = folium.Map(location=[float(units.lat.mean()), float(units.lon.mean())], zoom_start=11, tiles=tiles)
    half = units["half"] if "half" in units else pd.Series(0.02, index=units.index)
    for r, h in zip(units.itertuples(), half):
        call = "above" if r.theta > tau else "below"
        folium.Rectangle([[r.lat - h, r.lon - h], [r.lat + h, r.lon + h]], color="white", weight=1, fill=True,
                         fill_color=ABOVE if call == "above" else BELOW, fill_opacity=0.55,
                         tooltip=f"{html.escape(str(r.unit_id))}: {100 * r.theta:.1f}%, call {call}, P_u {r.P_u:.2f}, {r.n_checks} checks").add_to(m)
    if edges is not None and nodes is not None:
        xy = nodes.set_index("node")[["lat", "lon"]]
        for e in edges[edges.flooded].itertuples():
            folium.PolyLine([tuple(xy.loc[e.a]), tuple(xy.loc[e.b])], color=FLOOD_BLUE, weight=4).add_to(m)
    return m


# ---------------------------------------------------------------- three-step wizard
STEPS = ("1 Event", "2 Unit calls", "3 Evidence card")


def static_wizard(event_html: str, table: pd.DataFrame, map_fig, card_html_str: str) -> str:
    """The same three steps as the widget, as one HTML block that survives nbconvert."""
    return ("<div style='font-family:system-ui,Segoe UI,Arial'>"
            f"<h4>{STEPS[0]}</h4>{event_html}"
            f"<h4>{STEPS[1]}</h4>{table_html(table, 12)}"
            f"<p style='color:#666;font-size:12px'>Map figure shown below this block.</p>"
            f"<h4>{STEPS[2]}</h4>{card_html_str}</div>")


def interactive_wizard(units: pd.DataFrame, event_html: str, make_card: Callable[[str, float], str], tau: float = 0.25):
    """ipywidgets version of the old ask, configure, run flow: pick the event, set the line,
    pick a unit, read its card. Returns the widget, or None when ipywidgets is unavailable."""
    try:
        import ipywidgets as W
        from IPython.display import display, HTML
        import matplotlib.pyplot as plt
    except Exception:
        return None
    step = W.ToggleButtons(options=list(STEPS), value=STEPS[0])
    tau_w = W.FloatSlider(value=tau, min=0.05, max=0.6, step=0.01, description="Loss line", readout_format=".2f")
    unit_w = W.Dropdown(options=list(unit_calls_table(units, tau).unit_id), description="Unit")
    out = W.Output()

    def render(*_):
        with out:
            out.clear_output(wait=True)
            if step.value == STEPS[0]:
                display(HTML(event_html))
            elif step.value == STEPS[1]:
                t = unit_calls_table(units, tau_w.value)
                display(HTML(table_html(t)))
                fig, ax = plt.subplots(figsize=(6, 4.6)); plot_unit_map(units, ax, tau=tau_w.value, highlight=unit_w.value)
                plt.show()
            else:
                display(HTML(make_card(unit_w.value, tau_w.value)))

    for w in (step, tau_w, unit_w):
        w.observe(render, names="value")
    render()
    return W.VBox([W.HTML("<b>Paddybird</b>: event, unit calls, evidence card"), step, W.HBox([tau_w, unit_w]), out])
