"""F2 AI 번역 · 다듬기 · F3 검수 요청문 — PRD 완료 기준 검사.

진짜 Gemini는 부르지 않아요 (conftest.py 가 막아 둠). AI가 필요한 곳은 가짜 응답으로 시험해요.
"""
import urllib.error

from streamlit.testing.v1 import AppTest

import ai
import logic
from conftest import ROOT

APP = str(ROOT / "app.py")
CONTACTS = (
    "id,name,relation,language,formality\n"
    "1,Emily Carter,client,en,formal\n"
    "2,Jake,friend,en,casual\n"
    "3,王小明,boss,zh,formal\n"
    "5,佐藤健,client,ja,formal\n"
)


def run_app(data_dir, contacts=CONTACTS):
    if contacts is not None:
        (data_dir / "contacts.csv").write_text(contacts, encoding="utf-8")
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def fake_ai(monkeypatch, answer):
    """ai.translate 를 가짜로 바꾸고, 받은 요청을 기록해요."""
    sent = []

    def fake(prompt):
        sent.append(prompt)
        return answer

    monkeypatch.setattr(ai, "translate", fake)
    return sent


def translate_on_screen(at, source, contact="", language=None):
    at.text_area(key="t_source").input(source)
    at.selectbox(key="t_contact").set_value(contact)
    at.run()
    if language:
        at.radio(key="t_language").set_value(language)
    at.button(key="t_go").click()
    at.run()
    return at


def tab(at, n):
    return at.tabs[n]


# ================================================================ F2

# ---------- 완료 기준 1: 원문(1~2000자) + 상대 → 그 상대의 언어로 결과, 결과 칸에서 고칠 수 있다

def test_f2_contact_language_and_formality_go_to_ai(monkeypatch, data_dir):
    sent = fake_ai(monkeypatch, "尊敬的王经理，报告已附上。")
    at = translate_on_screen(run_app(data_dir), "팀장님, 보고서 첨부합니다.", contact="3")
    assert "중국어" in sent[0] and "격식: 격식" in sent[0] and "상사" in sent[0]
    assert at.text_area(key="t_result").value == "尊敬的王经理，报告已附上。"


def test_f2_result_can_be_edited(monkeypatch, data_dir):
    fake_ai(monkeypatch, "Hi Jake.")
    at = translate_on_screen(run_app(data_dir), "안녕 제이크.", contact="2")
    at.text_area(key="t_result").input("Hey Jake!")
    at.run()
    assert at.text_area(key="t_result").value == "Hey Jake!"


def test_f2_2000_chars_accepted():
    assert logic.validate_source("가" * 2000, "en") is None
    assert logic.validate_source("가", "ja") is None


def test_f2_result_not_saved_automatically(monkeypatch, data_dir):
    fake_ai(monkeypatch, "Hello.")
    translate_on_screen(run_app(data_dir), "안녕하세요.", contact="1")
    assert not (data_dir / "phrases.csv").exists()  # CLAUDE.md 6번: AI 결과는 초안


def test_f2_save_button_saves_to_phrases(monkeypatch, data_dir):
    fake_ai(monkeypatch, "Thank you for your reply.")
    at = translate_on_screen(run_app(data_dir), "답장 감사합니다.", contact="1")
    at.button(key="t_save").click()
    at.run()
    rows = logic.load_phrases(data_dir / "phrases.csv")
    assert rows[0]["text"] == "Thank you for your reply."
    assert rows[0]["contact_id"] == "1" and rows[0]["language"] == "en"
    assert rows[0]["source_ko"] == "답장 감사합니다."
    assert "보관함에 저장했어요!" in [s.value for s in tab(at, 1).success]


# ---------- 완료 기준 2: 원문이 비었거나 2001자 이상이면 AI에 보내지 않고 "1~2000자로 써 주세요"

