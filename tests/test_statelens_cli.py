"""Exercise the shipped skill as a separate, dependency-free command."""
import importlib.util
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "compare-experiments"
CLI = SKILL / "scripts" / "statelens.py"
INSTALLER = SKILL / "scripts" / "install.py"


class StateLensDeliveryTests(unittest.TestCase):
    def test_renderer_escapes_embedded_json_and_rejects_nonfinite_values(self):
        spec = importlib.util.spec_from_file_location("statelens_report_test", SKILL / "scripts" / "report.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        value = {"title": '</script><img src=x onerror="alert(1)">&\u2028\u2029'}
        rendered = module.render_report(value)
        self.assertNotIn(value["title"], rendered)
        embedded = re.search(r'<script id="report-data" type="application/json">(.*?)</script>', rendered, re.S)
        self.assertIsNotNone(embedded)
        self.assertEqual(json.loads(embedded.group(1)), value)
        with self.assertRaises(ValueError):
            module.render_report({"number":float("nan")})

    def run_script(self, script, *args, cwd=None):
        return subprocess.run([sys.executable, "-S", str(script), *map(str,args)], cwd=cwd,
                              env={**os.environ, "PYTHONIOENCODING":"cp1252"},
                              capture_output=True, text=True, encoding="cp1252", timeout=45)

    def test_standalone_demo_exports_finite_report_and_html_without_site_packages(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "比较报告"
            result = self.run_script(CLI, "demo", "--out", output, "--draws", 100, cwd=folder)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((output / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(len(report["studies"]), 4)
            self.assertTrue(report["provenance"]["synthetic"])
            self.assertTrue(any(c["gate"] == "blocked" for s in report["studies"] for c in s["comparisons"]))
            html = (output / "report.html").read_text(encoding="utf-8")
            self.assertIn(report["provenance"]["sha256"], html)
            self.assertNotIn("__STATELENS_REPORT_JSON__", html)
            self.assertTrue((output / "summary.md").exists())
            self.assertTrue((output / "comparison.csv").exists())

    def test_invalid_json_duplicate_keys_and_no_overwriting_input(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "report.json"
            for text in ('{"title":"one","title":"two"}', '{"x":NaN}'):
                source.write_text(text, encoding="utf-8")
                result = self.run_script(CLI, "compare", source, "--out", Path(folder) / "output")
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse((Path(folder) / "output").exists())
            source.write_bytes((SKILL / "assets" / "demo.json").read_bytes())
            before = source.read_bytes()
            result = self.run_script(CLI, "compare", source, "--out", folder)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(source.read_bytes(), before)

    def test_install_is_portable_idempotent_and_keeps_a_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "项目" / ".agents" / "skills"
            result = self.run_script(INSTALLER, "--target", "codex", "--destination", parent)
            self.assertEqual(result.returncode, 0, result.stderr)
            installed = parent / "compare-experiments"
            result = self.run_script(installed / "scripts" / "statelens.py", "demo", "--out", Path(folder)/"report", "--draws", 100)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = self.run_script(INSTALLER, "--target", "codex", "--destination", parent)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already_installed", result.stdout)
            user_file = installed / "my-notes.txt"
            user_file.write_text("keep these notes", encoding="utf-8")
            result = self.run_script(INSTALLER, "--target", "codex", "--destination", parent)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(user_file.exists())
            result = self.run_script(INSTALLER, "--target", "codex", "--destination", parent, "--replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            backups = list((parent.parent / "statelens-backups").glob("*/my-notes.txt"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "keep these notes")

    def test_bad_unicode_argument_reports_usage_without_traceback(self):
        result = self.run_script(CLI, "--未知参数")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
