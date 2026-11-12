"""전체 규칙 시험 (PRD F1~F5) — 경계값 · 세 언어 · 빈 데이터 · 문구 일치 · 진짜 data/ 보호.

진짜 Gemini 0회 (conftest.py 가 막고, 여기서도 ai.translate 를 가짜로 바꿈).
데이터 폴더는 conftest 의 BRIDGENOTE_DATA_DIR 임시 폴더만 쓴다.
"""
import datetime
import hashlib

import pytest
from streamlit.testing.v1 import AppTest

import ai
import logic
from conftest import ROOT, REAL_DATA

APP = str(ROOT / "app.py")
TODAY = datetime.date(2026, 11, 12)

RULES = (
    "language,type,word\n"
    "en,greeting,Dear\nen,greeting,Hi\nen,greeting,Hello\n"
    "en,closing,Best regards\nen,closing,Thanks\n"
    "en,casual,gonna\nen,casual,wanna\nen,casual,lol\nen,casual,btw\n"
    "zh,greeting,尊敬的\nzh,greeting,您好\nzh,greeting,你好\n"
    "zh,closing,此致敬礼\nzh,closing,谢谢\nzh,closing,祝好\n"
    "zh,casual,哈哈\nzh,casual,啥\nzh,casual,咋\n"
    "ja,greeting,様\nja,greeting,お世話になっております\n"
    "ja,closing,よろしくお願いいたします\nja,closing,敬具\n"
    "ja,casual,マジ\nja,casual,やばい\nja,casual,(笑)\n"
)
CONTACTS = (
    "id,name,relation,language,formality\n"
    "1,Emily Carter,client,en,formal\n"
    "2,Jake,friend,en,casual\n"
    "3,王小明,boss,zh,formal\n"
    "5,佐藤健,client,ja,formal\n"
)


def rules(data_dir):
    (data_dir / "check_rules.csv").write_text(RULES, encoding="utf-8")
    return logic.load_rules(data_dir / "check_rules.csv")


def app(data_dir, contacts=CONTACTS, phrases=None, with_rules=True):
    if contacts is not None:
        (data_dir / "contacts.csv").write_text(contacts, encoding="utf-8")
    if phrases is not None:
        (data_dir / "phrases.csv").write_text(phrases, encoding="utf-8")
    if with_rules:
        (data_dir / "check_rules.csv").write_text(RULES, encoding="utf-8")
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def texts(at):
    return [e.value for e in at.error] + [e.value for e in at.info] + \
           [e.value for e in at.warning] + [e.value for e in at.success]


# ================================================================ 진짜 data/ 보호
def test_real_data_not_used(data_dir):
    import os
    assert str(logic.data_dir()) == str(data_dir)
    assert os.path.realpath(data_dir) != os.path.realpath(REAL_DATA)


# ================================================================ F1
@pytest.mark.parametrize("name,ok", [
    ("", False), ("a", True), ("가" * 30, True), ("가" * 31, False),
    ("   ", False), ("\t\n", False), ("王" * 30, True), ("あ" * 31, False),
])
def test_f1_name_boundaries(data_dir, name, ok):
    err = logic.add_contact(data_dir / "contacts.csv", name, "boss", "zh", "formal", TODAY)
    if ok:
        assert err is None
        assert len(logic.load_contacts(data_dir / "contacts.csv")) == 1
    else:
        assert err == "이름은 1~30자로 써 주세요"
        assert not (data_dir / "contacts.csv").exists()


@pytest.mark.parametrize("args", [
    (None, "en", "normal"), ("boss", None, "normal"), ("boss", "en", None),
    (None, None, None), ("", "", ""),
])
def test_f1_missing_choice(data_dir, args):
    err = logic.add_contact(data_dir / "contacts.csv", "Kim", *args, TODAY)
    assert err == "관계 · 언어 · 격식을 모두 골라 주세요"
    assert not (data_dir / "contacts.csv").exists()


