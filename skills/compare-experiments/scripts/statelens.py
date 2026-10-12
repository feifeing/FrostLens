"""Portable StateLens entry point; Python standard library only."""
import argparse
import csv
import io
import json
from pathlib import Path
import sys
import webbrowser

VERSION = "0.2.0"
SKILL = Path(__file__).resolve().parents[1]


def say(text, stream=None):
    stream = sys.stdout if stream is None else stream
    try:
        stream.write(str(text) + "\n")
    except UnicodeEncodeError as exc:
        stream.write((str(text) + "\n").encode(exc.encoding, "backslashreplace").decode(exc.encoding))


class ArgumentParser(argparse.ArgumentParser):
    def _print_message(self, message, file=None):
        if message:
            say(message.rstrip("\n"), sys.stderr if file is None else file)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_dataset(path):
    path = Path(path)
    if path.stat().st_size > 20_000_000:
        raise ValueError("Dataset exceeds the 20 MB limit; select a relevant subset first.")
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Non-finite JSON: {x}")))


def csv_cell(value):
    if value is None:
        return ""
    # Keep numeric negatives numeric; neutralize only untrusted text formulas.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def comparison_csv(report):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["study", "state", "baseline", "metric", "unit", "n_baseline", "n_state",
                     "delta", "benefit", "interval_low", "interval_high", "margin", "decision", "gate"])
    for study in report["studies"]:
        for comparison in study["comparisons"]:
            for metric in comparison["metrics"]:
                interval = metric.get("interval") or [None, None]
                values = [study["id"], comparison["state_id"], comparison["baseline_id"], metric["id"],
                          metric["unit"], metric["n_baseline"], metric["n_state"], metric["delta"],
                          metric["benefit"], *interval, metric["margin"], metric["decision"], comparison["gate"]]
                writer.writerow([csv_cell(value) for value in values])
    return stream.getvalue()


def summary_markdown(report):
    def clean(value):
        return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|").replace("<", "&lt;")
    lines = [f"# {clean(report['title'])}", "", "StateLens 0.2 · exploratory comparison / 探索性比较", "",
             f"Dataset SHA-256: `{report['provenance']['sha256']}`", ""]
    for study in report["studies"]:
        lines.extend([f"## {clean(study['label'])}", "", clean(study.get("question", "")), ""])
        for comp in study["comparisons"]:
            lines.extend([f"### {clean(comp['state_id'])} vs {clean(comp['baseline_id'])}", "",
                          f"Gate: **{clean(comp['gate'])}**", ""])
            lines.extend(f"- {clean(reason)}" for reason in comp["reasons"])
            lines.extend(["", "| Metric | Change | Benefit interval | Decision |", "|---|---:|---|---|"])
            for metric in comp["metrics"]:
                delta = "missing" if metric["delta"] is None else f"{metric['delta']:.6g} {'百分点' if metric['unit'] == '%' else metric['unit']}"
                interval = metric.get("interval")
                band = "not estimated" if interval is None else f"[{interval[0]:.6g}, {interval[1]:.6g}]"
                lines.append(f"| {clean(metric['label'])} | {clean(delta)} | {band} | {clean(metric['decision'])} |")
            lines.append("")
        lines.extend(["Next evidence / 下一步证据：", "", *[f"- {clean(x)}" for x in study["next_steps"]], ""])
    lines.extend(["## Interpretation limits", "", *[f"- {clean(x)}" for x in report["provenance"]["limitations"]], ""])
    return "\n".join(lines)


def save_comparison(dataset, output_dir, draws=2000, seed=1729, source_path=None):
    from engine import compare_dataset
    from report import render_report
    output = Path(output_dir).resolve()
    names = ("report.json", "report.html", "comparison.csv", "summary.md")
    if source_path and Path(source_path).resolve() in [(output / name).resolve() for name in names]:
        raise ValueError("Output would overwrite the input; choose another output directory.")
    for name in names:
        if (output / name).is_symlink():
            raise ValueError(f"Refusing to write through output symlink: {name}")
    report = compare_dataset(dataset, draws=draws, seed=seed)
    files = {"report.json": json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
             "report.html": render_report(report), "comparison.csv": comparison_csv(report),
             "summary.md": summary_markdown(report)}
    output.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (output / name).write_text(content, encoding="utf-8")
    return report, output / "report.html"


def main(argv=None):
    parser = ArgumentParser(description="StateLens: evidence-grounded experiment state comparison")
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    intake = commands.add_parser("intake", help="Inventory and extract mixed files for the host agent")
    intake.add_argument("inputs", nargs="+", type=Path)
    intake.add_argument("--out", required=True, type=Path)
    for name in ("compare", "demo"):
        command = commands.add_parser(name, help="Compare a normalized dataset" if name == "compare" else "Explore four synthetic disciplines")
        if name == "compare":
            command.add_argument("dataset", type=Path)
        command.add_argument("--out", required=True, type=Path)
        command.add_argument("--draws", type=int, default=2000)
        command.add_argument("--seed", type=int, default=1729)
        command.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "intake":
            from intake import intake_paths
            manifest = intake_paths(args.inputs, args.out)
            say(f"Intake: {(args.out / 'intake.json').resolve()}")
            say(json.dumps(manifest["summary"], ensure_ascii=False))
            say("The host agent should map extracted evidence to dataset.json; needs_host entries remain pending.")
            return 0
        source = args.dataset if args.command == "compare" else SKILL / "assets" / "demo.json"
        report, page = save_comparison(read_dataset(source), args.out, args.draws, args.seed, source)
        say(f"Report: {page}")
        say(f"Studies: {len(report['studies'])}; dataset SHA-256: {report['provenance']['sha256']}")
        if args.open:
            webbrowser.open(page.as_uri())
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        say(f"StateLens: {exc}", sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
