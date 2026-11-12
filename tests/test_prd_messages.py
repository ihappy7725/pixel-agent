"""PRD에 새로 적은 안내 문장 — 글자 하나까지 PRD와 같은지, 그 경우에 실제로 나오는지 검사."""
import datetime

import logic

TODAY = datetime.date(2026, 11, 12)


def test_messages_match_prd_wording():
    assert logic.MSG_PICK_LANGUAGE == "번역할 언어를 골라 주세요"
    assert logic.MSG_PICK_SITUATION == "상황(이메일/채팅)을 골라 주세요"
    assert logic.MSG_NO_RULES == "점검 단어 목록(data/check_rules.csv)을 찾지 못해서 인사말 · 맺음말은 점검하지 못했어요"


# F3 기준 4: 상대도 언어도 안 고르면 만들지 않는다
def test_f3_no_contact_no_language():
    assert logic.build_review_request("안녕하세요", "email", None, None) == (None, "번역할 언어를 골라 주세요")


# F4 기준 6: 2001자 · 언어 없음 · 상황 없음 → 저장되지 않는다
def test_f4_invalid_inputs_not_saved(data_dir):
    p = data_dir / "phrases.csv"
    assert logic.add_phrase(p, "a" * 2001, "en", "email", "", "", TODAY) == "1~2000자로 써 주세요"
    assert logic.add_phrase(p, "Hello.", None, "email", "", "", TODAY) == "번역할 언어를 골라 주세요"
    assert logic.add_phrase(p, "你好。", "zh", None, "", "", TODAY) == "상황(이메일/채팅)을 골라 주세요"
    assert logic.add_phrase(p, "こんにちは。", "ja", "letter", "", "", TODAY) == "상황(이메일/채팅)을 골라 주세요"
    assert not p.exists()


# F5 기준 4 · 5: 언어 없음 → 점검 안 함 / 점검 단어 없음 → '보낼 준비 완료' 안 나옴
def test_f5_no_language_and_no_rules():
    assert logic.check_email("S", "Hi", None, None, {})["error"] == "번역할 언어를 골라 주세요"
    for lang, body in [("en", "Hello"), ("zh", "你好"), ("ja", "こんにちは")]:
        r = logic.check_email("S", body, lang, "client", {})
        assert r["note"] == logic.MSG_NO_RULES and r["ready"] is False


# F4 기준 6 (화면): 상황을 안 고르고 저장하면 안내가 보이고 저장되지 않는다
def test_f4_screen_situation_not_chosen(data_dir):
    from streamlit.testing.v1 import AppTest
    from conftest import ROOT

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
    at.run()
    at.text_area(key="p_text").input("Hello.")
    at.radio(key="p_language").set_value("en")
    at.button(key="p_save").click()
    at.run()
    assert "상황(이메일/채팅)을 골라 주세요" in [e.value for e in at.tabs[3].error]
    assert not (data_dir / "phrases.csv").exists()