def test_f2_empty_or_too_long_not_sent(monkeypatch, data_dir):
    sent = fake_ai(monkeypatch, "x")
    for source in ["", "   ", "가" * 2001]:
        at = translate_on_screen(run_app(data_dir), source, contact="1")
        assert "1~2000자로 써 주세요" in [e.value for e in tab(at, 1).error]
    assert sent == []


# ---------- 완료 기준 3: 키 없음 · 한도 초과 · 인터넷 끊김 → 앱이 꺼지지 않고 안내

def test_f2_no_key_returns_none():
    assert ai.has_key() is False
    assert ai.translate("아무 요청") is None  # _send 를 부르지 않고 바로 None


def test_f2_network_or_quota_error_returns_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    for err in [urllib.error.URLError("끊김"), urllib.error.HTTPError("u", 429, "한도 초과", {}, None),
                TimeoutError(), ValueError("이상한 응답")]:
        def boom(*a, _err=err, **k):
            raise _err
        monkeypatch.setattr(ai, "_send", boom)
        assert ai.translate("요청") is None


def test_f2_strange_answer_returns_none(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setattr(ai, "_send", lambda *a, **k: {"candidates": []})
    assert ai.translate("요청") is None


def test_f2_key_goes_in_header_not_url(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    seen = {}

    def fake_send(url, body, key):
        seen.update(url=url, key=key)
        return {"candidates": [{"content": {"parts": [{"text": "Hello."}]}}]}

    monkeypatch.setattr(ai, "_send", fake_send)
    assert ai.translate("요청") == "Hello."
    assert "test-key-not-real" not in seen["url"] and seen["key"] == "test-key-not-real"


def test_f2_key_read_from_env_file(monkeypatch, tmp_path):
    env = tmp_path / "test.env"
    env.write_text("# 테스트용\nGEMINI_API_KEY=from-file-not-real\n", encoding="utf-8")
    monkeypatch.setenv("BRIDGENOTE_ENV_FILE", str(env))
    assert ai.has_key() is True


def test_f2_screen_ai_down_message(monkeypatch, data_dir):
    fake_ai(monkeypatch, None)
    at = translate_on_screen(run_app(data_dir), "안녕하세요.", contact="1")
    assert not at.exception
    assert "지금은 AI를 쓸 수 없어요 — 검수 요청문으로 이어서 해 보세요" in [e.value for e in tab(at, 1).error]


# ---------- 완료 기준 4 (✍️ 내 기준): 결과 문장 수가 원문보다 2개 이상 많으면 경고

def test_f2_sentence_count_three_languages():
    assert logic.count_sentences("Hi. How are you? Great!") == 3
    assert logic.count_sentences("你好。谢谢！再见？") == 3
    assert logic.count_sentences("こんにちは。ありがとう！") == 2
    assert logic.count_sentences("문장부호 없는 채팅") == 1  # 부호가 없으면 1문장
    assert logic.count_sentences("") == 0
    assert logic.count_sentences("매출이 3.5억 늘었어요.") == 1  # 숫자 사이 점은 문장 끝이 아님


def test_f2_verbose_plus_two_warns_plus_one_not():
    src = "회의 시간 바뀌었어."
    assert logic.is_too_verbose(src, "The meeting time changed. Sorry. Please check.")  # +2 (en)
    assert not logic.is_too_verbose(src, "The meeting time changed. Sorry.")  # +1
    assert logic.is_too_verbose(src, "会议时间改了。不好意思。请确认。")  # zh
    assert logic.is_too_verbose(src, "会議の時間が変わりました。すみません。ご確認ください。")  # ja


def test_f2_screen_verbose_warning(monkeypatch, data_dir):
    fake_ai(monkeypatch, "Dear Emily. I hope you are well. The meeting moved. Thank you.")
    at = translate_on_screen(run_app(data_dir), "회의가 옮겨졌어요.", contact="1")
    assert "원문보다 길어졌어요, 줄여 볼까요?" in [w.value for w in tab(at, 1).warning]


def test_f2_screen_no_warning_when_short(monkeypatch, data_dir):
    fake_ai(monkeypatch, "The meeting moved.")
    at = translate_on_screen(run_app(data_dir), "회의가 옮겨졌어요.", contact="1")
    assert not tab(at, 1).warning


# ---------- 완료 기준 5: 상대 없음 → 언어 직접 · 격식 보통 / 언어도 없으면 보내지 않음

def test_f2_no_contact_no_language_not_sent(monkeypatch, data_dir):
    sent = fake_ai(monkeypatch, "x")
    at = translate_on_screen(run_app(data_dir), "안녕하세요.")
    assert "번역할 언어를 골라 주세요" in [e.value for e in tab(at, 1).error]
    assert sent == []


def test_f2_no_contact_uses_language_and_normal(monkeypatch, data_dir):
    sent = fake_ai(monkeypatch, "こんにちは。")
    translate_on_screen(run_app(data_dir), "안녕하세요.", language="ja")
    assert "일본어" in sent[0] and "격식: 보통" in sent[0] and "관계: 지정 안 함" in sent[0]


def test_f2_prompt_has_two_rules():
    p = logic.build_ai_prompt("안녕", "en", "formal", "client")
    assert "원문에 없는 내용을 덧붙이지 말 것" in p and "상대의 격식에 맞출 것" in p


# ================================================================ F3

def make_request_on_screen(at, source, contact="", language=None, situation="email"):
    at.text_area(key="r_source").input(source)
    at.selectbox(key="r_contact").set_value(contact)
    at.run()
    if language:
        at.radio(key="r_language").set_value(language)
    at.radio(key="r_situation").set_value(situation)
    at.button(key="r_go").click()
    at.run()
    return at


# ---------- 완료 기준 1: 요청문에 관계 · 언어 · 격식 · 원문이 모두 들어간다

def test_f3_request_has_everything():
    contact = {"id": "3", "name": "王小明", "relation": "boss", "language": "zh", "formality": "formal"}
    text, err = logic.build_review_request("보고서 첨부합니다.", "email", contact)
    assert err is None
    for part in ["관계: 상사", "언어: 중국어", "격식: 격식", "상황: 이메일", "보고서 첨부합니다."]:
        assert part in text
    assert "원문에 없는 내용을 덧붙이지 말 것" in text


def test_f3_three_languages():
    for lang, name in [("en", "영어"), ("zh", "중국어"), ("ja", "일본어")]:
        text, _ = logic.build_review_request("안녕", "chat", None, lang)
        assert f"언어: {name}" in text


def test_f3_screen_shows_request(data_dir):
    at = make_request_on_screen(run_app(data_dir), "내일 미팅 잘 부탁드립니다.", contact="5", situation="chat")
    code = tab(at, 2).code[0].value
    assert "佐藤健" in code and "언어: 일본어" in code and "상황: 채팅" in code


# ---------- 완료 기준 2: 원문이 비면 만들지 않고 "검수할 문장을 넣어 주세요"

def test_f3_empty_source(data_dir):
    assert logic.build_review_request("  ", "email", None, "en") == (None, "검수할 문장을 넣어 주세요")
    at = make_request_on_screen(run_app(data_dir), "", contact="1")
    assert "검수할 문장을 넣어 주세요" in [e.value for e in tab(at, 2).error]
    assert not tab(at, 2).code


# ---------- 완료 기준 3: 상대를 안 고르면 "보통" 격식 + "상대: 지정 안 함"

def test_f3_no_contact_normal_and_not_specified(data_dir):
    at = make_request_on_screen(run_app(data_dir), "고마워!", language="en", situation="chat")
    code = tab(at, 2).code[0].value
    assert "상대: 지정 안 함" in code and "격식: 보통" in code


def test_f3_works_with_zero_contacts(data_dir):
    at = make_request_on_screen(run_app(data_dir, contacts=None), "고마워!", language="zh")
    assert not at.exception
    assert "상대: 지정 안 함" in tab(at, 2).code[0].value
