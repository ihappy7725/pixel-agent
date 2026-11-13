"""내 컴퓨터에서 웹 배포판을 미리 보는 서버 (Vercel 과 같은 모양).

실행: python3 dev_server.py   →   http://localhost:3000
- public/ 의 화면 파일을 보여 주고, /api/* 는 webapi.handle 로 넘겨요.
- 내 컴퓨터 주소(localhost)에서만 열려요.
"""
import datetime
import functools
import http.server
import json
import pathlib

import webapi
from api.index import today_kst

ROOT = pathlib.Path(__file__).resolve().parent
PORT = int(__import__("os").environ.get("PORT") or 3000)


class DevHandler(http.server.SimpleHTTPRequestHandler):
    def _api(self, method):
        length = int(self.headers.get("content-length") or 0)
        body = {} if method == "POST" else None
        if length:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                body = None
        status, payload = webapi.handle(method, self.path.split("?")[0], body, "local", today_kst())
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._api("GET")
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._api("POST")
        self.send_error(404)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    handler = functools.partial(DevHandler, directory=str(ROOT / "public"))
    print(f"BridgeNote 웹 배포판 미리 보기: http://localhost:{PORT}")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
