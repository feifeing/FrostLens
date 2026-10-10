"""Small loopback-only application server, with no runtime web dependencies."""

from datetime import datetime, timezone
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit
import json
import mimetypes
import webbrowser

from . import __version__
from .io import MAX_ROWS, canonical_json, fingerprint, read_csv, write_csv

WEB_ROOT = Path(__file__).parent / "web"
MAX_BODY = 1_048_576
COMPUTE_LOCK = Lock()
INPUT_FIELDS = ("te_c", "tc_c", "tm_c", "load_kw")


def _core():
    from . import core
    return core


def options(payload):
    mode = payload.get("sensor_mode", "power")
    budget = payload.get("budget", 3)
    if mode not in ("power", "split"):
        raise ValueError("测量方式必须是 power 或 split。")
    if isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= 5:
        raise ValueError("实验预算必须是 1 到 5 之间的整数。")
    return mode, budget


@lru_cache(maxsize=8)
def _cached_analysis(rows_json, mode, budget, bounds_json):
    return canonical_json(_core().analyze(json.loads(rows_json), sensor_mode=mode, budget=budget, bounds=json.loads(bounds_json)))


def build_report(rows, mode="power", budget=3, case_id=None, bounds=None):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError(f"数据必须为 1 到 {MAX_ROWS} 行的列表。")
    rows = _core().validate_rows(rows, sensor_mode=mode)
    with COMPUTE_LOCK:
        report = json.loads(_cached_analysis(canonical_json(rows), mode, budget, canonical_json(bounds)))
    report["provenance"] = {
        "kind": "synthetic" if case_id else "user",
        "case_id": case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_sha256": fingerprint(report["rows"]),
        "software_version": __version__,
    }
    return report


def _same_row(left, right):
    return set(left) == set(right) and all(abs(float(left[key]) - float(right[key])) <= 1e-9 for key in left)


def check_virtual_history(case_id, rows):
    """Never silently relabel user measurements as generated measurements."""
    core = _core()
    initial = core.case_rows(case_id)
    if not isinstance(rows, list) or not len(initial) <= len(rows) <= MAX_ROWS:
        raise ValueError("虚拟实验需要完整的示例数据，请重新载入示例。")
    for actual, expected in zip(rows, initial):
        if not isinstance(actual, dict) or not _same_row(actual, expected):
            raise ValueError("示例数据已被改动；自有数据不能追加虚拟测量。")
    for index, row in enumerate(rows[len(initial):]):
        point = {key: row[key] for key in INPUT_FIELDS}
        expected = core.virtual_measurement(case_id, point, index=len(initial) + index)
        if not _same_row(row, expected):
            raise ValueError("虚拟测量记录不匹配，请重新载入示例。")
    return len(rows)


def dispatch(path, payload):
    if not isinstance(payload, dict):
        raise ValueError("请求内容必须是 JSON 对象。")
    mode, budget = options(payload)
    core = _core()
    if path == "/api/import":
        return build_report(read_csv(payload.get("csv")), mode, budget, bounds=payload.get("bounds"))
    if path == "/api/experiment":
        case_id = payload.get("case_id")
        rows = payload.get("rows")
        index = check_virtual_history(case_id, rows)
        if len(rows) >= MAX_ROWS:
            raise ValueError(f"已达到 {MAX_ROWS} 行上限；可导出当前结果或重置示例。")
        row = core.virtual_measurement(case_id, payload.get("point"), index=index)
        return build_report([*rows, row], mode, budget, case_id, payload.get("bounds"))
    if path == "/api/analyze":
        if "rows" in payload:
            case_id = payload.get("case_id")
            rows = payload["rows"]
            if case_id:
                check_virtual_history(case_id, rows)
            return build_report(rows, mode, budget, case_id, payload.get("bounds"))
        case_id = payload.get("case_id", "narrow")
        return build_report(core.case_rows(case_id), mode, budget, case_id, payload.get("bounds"))
    raise ValueError("不存在此分析接口。")


class Handler(BaseHTTPRequestHandler):
    server_version = "FrostLens/" + __version__

    def log_message(self, format, *args):
        # Avoid logging local CSV contents, query strings, and platform paths.
        pass

    def send_bytes(self, status, data, content_type, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, data):
        self.send_bytes(status, canonical_json(data).encode("utf-8"), "application/json; charset=utf-8")

    def trusted_request(self):
        expected = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
        host = self.headers.get("Host", "")
        if host not in expected:
            self.send_json(403, {"error": "此服务仅供本机访问。"})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{host}":
            self.send_json(403, {"error": "请在本机 FrostLens 页面中发起请求。"})
            return False
        return True

    def do_GET(self):
        if not self.trusted_request():
            return
        path = urlsplit(self.path).path
        if path == "/api/cases":
            self.send_json(200, {"cases": _core().catalog()})
            return
        if path == "/api/sample.csv":
            data = write_csv(_core().case_rows("narrow")).encode("utf-8-sig")
            self.send_bytes(200, data, "text/csv; charset=utf-8", "frostlens-synthetic-sample.csv")
            return
        # Flat public assets only; never expose source, data or arbitrary disk paths.
        name = "index.html" if path == "/" else path.removeprefix("/")
        if "/" in name or "\\" in name or name.startswith(".") or Path(name).suffix not in {".html", ".css", ".js", ".svg", ".png", ".ico"}:
            self.send_json(404, {"error": "页面不存在。"})
            return
        asset = WEB_ROOT / name
        if not asset.is_file():
            self.send_json(404, {"error": "文件不存在。"})
            return
        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if Path(name).suffix == ".js":
            kind = "text/javascript"
        self.send_bytes(200, asset.read_bytes(), kind + "; charset=utf-8")

    def do_POST(self):
        if not self.trusted_request():
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "请求需使用 application/json。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                self.send_json(413, {"error": "请求大小需在 1 字节到 1 MB 之间。"})
                return
            data = self.rfile.read(length).decode("utf-8")
            def reject_constant(value):
                raise ValueError("数据不能包含 NaN 或 Infinity。")
            payload = json.loads(data, parse_constant=reject_constant)
            report = dispatch(urlsplit(self.path).path, payload)
            self.send_json(200, report)
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception:
            self.send_json(500, {"error": "本次计算未能完成。请检查工况，或在命令行运行分析查看详细错误。"})


def serve(port=8765, open_browser=False):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"FrostLens {__version__}  |  {url}", flush=True)
    print("Data stays on this computer. Press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
