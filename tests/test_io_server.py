import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from frostlens.io import fingerprint, read_csv, write_csv
from frostlens.server import Handler, check_virtual_history, dispatch, options


class DataContractTests(unittest.TestCase):
    def test_csv_roundtrip_preserves_values_and_fingerprint(self):
        from frostlens.core import case_rows
        rows = case_rows("narrow")
        parsed = read_csv("\ufeff" + write_csv(rows))
        self.assertEqual(parsed, rows)
        self.assertEqual(fingerprint(parsed), fingerprint(rows))

    def test_csv_rejects_missing_duplicate_and_unknown_headers(self):
        for text in (
            "te_c,tc_c\n-35,35\n",
            "te_c,te_c,tc_c,tm_c,load_kw,power_kw,sigma_kw\n-35,-35,35,-10,8,4,.1\n",
            "te_c,tc_c,tm_c,load_kw,power_kw,sigma_kw,unexpected\n-35,35,-10,8,4,.1,1\n",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                read_csv(text)

    def test_csv_rejects_extra_values_and_empty_required_values(self):
        header = "te_c,tc_c,tm_c,load_kw,power_kw,sigma_kw\n"
        for row in ("-35,35,-10,8,4,.1,extra", "-35,35,-10,8,,.1"):
            with self.assertRaises(ValueError):
                read_csv(header + row)

    def test_csv_optional_channels_can_be_blank(self):
        header = "te_c,tc_c,tm_c,load_kw,power_kw,sigma_kw,low_power_kw,sigma_low_kw\n"
        self.assertNotIn("low_power_kw", read_csv(header + "-35,35,-10,8,4,.1,,")[0])

    def test_fingerprint_ignores_key_order_but_changes_with_data(self):
        self.assertEqual(fingerprint([{"a": 1, "b": 2}]), fingerprint([{"b": 2, "a": 1}]))
        self.assertNotEqual(fingerprint([{"a": 1}]), fingerprint([{"a": 2}]))

    def test_invalid_budget_and_mode_are_rejected(self):
        for budget in (True, 0, 6, "3", 2.5):
            with self.assertRaises(ValueError):
                options({"budget": budget})
        with self.assertRaises(ValueError):
            options({"sensor_mode": "unknown"})

    def test_virtual_history_cannot_mix_imported_and_synthetic_data(self):
        from frostlens.core import case_rows, virtual_measurement
        rows = case_rows("narrow")
        self.assertEqual(check_virtual_history("narrow", rows), len(rows))
        point = {key: rows[0][key] for key in ("te_c", "tc_c", "tm_c", "load_kw")}
        extra = virtual_measurement("narrow", point, index=len(rows))
        self.assertEqual(check_virtual_history("narrow", [*rows, extra]), len(rows) + 1)
        altered = [dict(row) for row in rows]
        altered[0]["power_kw"] += 0.1
        with self.assertRaises(ValueError):
            check_virtual_history("narrow", altered)
        changed_extra = dict(extra, power_kw=extra["power_kw"] + 0.1)
        with self.assertRaises(ValueError):
            check_virtual_history("narrow", [*rows, changed_extra])

    def test_import_is_marked_user_even_if_it_contains_example_values(self):
        from frostlens.core import case_rows
        report = dispatch("/api/import", {"csv": write_csv(case_rows("narrow")), "budget": 1})
        self.assertEqual(report["provenance"]["kind"], "user")
        self.assertIsNone(report["provenance"]["case_id"])
        self.assertEqual(report["provenance"]["data_sha256"], fingerprint(report["rows"]))
        json.dumps(report, allow_nan=False)


class HTTPBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=20)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = (response.status, response.read(), dict(response.getheaders()))
        conn.close()
        return result

    def test_only_public_assets_are_served(self):
        for path in ("/../pyproject.toml", "/%2e%2e/server.py", "/server.py", "/.git/config"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_cross_origin_and_wrong_host_are_rejected(self):
        self.assertEqual(self.request("GET", "/api/cases", headers={"Host": "malicious.example"})[0], 403)
        self.assertEqual(self.request("POST", "/api/analyze", "{}", {"Origin": "https://other.example", "Content-Type": "application/json"})[0], 403)

    def test_requests_must_be_bounded_strict_json(self):
        self.assertEqual(self.request("POST", "/api/analyze", "{}")[0], 415)
        for data in ("{", "[]", '{"budget": NaN}', '{"budget": true}'):
            with self.subTest(data=data):
                self.assertEqual(self.request("POST", "/api/analyze", data, {"Content-Type": "application/json"})[0], 400)
        status, _, _ = self.request("POST", "/api/analyze", "", {"Content-Type": "application/json", "Content-Length": "1048577"})
        self.assertEqual(status, 413)

    def test_sample_download_has_reproducible_data(self):
        from frostlens.core import case_rows
        status, data, headers = self.request("GET", "/api/sample.csv")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(read_csv(data.decode("utf-8-sig")), case_rows("narrow"))


if __name__ == "__main__":
    unittest.main()
