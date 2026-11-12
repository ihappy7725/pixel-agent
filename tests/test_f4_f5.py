"""F4 보관함 · F5 보내기 전 점검 — PRD 완료 기준 검사. 진짜 data/ 는 쓰지 않아요."""
import datetime

from streamlit.testing.v1 import AppTest

import logic
from conftest import ROOT

APP = str(ROOT / "app.py")
TODAY = datetime.date(2026, 11, 12)
CONTACTS = (
    "id,name,relation,language,formality\n"
    "1,Emily Carter,client,en,formal\n"
    "2,Jake,friend,en,casual\n"
    "3,王小明,boss,zh,formal\n"
    "5,佐藤健,client,ja,formal\n"
)
RULES = """language,type,word
en,greeting,Dear
en,greeting,Hi
en,greeting,Hello
en,closing,Best regards
en,closing,Thanks
en,casual,gonna
en,casual,wanna
en,casual,lol
en,casual,btw
zh,greeting,尊敬的
zh,greeting,您好
zh,greeting,你好
zh,closing,此致敬礼
zh,closing,谢谢
zh,closing,祝好
zh,casual,哈哈
zh,casual,啥
zh,casual,咋
ja,greeting,様
ja,greeting,お世話になっております
ja,closing,よろしくお願いいたします
ja,closing,敬具
ja,casual,マジ
ja,casual,やばい
ja,casual,(笑)
"""


def setup(data_dir, contacts=CONTACTS, phrases=None, rules=RULES):
    if contacts is not None:
        (data_dir / "contacts.csv").write_text(contacts, encoding="utf-8")
    if phrases is not None:
        (data_dir / "phrases.csv").write_text(phrases, encoding="utf-8")
    if rules is not None:
        (data_dir / "check_rules.csv").write_text(rules, encoding="utf-8")


def run_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def rules_dict():
    import io, csv
    out = {}
    for r in csv.DictReader(io.StringIO(RULES)):
        out.setdefault(r["language"], {}).setdefault(r["type"], []).append(r["word"])
    return out


# ================================================================ F4

def phrases_path(data_dir):
    return data_dir / "phrases.csv"


# ---------- 완료 기준 1: 1~2000자 + 태그로 저장하면 맨 위 (같은 날이면 나중 것이 위)

def test_f4_saved_on_top_same_day_later_first(data_dir):
    p = phrases_path(data_dir)
    assert logic.add_phrase(p, "First.", "en", "email", "1", "첫째", TODAY) is None
    assert logic.add_phrase(p, "第二。", "zh", "chat", "", "", TODAY) is None
    assert logic.add_phrase(p, "あ" * 2000, "ja", "email", "5", "", TODAY) is None
    assert [r["id"] for r in logic.load_phrases(p)] == ["3", "2", "1"]


def test_f4_newer_date_above_older(data_dir):
    p = phrases_path(data_dir)
    logic.add_phrase(p, "Newer.", "en", "chat", "", "", TODAY)
    logic.add_phrase(p, "Older.", "en", "chat", "", "", TODAY - datetime.timedelta(days=3))
    assert [r["text"] for r in logic.load_phrases(p)] == ["Newer.", "Older."]


def test_f4_screen_save(data_dir):
    setup(data_dir)
    at = run_app()
    at.text_area(key="p_text").input("See you at 7!")
    at.selectbox(key="p_contact").set_value("2")
    at.radio(key="p_situation").set_value("chat")
    at.button(key="p_save").click()
    at.run()
    assert "저장했어요!" in [s.value for s in at.tabs[3].success]
    row = logic.load_phrases(phrases_path(data_dir))[0]
    assert (row["text"], row["language"], row["situation"], row["contact_id"]) == ("See you at 7!", "en", "chat", "2")


# ---------- 완료 기준 2: 빈 문장은 저장되지 않고 "저장할 문장을 넣어 주세요"

def test_f4_empty_not_saved(data_dir):
    p = phrases_path(data_dir)
    assert logic.add_phrase(p, "", "en", "email", "", "", TODAY) == "저장할 문장을 넣어 주세요"
    assert logic.add_phrase(p, "   ", "en", "email", "", "", TODAY) == "저장할 문장을 넣어 주세요"
    assert logic.add_phrase(p, "a" * 2001, "en", "email", "", "", TODAY) == logic.MSG_SOURCE_LENGTH
    assert not p.exists()