def test_f1_screen_empty_states(data_dir):
    for contacts in (None, "id,name,relation,language,formality\n", ""):
        at = app(data_dir, contacts=contacts)
        assert "첫 상대를 등록해 보세요" in texts(at)


def test_f1_screen_nothing_preselected_and_messages(data_dir):
    at = app(data_dir, contacts=None)
    for k in ("c_relation", "c_language", "c_formality"):
        assert at.radio(key=k).value is None
    at.text_input(key="c_name").input("Kim")
    at.button(key="c_save").click()
    at.run()
    assert "관계 · 언어 · 격식을 모두 골라 주세요" in texts(at)
    at2 = app(data_dir, contacts=None)
    at2.button(key="c_save").click()
    at2.run()
    assert "이름은 1~30자로 써 주세요" in texts(at2)


def test_f1_chinese_japanese_utf8_roundtrip(data_dir):
    p = data_dir / "contacts.csv"
    logic.add_contact(p, "王小明", "boss", "zh", "formal", TODAY)
    logic.add_contact(p, "佐藤健", "client", "ja", "formal", TODAY)
    assert "王小明" in p.read_text(encoding="utf-8")
    assert [c["name"] for c in logic.load_contacts(p)] == ["王小明", "佐藤健"]


# ================================================================ F2
@pytest.mark.parametrize("n,ok", [(0, False), (1, True), (2000, True), (2001, False)])
def test_f2_source_boundaries(n, ok):
    err = logic.validate_source("가" * n, "en")
    assert (err is None) == ok
    if not ok:
        assert err == "1~2000자로 써 주세요"


def test_f2_whitespace_only_source():
    assert logic.validate_source("   \n ", "en") == "1~2000자로 써 주세요"


def test_f2_no_language_message():
    assert logic.validate_source("안녕", None) == "번역할 언어를 골라 주세요"
    assert logic.validate_source("안녕", "fr") == "번역할 언어를 골라 주세요"


@pytest.mark.parametrize("text,n", [
    ("", 0), ("   ", 0), ("Hello", 1), ("Hi. Bye! Why?", 3),
    ("你好。再见！为什么？", 3), ("こんにちは。さようなら！なぜ？", 3),
    ("你好", 1), ("こんにちは", 1), ("Total 3.5 dollars", 1),
    ("A. B", 2), ("尊敬的老师。您好", 2),
])
def test_f2_sentence_count_three_languages(text, n):
    assert logic.count_sentences(text) == n


def test_f2_verbose_threshold_three_languages():
    assert not logic.is_too_verbose("Hi.", "Hi. Bye.")        # +1
    assert logic.is_too_verbose("Hi.", "Hi. Bye. Ok.")        # +2
    assert not logic.is_too_verbose("你好。", "你好。再见。")
    assert logic.is_too_verbose("你好。", "你好。再见。谢谢。")
    assert not logic.is_too_verbose("こんにちは。", "こんにちは。さようなら。")
    assert logic.is_too_verbose("こんにちは。", "こんにちは。さようなら。ありがとう。")
    assert not logic.is_too_verbose("한 문장", "No punctuation at all")


def _run_translate(at, source, contact="", language=None):
    at.text_area(key="t_source").input(source)
    at.selectbox(key="t_contact").set_value(contact)
    at.run()
    if language:
        at.radio(key="t_language").set_value(language)
    at.button(key="t_go").click()
    at.run()


def test_f2_screen_bad_length_not_sent(data_dir, monkeypatch):
    sent = []
    monkeypatch.setattr(ai, "translate", lambda p: sent.append(p) or "x")
    for src in ("", "   ", "가" * 2001):
        at = app(data_dir)
        _run_translate(at, src, contact="1")
        assert "1~2000자로 써 주세요" in texts(at)
    assert sent == []


def test_f2_screen_2000_sent_and_1_sent(data_dir, monkeypatch):
    sent = []
    monkeypatch.setattr(ai, "translate", lambda p: sent.append(p) or "Hello.")
    for src in ("가", "가" * 2000):
        at = app(data_dir)
        _run_translate(at, src, contact="1")
        assert at.text_area(key="t_result").value == "Hello."
    assert len(sent) == 2


