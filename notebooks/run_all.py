"""Execute the Paddybird notebooks 01 to 06 in order with nbconvert and check each final assertion cell.

Usage (from the repo root, with the shared venv):
    .venv/Scripts/python.exe notebooks/run_all.py              # all six, outputs written in place
    .venv/Scripts/python.exe notebooks/run_all.py 05 06        # only these
    .venv/Scripts/python.exe notebooks/run_all.py --out DIR    # write executed copies to DIR instead

A notebook passes when it runs top to bottom without an error and its last code cell contains an
`assert` and produced no error output. The script stops at the first failure (later layers read the
earlier layers' artifacts) unless --keep-going is given. Exit code 0 only if every notebook passed.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ORDER = ["01", "02", "03", "04", "05", "06"]


def find(prefix: str) -> pathlib.Path | None:
    hits = sorted(HERE.glob(f"{prefix}_*.ipynb"))
    return hits[0] if hits else None


def last_code_cell(nb):
    cells = [c for c in nb.cells if c.cell_type == "code" and c.source.strip()]
    return cells[-1] if cells else None


def kernel_name(default: str) -> str:
    try:
        from jupyter_client.kernelspec import KernelSpecManager
        names = KernelSpecManager().find_kernel_specs()
        return default if default in names else "python3"
    except Exception:
        return "python3"


def run_one(path: pathlib.Path, kernel: str, timeout: int, out_dir: pathlib.Path | None) -> tuple[bool, str]:
    import nbformat
    from nbconvert.preprocessors import ExecutePreprocessor, CellExecutionError
    nb = nbformat.read(path, as_version=4)
    last = last_code_cell(nb)
    if last is None or "assert" not in last.source:
        return False, "final code cell has no assert"
    ep = ExecutePreprocessor(timeout=timeout, kernel_name=kernel)
    err = ""
    try:
        ep.preprocess(nb, {"metadata": {"path": str(HERE)}})
    except CellExecutionError as exc:
        err = str(exc).strip().splitlines()[-1][:300] if str(exc).strip() else "cell error"
    finally:
        dest = (out_dir / path.name) if out_dir else path
        dest.parent.mkdir(parents=True, exist_ok=True)
        nbformat.write(nb, dest)
    if err:
        return False, err
    last = last_code_cell(nb)
    if any(o.get("output_type") == "error" for o in last.get("outputs", [])):
        return False, "final assertion cell raised"
    if last.get("execution_count") is None:
        return False, "final assertion cell did not run"
    text = "".join(o.get("text", "") for o in last.get("outputs", []) if o.get("output_type") == "stream").strip()
    return True, text.splitlines()[-1][:200] if text else "ok"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("only", nargs="*", help="notebook prefixes to run, e.g. 05 06 (default: 01 to 06)")
    ap.add_argument("--kernel", default="paddybird")
    ap.add_argument("--timeout", type=int, default=3600, help="seconds per cell")
    ap.add_argument("--out", type=pathlib.Path, default=None, help="write executed copies here instead of in place")
    ap.add_argument("--keep-going", action="store_true")
    a = ap.parse_args(argv)
    kernel = kernel_name(a.kernel)
    todo = [p for p in ORDER if not a.only or p in a.only]
    results, ok_all = [], True
    for pre in todo:
        path = find(pre)
        if path is None:
            results.append((pre, False, "notebook missing", 0.0)); ok_all = False
            print(f"[{pre}] MISSING");
            if not a.keep_going:
                break
            continue
        t0 = time.time()
        print(f"[{pre}] running {path.name} (kernel {kernel}) ...", flush=True)
        ok, msg = run_one(path, kernel, a.timeout, a.out)
        dt = time.time() - t0
        results.append((path.name, ok, msg, dt))
        print(f"[{pre}] {'PASS' if ok else 'FAIL'} in {dt:.0f} s: {msg}", flush=True)
        if not ok:
            ok_all = False
            if not a.keep_going:
                break
    print("\nsummary")
    for name, ok, msg, dt in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name:32s} {dt:6.0f} s  {msg}")
    return 0 if ok_all and len(results) == len(todo) else 1


if __name__ == "__main__":
    sys.exit(main())
