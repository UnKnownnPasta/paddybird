"""Turn a study source file (plain text with '#%% md' and '#%% code' markers) into an .ipynb.

Usage: python _build.py src/S1_data_platform.txt   ->  S1_data_platform_STUDY.ipynb (same folder as this file)
Source files live in study/src/. Only the .ipynb files are meant to be handed out.
"""
import base64
import json
import re
import sys
from pathlib import Path


def parse(text: str):
    cells, kind, buf = [], None, []

    def flush():
        if kind is None:
            return
        body = "\n".join(buf).strip("\n")
        if body:
            cells.append((kind, body))

    for line in text.splitlines():
        if line.startswith("#%% md"):
            flush(); kind, buf = "md", []
        elif line.startswith("#%% code"):
            flush(); kind, buf = "code", []
        else:
            buf.append(line)
    flush()
    return cells


def to_nb(cells):
    out = []
    for kind, body in cells:
        src = body.splitlines(keepends=True)
        if kind == "md":
            cell = {"cell_type": "markdown", "metadata": {}, "source": src}
            att = {}
            for name in re.findall(r"\(attachment:([\w.\-]+)\)", body):
                png = Path(__file__).parent / "figures" / name
                att[name] = {"image/png": base64.b64encode(png.read_bytes()).decode()}
            if att:
                cell["attachments"] = att
            out.append(cell)
        else:
            out.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": src})
    return {"cells": out, "metadata": {"kernelspec": {"display_name": "paddybird", "language": "python", "name": "paddybird"},
                                       "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 5}


if __name__ == "__main__":
    src = Path(sys.argv[1])
    nb = to_nb(parse(src.read_text(encoding="utf-8")))
    for i, c in enumerate(nb["cells"]):
        c["id"] = f"c{i:03d}"
    dest = Path(__file__).parent / (src.stem + "_STUDY.ipynb")
    dest.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    bad = [i for i, c in enumerate(nb["cells"]) if "—" in "".join(c["source"]) or "–" in "".join(c["source"])]
    print("wrote", dest.name, len(nb["cells"]), "cells", "| dash chars in cells:", bad)