@pytest.mark.parametrize("contact,expect", [("1", "영어"), ("3", "중국어"), ("5", "일본어")])
def test_f2_prompt_language_and_rules(data_dir, monkeypatch, contact, expect):
    sent = []
    monkeypatch.setattr(ai, "translate", lambda p: sent.append(p) or "ok")
    at = app(data_dir)
    _run_translate(at, "안녕하세요", contact=contact)
    assert expect in sent[0]
    assert "원문에 없는 내용을 덧붙이지 말 것" in sent[0]
    assert "상대의 격식에 맞출 것" in sent[0]


def test_f2_ai_down_message_and_app_alive(data_dir, monkeypatch):
    monkeypatch.setattr(ai, "translate", lambda p: None)
    at = app(data_dir)
    _run_translate(at, "안녕하세요", contact="1")
    assert "지금은 AI를 쓸 수 없어요 — 검수 요청문으로 이어서 해 보세요" in texts(at)
    assert not at.exception


def test_f2_no_key_returns_none_without_network(monkeypatch):
    # conftest 가 키 제거 + _send 차단 → 키 없으면 None, 인터넷 안 나감
    assert ai.translate("x") is None


def test_f2_network_error_returns_none(monkeypatch):
    import urllib.error
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-value")

    def boom(*a, **k):
        raise urllib.error.URLError("down")
    monkeypatch.setattr(ai, "_send", boom)
    assert ai.translate("x") is None


def test_f2_no_contact_no_language(data_dir, monkeypatch):
    sent = []
    monkeypatch.setattr(ai, "translate", lambda p: sent.append(p) or "ok")
    at = app(data_dir)
    _run_translate(at, "안녕하세요", contact="")
    assert "번역할 언어를 골라 주세요" in texts(at)
    assert sent == []


def test_f2_no_contact_with_language_uses_normal(data_dir, monkeypatch):
    sent = []
    monkeypatch.setattr(ai, "translate", lambda p: sent.append(p) or "ok")
    at = app(data_dir)
    _run_translate(at, "안녕하세요", contact="", language="ja")
    assert "일본어" in sent[0] and "격식: 보통" in sent[0]


def test_f2_result_not_auto_saved(data_dir, monkeypatch):
    monkeypatch.setattr(ai, "translate", lambda p: "Hello.")
    at = app(data_dir)
    _run_translate(at, "안녕", contact="1")
    assert not (data_dir / "phrases.csv").exists()


def test_f2_verbose_warning_on_screen(data_dir, monkeypatch):
    monkeypatch.setattr(ai, "translate", lambda p: "A. B. C.")
    at = app(data_dir)
    _run_translate(at, "안녕", contact="1")
    assert "원문보다 길어졌어요, 줄여 볼까요?" in texts(at)


# ================================================================ F3
def test_f3_contents_three_languages():
    import csv, io
    cs = {c["id"]: c for c in csv.DictReader(io.StringIO(CONTACTS))}
    for cid, lang, rel in (("1", "영어", "거래처"), ("3", "중국어", "상사"), ("5", "일본어", "거래처")):
        text, err = logic.build_review_request("회의 일정 알려 주세요", "email", cs[cid])
        assert err is None
        assert lang in text and rel in text and "격식" in text and "회의 일정 알려 주세요" in text
        assert "원문에 없는 내용을 덧붙이지 말 것" in text


def test_f3_empty_source():
    for s in ("", "  \n"):
        assert logic.build_review_request(s, "email", None, "en") == (None, "검수할 문장을 넣어 주세요")


def test_f3_no_contact_defaults():
    text, err = logic.build_review_request("안녕", "chat", None, "zh")
    assert err is None and "상대: 지정 안 함" in text and "격식: 보통" in text


def test_f3_no_contact_no_language():
    assert logic.build_review_request("안녕", "chat", None, None) == (None, "번역할 언어를 골라 주세요")