def test_f4_append_only_and_backup(data_dir):
    p = phrases_path(data_dir)
    logic.add_phrase(p, "One.", "en", "email", "", "", TODAY)
    before = p.read_bytes()
    logic.add_phrase(p, "Two.", "en", "email", "", "", TODAY)
    assert p.read_bytes().startswith(before)
    assert (data_dir / "backup" / "phrases-2026-11-12.csv").read_bytes() == before


# ---------- 완료 기준 3: 0개면 "첫 문장을 저장해 보세요", 검색 0개면 "찾는 문장이 없어요"

def test_f4_empty_box_message(data_dir):
    setup(data_dir)
    at = run_app()
    assert not at.exception
    assert "첫 문장을 저장해 보세요" in [i.value for i in at.tabs[3].info]


def test_f4_no_results_message(data_dir):
    setup(data_dir, phrases="id,date,text,language,situation,contact_id,source_ko\n1,2026-11-10,Hello.,en,chat,2,안녕\n")
    at = run_app()
    at.text_input(key="q_word").input("없는단어")
    at.run()
    assert "찾는 문장이 없어요" in [i.value for i in at.tabs[3].info]


# ---------- 완료 기준 4 (✍️ 내 기준): 단어 · 상대로 찾기, 검색칸이 비면 전체

SAMPLE = [
    {"id": "1", "text": "See you at the Meeting.", "source_ko": "회의에서 봐요", "contact_id": "1"},
    {"id": "2", "text": "明天的会议改到下午三点了。", "source_ko": "내일 회의 3시로", "contact_id": "3"},
    {"id": "3", "text": "よろしくお願いします。", "source_ko": "", "contact_id": ""},
]


def test_f4_search_word_three_languages_and_korean():
    assert [p["id"] for p in logic.search_phrases(SAMPLE, "meeting")] == ["1"]  # 대소문자 구분 없음
    assert [p["id"] for p in logic.search_phrases(SAMPLE, "会议")] == ["2"]
    assert [p["id"] for p in logic.search_phrases(SAMPLE, "お願い")] == ["3"]
    assert [p["id"] for p in logic.search_phrases(SAMPLE, "회의")] == ["1", "2"]  # 한국어 원문에서도


def test_f4_search_by_contact_and_both():
    assert [p["id"] for p in logic.search_phrases(SAMPLE, "", "3")] == ["2"]
    assert [p["id"] for p in logic.search_phrases(SAMPLE, "회의", "1")] == ["1"]


def test_f4_empty_search_shows_all():
    assert logic.search_phrases(SAMPLE, "", "") == SAMPLE
    assert logic.search_phrases(SAMPLE, "   ", None) == SAMPLE


def test_f4_screen_search_by_contact(data_dir):
    setup(data_dir, phrases=(
        "id,date,text,language,situation,contact_id,source_ko\n"
        "1,2026-11-10,Hello Emily.,en,email,1,\n"
        "2,2026-11-11,Hey Jake!,en,chat,2,\n"
    ))
    at = run_app()
    at.selectbox(key="q_contact").set_value("2")
    at.run()
    assert list(at.tabs[3].table[0].value["문장"]) == ["Hey Jake!"]


# ---------- 완료 기준 5: contact_id 가 비었거나 없는 번호여도 깨지지 않고 "—"

def test_f4_missing_contact_shown_as_dash(data_dir):
    setup(data_dir, phrases=(
        "id,date,text,language,situation,contact_id,source_ko\n"
        "1,2026-11-10,No contact.,en,chat,,\n"
        "2,2026-11-11,Ghost contact.,en,chat,99,\n"
        "3,2026-11-12,Emily.,en,email,1,\n"
    ))
    at = run_app()
    assert not at.exception
    assert list(at.tabs[3].table[0].value["상대"]) == ["Emily Carter", "—", "—"]


# ================================================================ F5

def check(subject, body, language, relation=None):
    return logic.check_email(subject, body, language, relation, rules_dict())


# ---------- 완료 기준 1: 제목 · 인사말 · 맺음말 중 빠진 것의 이름이 보인다

def test_f5_all_present_three_languages():
    assert check("Quote", "Dear Ms. Carter,\nPlease see attached.\nBest regards,", "en")["ready"]
    assert check("报告", "尊敬的王经理，附件是报告。此致敬礼", "zh")["ready"]
    assert check("見積書", "佐藤様\nお世話になっております。\nよろしくお願いいたします。", "ja")["ready"]


