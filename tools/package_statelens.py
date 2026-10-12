"""Build a portable skill ZIP with a manifest; never include local research data."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "compare-experiments"


def package(destination):
    destination = Path(destination).resolve()
    if SKILL == destination or SKILL in destination.parents:
        raise ValueError("Archive must be outside the skill payload.")
    files = [p for p in sorted(SKILL.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    if any(p.is_symlink() for p in files):
        raise ValueError("Skill payload contains a symlink.")
    manifest = {p.relative_to(SKILL).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            name = "compare-experiments/" + path.relative_to(SKILL).as_posix()
            info = zipfile.ZipInfo(name, (2026,10,12,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
        info = zipfile.ZipInfo("compare-experiments/SHA256SUMS.json", (2026,10,12,0,0,0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, json.dumps(manifest, indent=2) + "\n")
    return {"file":str(destination), "files":len(files), "bytes":destination.stat().st_size,
            "sha256":hashlib.sha256(destination.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "downloads" / "compare-experiments-v0.2.0.zip")
    print(json.dumps(package(parser.parse_args().out), indent=2))
