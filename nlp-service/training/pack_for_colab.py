"""Bundle the five inputs train_colab_v3.ipynb needs into one zip.

Colab's upload picker selects from one folder at a time and the inputs live in
three, so choosing them one by one silently sends only some. One zip avoids it.
The manifest records each file's SHA-256, and the notebook refuses a file that
does not match — so an old copy cannot be trained on by mistake.

    python training/pack_for_colab.py

Writes nlp-service/colab_upload_v3.zip (gitignored; rebuild it after
regenerating any input).
"""
import datetime
import hashlib
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
NLP = os.path.dirname(HERE)
ROOT = os.path.dirname(NLP)
sys.path.insert(0, NLP)

from training.redaction import leaks  # noqa: E402

PROCESSED = os.path.join(ROOT, "data", "processed")
INPUTS = {
    "train.csv": os.path.join(PROCESSED, "random", "train.csv"),
    "val.csv": os.path.join(PROCESSED, "random", "val.csv"),
    "minimal_pairs_train.csv": os.path.join(PROCESSED, "augmented", "minimal_pairs_train.csv"),
    "minimal_pairs_test.csv": os.path.join(PROCESSED, "augmented", "minimal_pairs_test.csv"),
    "gates.json": os.path.join(HERE, "gates.json"),
}
OUT = os.path.join(NLP, "colab_upload_v3.zip")


def main():
    absent = [name for name, path in INPUTS.items() if not os.path.exists(path)]
    if absent:
        sys.exit(f"missing inputs: {absent}")

    # gates.json carries text from real screenshots; it leaves this machine.
    with open(INPUTS["gates.json"], encoding="utf-8") as handle:
        found = leaks(handle.read())
    if found:
        sys.exit(f"refusing to pack: gates.json still contains personal data {found}")

    manifest = {"packed": datetime.datetime.now().isoformat(timespec="seconds"),
                "files": {}}
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, path in INPUTS.items():
            with open(path, "rb") as handle:
                data = handle.read()
            bundle.writestr(name, data)
            manifest["files"][name] = {"sha256": hashlib.sha256(data).hexdigest(),
                                       "bytes": len(data)}
            print(f"  {name:<26} {len(data):>8} bytes")
        bundle.writestr("manifest.json", json.dumps(manifest, indent=2))

    print(f"\nwrote {OUT}  ({os.path.getsize(OUT) / 1e3:.0f} KB)")


if __name__ == "__main__":
    main()
