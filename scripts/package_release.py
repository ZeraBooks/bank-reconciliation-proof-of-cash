"""Zip the release assets into dist/.

Run from the repository root:  python3 scripts/package_release.py
Makes dist/<name>-v<version>.zip with the samples, schema, rules, data,
templates, MANIFEST.json, checksums.txt and the licenses.
"""
import json
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INCLUDE_DIRS = ["schema", "rules", "data", "samples", "templates"]
INCLUDE_FILES = ["MANIFEST.json", "checksums.txt", "LICENSE", "LICENSE-SAMPLES", "README.md", "CHANGELOG.md"]


def main():
    with open(os.path.join(ROOT, "repo.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    os.makedirs(os.path.join(ROOT, "dist"), exist_ok=True)
    out = os.path.join(ROOT, "dist", f"{meta['name']}-v{meta['version']}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in INCLUDE_DIRS:
            base = os.path.join(ROOT, d)
            if not os.path.isdir(base):
                continue
            for dirpath, _, names in sorted(os.walk(base)):
                for n in sorted(names):
                    full = os.path.join(dirpath, n)
                    zf.write(full, os.path.relpath(full, ROOT))
        for f in INCLUDE_FILES:
            if os.path.exists(os.path.join(ROOT, f)):
                zf.write(os.path.join(ROOT, f), f)
    print(out)


if __name__ == "__main__":
    main()