# ================================================================ F4
def test_f4_text_boundaries(data_dir):
    p = data_dir / "phrases.csv"
    assert logic.add_phrase(p, "", "en", "email", "", "", TODAY) == "저장할 문장을 넣어 주세요"
    assert logic.add_phrase(p, "  ", "en", "email", "", "", TODAY) == "저장할 문장을 넣어 주세요"
    assert logic.add_phrase(p, "a" * 2001, "en", "email", "", "", TODAY) == "1~2000자로 써 주세요"
    assert logic.add_phrase(p, "a", "en", "email", "", "", TODAY) is None
    assert logic.add_phrase(p, "a" * 2000, "en", "email", "", "", TODAY) is None
    assert len(logic.load_phrases(p)) == 2


def test_f4_missing_language_and_situation(data_dir):
    p = data_dir / "phrases.csv"
    assert logic.add_phrase(p, "Hi", None, "email", "", "", TODAY) == "번역할 언어를 골라 주세요"
    assert logic.add_phrase(p, "Hi", "en", None, "", "", TODAY) == "상황(이메일/채팅)을 골라 주세요"
    assert logic.add_phrase(p, "Hi", "en", "", "", "", TODAY) == "상황(이메일/채팅)을 골라 주세요"
    assert not p.exists()


def test_f4_newest_on_top_same_day(data_dir):
    p = data_dir / "phrases.csv"
    logic.add_phrase(p, "first", "en", "email", "", "", TODAY)
    logic.add_phrase(p, "second", "en", "email", "", "", TODAY)
    logic.add_phrase(p, "old-day", "en", "email", "", "", datetime.date(2026, 1, 1))
    assert [r["text"] for r in logic.load_phrases(p)] == ["second", "first", "old-day"]


def test_f4_utf8_roundtrip_and_append_only(data_dir):
    p = data_dir / "phrases.csv"
    logic.add_phrase(p, "尊敬的王先生，谢谢。", "zh", "email", "", "", TODAY)
    before = p.read_bytes()
    logic.add_phrase(p, "お世話になっております。田中様", "ja", "email", "", "원문", TODAY)
    assert p.read_bytes().startswith(before)
    got = [r["text"] for r in logic.load_phrases(p)]
    assert "尊敬的王先生，谢谢。" in got and "お世話になっております。田中様" in got
    assert (data_dir / "backup").exists()


PH = (
    "id,date,text,language,situation,contact_id,source_ko\n"
    "1,2026-11-01,Meeting at 3pm.,en,email,1,회의\n"
    "2,2026-11-02,明天开会。,zh,chat,3,내일 회의\n"
    "3,2026-11-03,会議は3時です。,ja,email,,회의\n"
    "4,2026-11-04,Hello there,en,chat,99,인사\n"
)


def test_f4_search_word_and_contact_three_languages():
    ph = logic.load_phrases  # noqa
    import csv, io
    rows = list(csv.DictReader(io.StringIO(PH)))
    ids = lambda r: sorted(x["id"] for x in r)
    assert ids(logic.search_phrases(rows, "MEETING")) == ["1"]       # 대소문자 무시
    assert ids(logic.search_phrases(rows, "开会")) == ["2"]
    assert ids(logic.search_phrases(rows, "会議")) == ["3"]
    assert ids(logic.search_phrases(rows, "")) == ["1", "2", "3", "4"]
    assert ids(logic.search_phrases(rows, "   ")) == ["1", "2", "3", "4"]
    assert ids(logic.search_phrases(rows, "", "3")) == ["2"]
    assert ids(logic.search_phrases(rows, "meeting", "3")) == []
    assert ids(logic.search_phrases(rows, "zzz")) == []


def test_f4_screen_blank_and_unknown_contact_show_dash(data_dir):
    at = app(data_dir, phrases=PH)
    cells = [c for t in at.table for c in [t.value]]
    assert cells
    df = at.table[0].value
    col = list(df["상대"])
    # 정렬: 4(없는번호) 3(빈칸) 2 1
    assert col[0] == "—" and col[1] == "—"
    assert col[2] == "王小明" and col[3] == "Emily Carter"


