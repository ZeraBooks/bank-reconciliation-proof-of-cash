"""Write MANIFEST.json and checksums.txt for every data file in the repo.

Run from the repository root:  python3 scripts/build_manifest.py
Standard library only. The output is deterministic, so a clean checkout
reproduces the committed files byte for byte.
"""
import csv
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIRS = ["schema", "rules", "data", "samples", "templates"]


def load_meta():
    with open(os.path.join(ROOT, "repo.json"), encoding="utf-8") as fh:
        return json.load(fh)


def describe(path):
    full = os.path.join(ROOT, path)
    with open(full, "rb") as fh:
        raw = fh.read()
    entry = {"path": path, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if path.endswith(".csv"):
        rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
        entry["rows"] = max(len(rows) - 1, 0)
    return entry


def main():
    meta = load_meta()
    files = []
    for d in DATA_DIRS:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, _, names in os.walk(base):
            for n in names:
                if n.startswith("."):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, n), ROOT).replace(os.sep, "/")
                files.append(rel)
    files.sort()
    entries = [describe(p) for p in files]
    counts = {}
    for e in entries:
        top = e["path"].split("/")[0]
        counts[top] = counts.get(top, 0) + 1
    manifest = {
        "name": meta["name"],
        "version": meta["version"],
        "released": meta["released"],
        "publisher": "Zera Books Inc. (ZeraBooks)",
        "homepage": meta["homepage"],
        "repository": "https://github.com/ZeraBooks/" + meta["name"],
        "license_code": "MIT",
        "license_data": "CC-BY-4.0",
        "fictional_data": True,
        "file_counts": counts,
        "files": entries,
    }
    with open(os.path.join(ROOT, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    with open(os.path.join(ROOT, "checksums.txt"), "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(f"{e['sha256']}  {e['path']}\n")
    print(f"MANIFEST.json: {len(entries)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