def test_f5_missing_items_named():
    assert check("", "Dear Emily, ok. Thanks", "en")["missing"] == ["제목"]
    assert check("Hi", "Please see attached. Thanks", "en")["missing"] == ["인사말"]
    assert check("报告", "您好，附件是报告。", "zh")["missing"] == ["맺음말"]
    assert check("", "見積書をお送りします。", "ja")["missing"] == ["제목", "인사말", "맺음말"]


def test_f5_english_word_unit_and_case():
    # "This" · "Think" 안의 "hi"는 인사말이 아니다
    assert "인사말" in check("S", "This is it. Think about it. Thanks", "en")["missing"]
    assert "인사말" not in check("S", "dear Emily, ok. thanks", "en")["missing"]  # 대소문자 무관
    assert "맺음말" not in check("S", "Hi. BEST REGARDS", "en")["missing"]


# ---------- 완료 기준 2: 상사 · 거래처인데 피할 표현이 있으면 그 단어가 표시된다

def test_f5_casual_words_for_boss_client_three_languages():
    assert check("S", "Hi, I'm gonna send it btw. Thanks", "en", "client")["casual"] == ["gonna", "btw"]
    assert check("S", "您好，哈哈，啥时候？谢谢", "zh", "boss")["casual"] == ["哈哈", "啥"]
    assert check("S", "佐藤様 マジで助かりました(笑) 敬具", "ja", "client")["casual"] == ["マジ", "(笑)"]


def test_f5_casual_ok_for_friend():
    r = check("S", "Hi Jake, gonna be late lol. Thanks", "en", "friend")
    assert r["casual"] == [] and r["ready"]


def test_f5_casual_word_unit_in_english():
    assert check("S", "Hi, the lollipop arrived. Thanks", "en", "client")["casual"] == []  # lol ≠ lollipop


# ---------- 완료 기준 3: 본문이 비면 "점검할 글을 넣어 주세요", 문제 0개면 "보낼 준비 완료"

def test_f5_empty_body():
    assert check("Hi", "   ", "en")["error"] == "점검할 글을 넣어 주세요"


def test_f5_screen_ready_and_missing(data_dir):
    setup(data_dir)
    at = run_app()
    at.text_input(key="e_subject").input("Quotation")
    at.text_area(key="e_body").input("Dear Ms. Carter,\nPlease find the quote.\nBest regards,")
    at.selectbox(key="e_contact").set_value("1")
    at.button(key="e_go").click()
    at.run()
    assert "보낼 준비 완료" in [s.value for s in at.tabs[4].success]

    at.text_input(key="e_subject").input("")
    at.text_area(key="e_body").input("I'm gonna send it.")
    at.button(key="e_go").click()
    at.run()
    assert "빠진 항목: 제목 · 인사말 · 맺음말" in [e.value for e in at.tabs[4].error]
    assert "상사 · 거래처에게 피할 표현: gonna" in [w.value for w in at.tabs[4].warning]


def test_f5_screen_empty_body(data_dir):
    setup(data_dir)
    at = run_app()
    at.selectbox(key="e_contact").set_value("1")
    at.button(key="e_go").click()
    at.run()
    assert "점검할 글을 넣어 주세요" in [e.value for e in at.tabs[4].error]


# ---------- 완료 기준 4: 상대를 안 고르면 언어를 직접 고르고, 피할 표현은 검사하지 않는다

def test_f5_no_contact_skips_casual_check(data_dir):
    setup(data_dir)
    at = run_app()
    at.text_input(key="e_subject").input("Hey")
    at.text_area(key="e_body").input("Hi, gonna be late. Thanks")
    at.radio(key="e_language").set_value("en")
    at.button(key="e_go").click()
    at.run()
    assert not at.tabs[4].warning
    assert "보낼 준비 완료" in [s.value for s in at.tabs[4].success]


def test_f5_no_contact_no_language(data_dir):
    setup(data_dir)
    at = run_app()
    at.text_area(key="e_body").input("Hi")
    at.button(key="e_go").click()
    at.run()
    assert "번역할 언어를 골라 주세요" in [e.value for e in at.tabs[4].error]


def test_f5_missing_rules_file_does_not_crash(data_dir):
    setup(data_dir, rules=None)
    at = run_app()
    at.text_input(key="e_subject").input("S")
    at.text_area(key="e_body").input("Hello")
    at.selectbox(key="e_contact").set_value("1")
    at.button(key="e_go").click()
    at.run()
    assert not at.exception
    assert logic.MSG_NO_RULES in [i.value for i in at.tabs[4].info]
    assert not at.tabs[4].success  # 점검 못 한 게 있으면 '보낼 준비 완료'라고 하지 않는다
