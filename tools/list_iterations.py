"""Print the code iterations in chronological (numeric) order as a Markdown table.

Usage: python3 tools/list_iterations.py code
Main versions are test.py, test2.py, test3.py ...; test.py counts as version 1.
Other .py files (component tests such as Servotest.py) are listed after them.
"""
import re
import sys
from datetime import datetime
from pathlib import Path


def version(path):
    m = re.fullmatch(r"test(\d*)", path.stem, re.IGNORECASE)
    return (int(m.group(1)) if m.group(1) else 1) if m else None


def row(n, path):
    st = path.stat()
    with path.open(encoding="utf-8", errors="replace") as f:
        lines = sum(1 for _ in f)
    when = datetime.fromtimestamp(st.st_mtime).strftime("%d/%m/%Y %H:%M")
    return f"| {n} | [`{path.name}`](code/{path.name}) | {when} | {lines} |"


def main(folder):
    files = sorted(Path(folder).glob("*.py"))
    mains = sorted((f for f in files if version(f) is not None), key=version)
    others = sorted((f for f in files if version(f) is None), key=lambda f: f.stat().st_mtime)
    print("| Version | File | Last modified | Lines |")
    print("| --- | --- | --- | --- |")
    for f in mains:
        print(row(version(f), f))
    if others:
        print("\n| Component test | File | Last modified | Lines |")
        print("| --- | --- | --- | --- |")
        for f in others:
            print(row("-", f))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "code")