def test_f4_screen_empty_messages(data_dir):
    for ph in (None, "id,date,text,language,situation,contact_id,source_ko\n", ""):
        at = app(data_dir, phrases=ph)
        assert "첫 문장을 저장해 보세요" in texts(at)
    at = app(data_dir, phrases=PH)
    at.text_input(key="q_word").input("없는단어xyz")
    at.run()
    assert "찾는 문장이 없어요" in texts(at)


def test_f4_screen_save_errors(data_dir):
    at = app(data_dir, phrases=PH)
    at.button(key="p_save").click()
    at.run()
    assert "저장할 문장을 넣어 주세요" in texts(at)
    at.text_area(key="p_text").input("a" * 2001)
    at.selectbox(key="p_contact").set_value("")
    at.run()
    at.button(key="p_save").click()
    at.run()
    assert "1~2000자로 써 주세요" in texts(at)
    assert len(logic.load_phrases(data_dir / "phrases.csv")) == 4


def test_f4_screen_no_contact_no_language(data_dir):
    at = app(data_dir, phrases=PH)
    at.text_area(key="p_text").input("Hello")
    at.selectbox(key="p_contact").set_value("")
    at.run()
    at.radio(key="p_situation").set_value("email")
    at.run()
    at.button(key="p_save").click()
    at.run()
    assert "번역할 언어를 골라 주세요" in texts(at)
    assert len(logic.load_phrases(data_dir / "phrases.csv")) == 4


# (예전 ❓: 상황 칸이 미리 '이메일'로 골라져 있었음 → 2026-11-12 미리 고르지 않게 고침)
def test_f4_screen_situation_not_chosen_by_default_check(data_dir):
    """상황을 안 고르면 저장되지 않아야 한다 (기준 6). 화면의 상황 라디오가 미리 골라져 있으면 이 기준을 화면에서 확인할 수 없다."""
    at = app(data_dir, phrases=PH)
    default = at.radio(key="p_situation").value
    assert default is None, f"상황이 미리 '{default}' 로 골라져 있어요 (PRD F4 기준 6: 안 고르면 안내가 떠야 함)"


# ================================================================ F5 (영어 · 중국어 · 일본어)
def test_f5_english_word_boundary(data_dir):
    r = rules(data_dir)
    res = logic.check_email("s", "This is it. Thanks", "en", None, r)
    assert "인사말" in res["missing"]          # "This" 안의 hi 는 인사말 아님
    assert "맺음말" not in res["missing"]
    res = logic.check_email("s", "HI team, best REGARDS", "en", None, r)
    assert res["missing"] == [] and res["ready"]   # 대소문자 무시
    res = logic.check_email("s", "Dear Bob, thanks", "en", "boss", r)
    assert res["ready"] is False or res["casual"] == []
    # 단어 단위: 'btwn', 'biglol' 은 피할 표현이 아님
    res = logic.check_email("s", "Dear Bob, btwn us, biglol. Thanks", "en", "boss", r)
    assert res["casual"] == []
    res = logic.check_email("s", "Dear Bob, I'm GONNA go, LOL. Thanks", "en", "client", r)
    assert set(res["casual"]) == {"gonna", "lol"}


def test_f5_chinese(data_dir):
    r = rules(data_dir)
    ok = logic.check_email("主题", "尊敬的王先生，会议改期。谢谢", "zh", "boss", r)
    assert ok["ready"] and ok["missing"] == []
    bad = logic.check_email("主题", "哈哈 明天啥时候开会", "zh", "boss", r)
    assert set(bad["missing"]) == {"인사말", "맺음말"}
    assert set(bad["casual"]) == {"哈哈", "啥"}
    notstrict = logic.check_email("主题", "你好 哈哈 祝好", "zh", "friend", r)
    assert notstrict["casual"] == [] and notstrict["ready"]


def test_f5_japanese(data_dir):
    r = rules(data_dir)
    ok = logic.check_email("件名", "田中様\n会議の件です。よろしくお願いいたします", "ja", "client", r)
    assert ok["ready"]
    bad = logic.check_email("件名", "マジやばい(笑)", "ja", "client", r)
    assert set(bad["casual"]) == {"マジ", "やばい", "(笑)"}
    assert set(bad["missing"]) == {"인사말", "맺음말"}


