"""웹 배포판(Vercel) 서버 쪽 검사 — 진짜 Gemini 는 부르지 않아요 (conftest.py 가 막아 둠)."""
import datetime
import io
import json

import pytest

import ai
import logic
import webapi

TODAY = datetime.date(2026, 11, 12)
EMILY = {"id": "1", "name": "Emily Carter", "relation": "client", "language": "en", "formality": "formal"}


@pytest.fixture(autouse=True)
def fresh_quota(monkeypatch):
    monkeypatch.setattr(webapi, "QUOTA", logic.DailyQuota())


def call(path, body=None, method="POST", visitor="v1", today=TODAY):
    return webapi.handle(method, path, body, visitor, today)


def fake_ai(monkeypatch, answer):
    sent = []
    monkeypatch.setattr(ai, "translate", lambda prompt: sent.append(prompt) or answer)
    return sent


# ---------------------------------------------------------------- 시작 데이터
def test_seed_is_fake_sample_and_options():
    status, r = call("/api/seed", method="GET")
    assert status == 200
    assert [c["name"] for c in r["contacts"]] == ["Emily Carter", "Jake", "王小明", "李娜", "佐藤健"]
    assert len(r["phrases"]) == 10 and r["phrases"][0]["id"] == "10"  # 최신이 위
    assert r["options"]["languages"] == logic.LANGUAGES
    assert r["aiLimit"] == 3 and r["aiLeft"] == 3


def test_unknown_path_and_bad_body():
    assert call("/api/nope")[0] == 404
    assert call("/api/contact", body=None)[0] == 400


# ---------------------------------------------------------------- F1 (PRD 문장 그대로)
def test_contact_rules_same_as_prd():
    assert call("/api/contact", {"name": "a" * 31, "relation": "friend", "language": "en", "formality": "casual"})[1] == \
        {"error": "이름은 1~30자로 써 주세요"}
    assert call("/api/contact", {"name": "Jake", "relation": "friend", "language": None, "formality": "casual"})[1] == \
        {"error": "관계 · 언어 · 격식을 모두 골라 주세요"}
    r = call("/api/contact", {"name": " 王小明 ", "relation": "boss", "language": "zh", "formality": "formal",
                              "contacts": [EMILY]})[1]
    assert r["contact"] == {"id": "2", "name": "王小明", "relation": "boss", "language": "zh", "formality": "formal"}


# ---------------------------------------------------------------- F2 + 횟수 제한 (PRD 7장)
def test_translate_with_contact(monkeypatch):
    sent = fake_ai(monkeypatch, "Thank you.")
    r = call("/api/translate", {"source": "감사합니다.", "contact": EMILY})[1]
    assert r["result"] == "Thank you." and r["language"] == "en" and r["verbose"] is False
    assert "영어" in sent[0] and "격식: 격식" in sent[0] and "원문에 없는 내용을 덧붙이지 말 것" in sent[0]
    assert r["aiLeft"] == 2


def test_translate_input_errors_do_not_use_quota(monkeypatch):
    sent = fake_ai(monkeypatch, "x")
    assert call("/api/translate", {"source": "", "contact": EMILY})[1]["error"] == "1~2000자로 써 주세요"
    assert call("/api/translate", {"source": "가" * 2001, "contact": EMILY})[1]["error"] == "1~2000자로 써 주세요"
    assert call("/api/translate", {"source": "안녕"})[1]["error"] == "번역할 언어를 골라 주세요"
    assert sent == [] and webapi.QUOTA.left("v1", TODAY) == 3


def test_translate_ai_down_message(monkeypatch):
    fake_ai(monkeypatch, None)
    assert call("/api/translate", {"source": "안녕", "language": "ja"})[1]["error"] == \
        "지금은 AI를 쓸 수 없어요 — 검수 요청문으로 이어서 해 보세요"


def test_translate_verbose_three_languages(monkeypatch):
    for lang, answer in [("en", "Hi. I hope you are well. Thanks."), ("zh", "你好。希望你一切都好。谢谢。"),
                         ("ja", "こんにちは。お元気ですか。ありがとう。")]:
        fake_ai(monkeypatch, answer)
        assert call("/api/translate", {"source": "안녕", "language": lang}, visitor=lang)[1]["verbose"] is True


def test_visitor_limit_three_per_day(monkeypatch):
    sent = fake_ai(monkeypatch, "Hi.")
    for _ in range(3):
        assert "result" in call("/api/translate", {"source": "안녕", "language": "en"})[1]
    r = call("/api/translate", {"source": "안녕", "language": "en"})[1]
    assert r == {"error": "오늘 쓸 수 있는 AI 번역 3번을 다 썼어요 — 검수 요청문으로 이어서 해 보세요", "aiLeft": 0}
    assert len(sent) == 3                                    # 4번째는 AI 를 부르지 않음
    assert "result" in call("/api/translate", {"source": "안녕", "language": "en"}, visitor="v2")[1]  # 다른 방문자는 됨
    tomorrow = TODAY + datetime.timedelta(days=1)
    assert "result" in call("/api/translate", {"source": "안녕", "language": "en"}, today=tomorrow)[1]  # 다음 날 다시


