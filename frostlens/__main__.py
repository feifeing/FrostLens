"""Run ``python -m frostlens`` or use the installed ``frostlens`` command."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__


def _write_message(message, stream):
    """Keep the stream's encoding, escaping only characters it cannot represent."""
    try:
        stream.write(message)
    except UnicodeEncodeError as exc:
        stream.write(message.encode(exc.encoding, errors="backslashreplace").decode(exc.encoding))


class _ArgumentParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if message:
            _write_message(message, sys.stderr if file is None else file)


def main(argv=None):
    parser = _ArgumentParser(description="FrostLens — find the next informative refrigeration experiment.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")
    server = commands.add_parser("serve", help="Open the local research workbench")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--open", action="store_true", help="Open your default browser")
    for name in ("analyze", "demo"):
        command = commands.add_parser(name, help="Analyze a CSV" if name == "analyze" else "Reproduce a synthetic case")
        if name == "analyze":
            command.add_argument("csv", type=Path)
        else:
            command.add_argument("--case", choices=("narrow", "wide", "drift"), default="narrow")
        command.add_argument("--sensor-mode", choices=("power", "split"), default="power")
        command.add_argument("--budget", type=int, choices=range(1, 6), default=3)
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        from .server import build_report, serve
        if args.command in (None, "serve"):
            serve(getattr(args, "port", 8765), getattr(args, "open", False))
            return 0
        from .core import case_rows
        from .io import read_csv
        if args.command == "analyze":
            rows = read_csv(args.csv.read_text(encoding="utf-8-sig"))
            case_id = None
        else:
            rows, case_id = case_rows(args.case), args.case
        report = build_report(rows, args.sensor_mode, args.budget, case_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
        _write_message(f"Report: {args.output.resolve()}\n", sys.stdout)
        _write_message(report["summary"]["message"] + "\n", sys.stdout)
        return 0
    except (ValueError, OSError, ImportError) as exc:
        _write_message(f"FrostLens: {exc}\n", sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
