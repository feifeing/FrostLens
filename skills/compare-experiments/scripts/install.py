"""Install the standalone skill without editing host settings or downloading code."""
import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
from statelens import ArgumentParser, say

NAME = "compare-experiments"
SOURCE = Path(__file__).resolve().parents[1]
EXCLUDED = {"__pycache__", ".git", ".venv"}


def payload(root):
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in EXCLUDED for part in relative.parts) or path.suffix == ".pyc":
            continue
        if path.is_symlink():
            raise ValueError(f"Skill payload cannot contain symlinks: {relative}")
        if path.is_file():
            files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def install_to(parent, replace=False):
    parent = Path(parent).expanduser().resolve()
    target = parent / NAME
    if target.is_symlink():
        raise ValueError("Existing skill is a symlink; choose an explicit different destination.")
    resolved = target.resolve()
    if SOURCE == resolved or SOURCE in resolved.parents or resolved in SOURCE.parents:
        raise ValueError("Install destination overlaps the source skill.")
    expected = payload(SOURCE)
    if not expected or "SKILL.md" not in expected:
        raise ValueError("Incomplete skill package.")
    if target.exists():
        if target.is_dir() and payload(target) == expected:
            return {"path":str(target), "status":"already_installed"}
        if not replace:
            raise ValueError(f"Skill already exists at {target}; --replace keeps a backup before updating.")
    parent.mkdir(parents=True, exist_ok=True)
    # Both the staging directory and backup are fixed children of the resolved parent.
    with tempfile.TemporaryDirectory(prefix=".statelens-install-", dir=parent) as staging:
        staged = Path(staging) / NAME
        for relative in expected:
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / relative, destination)
        if payload(staged) != expected:
            raise OSError("Staged skill verification failed.")
        backup = None
        if target.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
            # Outside the discovery folder: a backup must not load as a second skill.
            backup_parent = parent.parent / "statelens-backups"
            backup_parent.mkdir(parents=True, exist_ok=True)
            backup = backup_parent.resolve() / f"{NAME}-{stamp}"
            if target.resolve().parent != parent or backup.parent != backup_parent.resolve():
                raise ValueError("Unexpected installation path.")
            target.rename(backup)
        try:
            staged.rename(target)
        except OSError:
            if backup and not target.exists():
                backup.rename(target)
            raise
    return {"path":str(target), "status":"installed", "backup":str(backup) if backup else None}


def main(argv=None):
    parser = ArgumentParser(description="Install StateLens for Codex or Claude Code")
    parser.add_argument("--target", choices=("codex", "claude", "both"), required=True)
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--project", type=Path, help="Required for project scope")
    parser.add_argument("--destination", type=Path, help="Explicit skills parent directory; single target only")
    parser.add_argument("--replace", action="store_true", help="Keep a backup and replace a differing existing skill")
    args = parser.parse_args(argv)
    try:
        if args.destination and args.target == "both":
            raise ValueError("Use a single target with --destination.")
        if args.scope == "project" and args.project is None:
            raise ValueError("--project is required for project scope.")
        base = args.project.resolve() if args.scope == "project" else Path.home()
        targets = ("codex", "claude") if args.target == "both" else (args.target,)
        for target in targets:
            parent = args.destination or base / (".agents" if target == "codex" else ".claude") / "skills"
            result = install_to(parent, args.replace)
            say(f"{target}: {result['status']} -> {result['path']}")
            if result.get("backup"):
                say(f"Backup: {result['backup']}")
        say("Reopen the host session if the skill is not discovered. No host settings were changed.")
        return 0
    except (OSError, ValueError) as exc:
        say(f"StateLens install: {exc}", sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