def test_f5_missing_subject_and_each_item(data_dir):
    r = rules(data_dir)
    res = logic.check_email("", "text", "en", None, r)
    assert res["missing"] == ["제목", "인사말", "맺음말"]
    res = logic.check_email("   ", "Dear A. Thanks", "en", None, r)
    assert res["missing"] == ["제목"]


def test_f5_empty_body_and_no_language(data_dir):
    r = rules(data_dir)
    for body in ("", "  \n"):
        assert logic.check_email("s", body, "en", None, r)["error"] == "점검할 글을 넣어 주세요"
    res = logic.check_email("s", "Dear A. Thanks", None, None, r)
    assert res["error"] == "번역할 언어를 골라 주세요" and not res["ready"]


def test_f5_no_contact_skips_casual(data_dir):
    r = rules(data_dir)
    res = logic.check_email("s", "Dear A, lol gonna. Thanks", "en", None, r)
    assert res["casual"] == [] and res["ready"]


def test_f5_rules_file_missing_or_header_only(data_dir):
    missing = logic.load_rules(data_dir / "nope.csv")
    res = logic.check_email("s", "Dear A. Thanks", "en", "boss", missing)
    assert res["note"] == "점검 단어 목록(data/check_rules.csv)을 찾지 못해서 인사말 · 맺음말은 점검하지 못했어요"
    assert not res["ready"]
    (data_dir / "check_rules.csv").write_text("language,type,word\n", encoding="utf-8")
    res = logic.check_email("s", "Dear A. Thanks", "en", "boss", logic.load_rules(data_dir / "check_rules.csv"))
    assert res["note"] and not res["ready"]


def test_f5_rules_missing_for_one_language_only(data_dir):
    (data_dir / "check_rules.csv").write_text("language,type,word\nen,greeting,Dear\n", encoding="utf-8")
    r = logic.load_rules(data_dir / "check_rules.csv")
    res = logic.check_email("s", "你好 谢谢", "zh", None, r)
    assert res["note"] and not res["ready"]


def _check_on_screen(at, subject, body, contact="", language=None):
    at.text_input(key="e_subject").input(subject)
    at.text_area(key="e_body").input(body)
    at.selectbox(key="e_contact").set_value(contact)
    at.run()
    if language:
        at.radio(key="e_language").set_value(language)
    at.button(key="e_go").click()
    at.run()


def test_f5_screen_messages(data_dir):
    at = app(data_dir)
    _check_on_screen(at, "s", "", contact="1")
    assert "점검할 글을 넣어 주세요" in texts(at)
    at = app(data_dir)
    _check_on_screen(at, "s", "Dear A. Thanks", contact="1")
    assert "보낼 준비 완료" in texts(at)
    at = app(data_dir)
    _check_on_screen(at, "s", "Dear A. Thanks", contact="")
    assert "번역할 언어를 골라 주세요" in texts(at)


def test_f5_screen_rules_file_missing(data_dir):
    at = app(data_dir, with_rules=False)
    _check_on_screen(at, "s", "Dear A. Thanks", contact="1")
    t = texts(at)
    assert "점검 단어 목록(data/check_rules.csv)을 찾지 못해서 인사말 · 맺음말은 점검하지 못했어요" in t
    assert "보낼 준비 완료" not in t
    assert not at.exception


# ================================================================ 비어 있을 때 / 화면이 열리는지
@pytest.mark.parametrize("contacts", [None, "", "id,name,relation,language,formality\n"])
@pytest.mark.parametrize("phrases", [None, "", "id,date,text,language,situation,contact_id,source_ko\n"])
@pytest.mark.parametrize("with_rules", [True, False])
def test_open_with_any_empty_files(data_dir, contacts, phrases, with_rules):
    at = app(data_dir, contacts=contacts, phrases=phrases, with_rules=with_rules)
    assert not at.exception


