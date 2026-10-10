import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CliEncodingTests(unittest.TestCase):
    def run_cli(self, *args, encoding="cp1252"):
        return subprocess.run(
            [sys.executable, "-m", "frostlens", *map(str, args)],
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": encoding},
            capture_output=True,
            text=True,
            encoding=encoding,
            timeout=60,
        )

    def test_demo_succeeds_with_legacy_stdout_and_unicode_output_path(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "résumé-实验" / "报告.json"
            result = self.run_cli("demo", "--budget", "1", "--output", output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            # Both the JSON contents and the actual filename remain Unicode.
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["n"], 12)
            self.assertEqual(len(report["rows"]), 12)
            self.assertEqual(len(report["provenance"]["data_sha256"]), 64)
            self.assertTrue(any(ord(char) > 255 for char in report["summary"]["message"]))
            self.assertIn("résumé-", result.stdout)  # Encodable characters are preserved.
            for value in (str(output.resolve()), report["summary"]["message"]):
                escaped = value.encode("cp1252", errors="backslashreplace").decode("cp1252")
                self.assertIn(escaped, result.stdout)
            self.assertNotIn("Traceback", result.stdout)

    def test_utf8_stdout_preserves_chinese_messages_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "报告.json"
            result = self.run_cli("demo", "--budget", "1", "--output", output, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn(str(output.resolve()), result.stdout)
            self.assertIn(report["summary"]["message"], result.stdout)
            self.assertEqual(result.stderr, "")

    def test_csv_validation_error_is_reported_with_legacy_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "错误.csv"
            output = Path(directory) / "报告.json"
            source.write_text("te_c\n-35\n", encoding="utf-8")
            result = self.run_cli("analyze", source, "--output", output)
            self.assertEqual(result.returncode, 1)
            self.assertIn("FrostLens: CSV", result.stderr)
            self.assertIn("缺少列".encode("cp1252", errors="backslashreplace").decode("cp1252"), result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse(output.exists())

    def test_missing_unicode_file_reports_path_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "不存在.csv"
            result = self.run_cli("analyze", source, "--output", Path(directory) / "报告.json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("FrostLens:", result.stderr)
            self.assertIn("不存在.csv".encode("cp1252", errors="backslashreplace").decode("cp1252"), result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_unicode_argument_error_uses_normal_exit_status(self):
        result = self.run_cli("--不存在")
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments:", result.stderr)
        self.assertIn("--不存在".encode("cp1252", errors="backslashreplace").decode("cp1252"), result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
