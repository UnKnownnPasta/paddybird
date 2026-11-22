"""Smoke-test: run every code cell of a notebook in one namespace (Agg backend)."""
import json, sys, matplotlib
matplotlib.use("Agg")
nb = json.load(open(sys.argv[1], encoding="utf8"))
ns = {"__name__": "__main__"}
for i, c in enumerate(nb["cells"]):
    if c["cell_type"] != "code":
        continue
    try:
        exec(compile("".join(c["source"]), f"cell{i}", "exec"), ns)
    except Exception as e:
        print(f"!!! cell {i} failed: {type(e).__name__}: {e}"); sys.exit(1)
print("ALL CELLS OK")