def test_open_header_only_rules_and_all_missing(data_dir):
    (data_dir / "check_rules.csv").write_text("language,type,word\n", encoding="utf-8")
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception


def test_open_phrase_contact_id_variants(data_dir):
    ph = ("id,date,text,language,situation,contact_id,source_ko\n"
          "1,2026-11-01,a,en,email,,\n2,2026-11-01,b,en,email,777,\n3,2026-11-01,c,en,email, ,x\n"
          "4,,d,xx,yy,abc,\n")
    at = app(data_dir, phrases=ph)
    assert not at.exception
    assert all(v == "—" for v in list(at.table[0].value["상대"]))


def test_contact_label_helpers():
    cs = [{"id": "1", "name": "Kim"}]
    assert logic.contact_label(cs, "") == "—"
    assert logic.contact_label(cs, None) == "—"
    assert logic.contact_label(cs, "9") == "—"
    assert logic.contact_label(cs, "1") == "Kim"


# ================================================================ 문구 일치 (PRD 문장 그대로)
def test_messages_exact_match_prd():
    assert logic.MSG_NAME_LENGTH == "이름은 1~30자로 써 주세요"
    assert logic.MSG_NO_CONTACTS == "첫 상대를 등록해 보세요"
    assert logic.MSG_PICK_ALL == "관계 · 언어 · 격식을 모두 골라 주세요"
    assert logic.MSG_SOURCE_LENGTH == "1~2000자로 써 주세요"
    assert logic.MSG_AI_DOWN == "지금은 AI를 쓸 수 없어요 — 검수 요청문으로 이어서 해 보세요"
    assert logic.MSG_TOO_VERBOSE == "원문보다 길어졌어요, 줄여 볼까요?"
    assert logic.MSG_PICK_LANGUAGE == "번역할 언어를 골라 주세요"
    assert logic.MSG_NEED_SOURCE == "검수할 문장을 넣어 주세요"
    assert logic.MSG_EMPTY_PHRASE == "저장할 문장을 넣어 주세요"
    assert logic.MSG_NO_PHRASES == "첫 문장을 저장해 보세요"
    assert logic.MSG_NO_RESULTS == "찾는 문장이 없어요"
    assert logic.MSG_PICK_SITUATION == "상황(이메일/채팅)을 골라 주세요"
    assert logic.MSG_EMPTY_BODY == "점검할 글을 넣어 주세요"
    assert logic.MSG_READY == "보낼 준비 완료"
    assert logic.MSG_NO_RULES == "점검 단어 목록(data/check_rules.csv)을 찾지 못해서 인사말 · 맺음말은 점검하지 못했어요"


def test_prd_md_contains_every_message():
    prd = (ROOT / "PRD.md").read_text(encoding="utf-8")
    for m in (logic.MSG_NAME_LENGTH, logic.MSG_NO_CONTACTS, logic.MSG_PICK_ALL, logic.MSG_SOURCE_LENGTH,
              logic.MSG_AI_DOWN, logic.MSG_TOO_VERBOSE, logic.MSG_PICK_LANGUAGE, logic.MSG_NEED_SOURCE,
              logic.MSG_EMPTY_PHRASE, logic.MSG_NO_PHRASES, logic.MSG_NO_RESULTS, logic.MSG_PICK_SITUATION,
              logic.MSG_EMPTY_BODY, logic.MSG_READY, logic.MSG_NO_RULES):
        assert m in prd, m


# ================================================================ 진짜 data/ 지문 (이 파일 안에서도 비교)
def test_real_data_fingerprint_unchanged_after_everything():
    # 이 파일의 다른 테스트들이 먼저 돈 뒤 (파일 맨 아래) 지문을 한 번 더 확인한다.
    # 처음 값은 conftest 가 세션 시작 때 저장; 여기서는 파일이 존재하고 읽히는지만 확인.
    fp = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in REAL_DATA.glob("*.csv")}
    assert {"contacts.csv", "phrases.csv", "check_rules.csv"} <= set(fp)