def test_site_limit_per_day(monkeypatch):
    fake_ai(monkeypatch, "Hi.")
    monkeypatch.setattr(webapi, "QUOTA", logic.DailyQuota(per_visitor=3, per_site=4))
    for v in ["a", "a", "b", "b"]:
        assert "result" in call("/api/translate", {"source": "안녕", "language": "en"}, visitor=v)[1]
    assert call("/api/translate", {"source": "안녕", "language": "en"}, visitor="c")[1]["error"] == \
        "오늘 사이트 전체 AI 번역 한도를 다 썼어요 — 검수 요청문으로 이어서 해 보세요"


def test_failed_ai_calls_still_count(monkeypatch):
    fake_ai(monkeypatch, None)  # 실패를 반복해도 한도를 넘어 부르지 않게
    for _ in range(3):
        call("/api/translate", {"source": "안녕", "language": "en"})
    assert call("/api/translate", {"source": "안녕", "language": "en"})[1]["error"].startswith("오늘 쓸 수 있는")


# ---------------------------------------------------------------- F3 · F4 · F5
def test_request_and_check():
    r = call("/api/request", {"source": "고마워", "situation": "chat", "language": "zh"})[1]
    assert "상대: 지정 안 함" in r["text"] and "격식: 보통" in r["text"] and "언어: 중국어" in r["text"]
    assert call("/api/request", {"source": "", "situation": "chat", "contact": EMILY})[1] == {"error": "검수할 문장을 넣어 주세요"}
    c = call("/api/check", {"subject": "", "body": "I'm gonna send it.", "contact": EMILY})[1]
    assert c["missing"] == ["제목", "인사말", "맺음말"] and c["casual"] == ["gonna"]
    ok = call("/api/check", {"subject": "見積書", "body": "佐藤様\nお世話になっております。\n敬具", "language": "ja"})[1]
    assert ok["ready"] is True


def test_phrase_and_search():
    assert call("/api/phrase", {"text": "Hi", "language": "en", "situation": None})[1] == {"error": "상황(이메일/채팅)을 골라 주세요"}
    r = call("/api/phrase", {"text": " Hi Emily. ", "contact": EMILY, "situation": "email",
                             "phrases": [{"id": "4"}], "source_ko": "안녕"})[1]["phrase"]
    assert r == {"id": "5", "date": "2026-11-12", "text": "Hi Emily.", "language": "en", "situation": "email",
                 "contact_id": "1", "source_ko": "안녕"}
    phrases = [r, {"id": "6", "date": "2026-11-12", "text": "Ghost.", "language": "en", "situation": "chat", "contact_id": "99"}]
    s = call("/api/search", {"phrases": phrases, "contacts": [EMILY], "word": "", "contact_id": ""})[1]
    assert [p["id"] for p in s["phrases"]] == ["6", "5"] and [p["contact_name"] for p in s["phrases"]] == ["—", "Emily Carter"]
    assert call("/api/search", {"phrases": phrases, "contacts": [EMILY], "word": "emily"})[1]["phrases"][0]["id"] == "5"


def test_strange_input_never_crashes():
    for path in ["/api/contact", "/api/phrase", "/api/search", "/api/translate", "/api/request", "/api/check", "/api/verbose"]:
        status, r = call(path, {"contacts": "x", "phrases": 7, "contact": [1], "source": 5, "text": None})
        assert status == 200 and isinstance(r, dict)


# ---------------------------------------------------------------- Vercel 입구 (api/index.py)
def test_vercel_handler_end_to_end():
    from api.index import handler

    class FakeHandler(handler):
        def __init__(self, method, path, body):
            raw = json.dumps(body).encode() if body is not None else b""
            self.headers = {"content-length": str(len(raw)), "x-forwarded-for": "1.2.3.4, 10.0.0.1"}
            self.rfile, self.wfile, self.path, self.client_address = io.BytesIO(raw), io.BytesIO(), path, ("9.9.9.9", 0)
            self.sent = []

        def send_response(self, code): self.sent.append(code)
        def send_header(self, *a): pass
        def end_headers(self): pass

    h = FakeHandler("POST", "/api/request?x=1", {"source": "고마워", "situation": "chat", "language": "en"})
    h.do_POST()
    assert h.sent == [200] and "언어: 영어" in json.loads(h.wfile.getvalue())["text"]
