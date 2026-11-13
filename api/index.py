"""Vercel 서버 함수 입구 — /api/* 요청을 webapi.handle 로 넘겨요."""
import datetime
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import webapi  # noqa: E402

KST = datetime.timezone(datetime.timedelta(hours=9))


def today_kst():
    """하루 횟수 제한은 한국 시간 자정에 다시 세요."""
    return datetime.datetime.now(KST).date()


def visitor_of(headers, client_address):
    """방문자 구분: Vercel 이 직접 채우는 x-real-ip 를 먼저 써요 (방문자가 바꾸기 어려움)."""
    real = (headers.get("x-real-ip") or "").strip()
    forwarded = (headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return real or forwarded or (client_address or ["?"])[0]


class handler(BaseHTTPRequestHandler):
    def _answer(self, method):
        length = int(self.headers.get("content-length") or 0)
        if length > webapi.MAX_BODY:
            return self._send(413, {"error": "보낸 글이 너무 길어요"})
        body = None
        if length:
            try:
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                body = None
        elif method == "POST":
            body = {}
        status, payload = webapi.handle(method, self.path.split("?")[0], body,
                                        visitor_of(self.headers, self.client_address), today_kst())
        self._send(status, payload)

    def do_GET(self):
        self._answer("GET")

    def do_POST(self):
        self._answer("POST")

    def _send(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # 요청 기록에 글 내용이 남지 않게
        pass
