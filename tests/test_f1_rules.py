"""F1 상대방 카드 — 규칙 시험 (경계값 · 세 언어 · 빈 상태 · 문구). 임시 데이터 폴더만 사용."""
import datetime

import pytest
from streamlit.testing.v1 import AppTest

import logic
from conftest import ROOT

TODAY = datetime.date(2026, 11, 12)
APP = str(ROOT / "app.py")
MSG_NAME = "이름은 1~30자로 써 주세요"
MSG_EMPTY = "첫 상대를 등록해 보세요"
MSG_PICK = "관계 · 언어 · 격식을 모두 골라 주세요"


def run():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def submit(at, name, rel=None, lang=None, form=None):
    at.text_input(key="c_name").input(name)
    if rel:
        at.radio(key="c_relation").set_value(rel)
    if lang:
        at.radio(key="c_language").set_value(lang)
    if form:
        at.radio(key="c_formality").set_value(form)
    at.button(key="c_save").click()
    at.run()
    return at


def errors(at):
    return [e.value for e in at.tabs[0].error]


# ---- 기준 1: 저장되고 목록에 보인다
@pytest.mark.parametrize("name", ["가", "a" * 30, "田" * 30, "山田太郎", "王小明", "Emily Carter"])
def test_c1_valid_names_saved_in_file(data_dir, name):
    p = data_dir / "contacts.csv"
    assert logic.add_contact(p, name, "client", "ja", "formal", TODAY) is None
    assert logic.load_contacts(p)[0]["name"] == name


def test_c1_screen_save_and_list_three_languages(data_dir):
    at = run()
    for n, lang in [("Emily", "en"), ("王小明", "zh"), ("山田様", "ja")]:
        submit(at, n, "boss", lang, "formal")
        assert not at.exception and not errors(at)
    names = [r["이름"] for r in at.dataframe[0].value.to_dict("records")]
    assert names == ["山田様", "王小明", "Emily"]
    assert (data_dir / "contacts.csv").read_text(encoding="utf-8").count("\n") == 4


# ---- 기준 2: 이름 경계값
@pytest.mark.parametrize("name", ["", " ", "   ", "\t", "a" * 31, "a" * 100, "あ" * 31, "中" * 31])
def test_c2_bad_names_rejected(data_dir, name):
    p = data_dir / "contacts.csv"
    assert logic.add_contact(p, name, "friend", "en", "casual", TODAY) == MSG_NAME
    assert not p.exists()


def test_c2_screen_message_exact(data_dir):
    for bad in ["", "   ", "x" * 31]:
        at = submit(run(), bad, "friend", "en", "casual")
        assert errors(at) == [MSG_NAME]
        assert not (data_dir / "contacts.csv").exists()


def test_c2_name_checked_before_choices(data_dir):
    assert logic.add_contact(data_dir / "c.csv", "", None, None, None, TODAY) == MSG_NAME


# ---- 기준 3: 빈 상태
def test_c3_no_file(data_dir):
    at = run()
    assert not at.exception
    assert [i.value for i in at.tabs[0].info] == [MSG_EMPTY]


def test_c3_header_only(data_dir):
    (data_dir / "contacts.csv").write_text("id,name,relation,language,formality\n", encoding="utf-8")
    at = run()
    assert not at.exception
    assert [i.value for i in at.tabs[0].info] == [MSG_EMPTY]


def test_c3_message_gone_after_first_card(data_dir):
    at = submit(run(), "Kim", "friend", "en", "casual")
    assert not at.tabs[0].info


def test_c3_empty_zero_byte_file(data_dir):
    (data_dir / "contacts.csv").write_text("", encoding="utf-8")
    at = run()
    assert not at.exception
    assert [i.value for i in at.tabs[0].info] == [MSG_EMPTY]


# ---- 기준 4: 하나라도 안 고르면
@pytest.mark.parametrize("missing", ["relation", "language", "formality"])
def test_c4_each_missing_choice(data_dir, missing):
    args = {"relation": "boss", "language": "zh", "formality": "formal"}
    args[missing] = None
    assert logic.add_contact(data_dir / "c.csv", "Kim", **args, today=TODAY) == MSG_PICK
    assert not (data_dir / "c.csv").exists()


def test_c4_screen_nothing_preselected_and_message(data_dir):
    at = run()
    for k in ("c_relation", "c_language", "c_formality"):
        assert at.radio(key=k).value is None
    at = submit(at, "Kim")
    assert errors(at) == [MSG_PICK]
    assert not (data_dir / "contacts.csv").exists()


@pytest.mark.parametrize("rel,lang,form", [("friend", "en", None), (None, "ja", "casual"), ("boss", None, "formal")])
def test_c4_screen_partial(data_dir, rel, lang, form):
    at = submit(run(), "Kim", rel, lang, form)
    assert errors(at) == [MSG_PICK]


def test_c4_invalid_code_rejected(data_dir):
    assert logic.add_contact(data_dir / "c.csv", "Kim", "boss", "ko", "formal", TODAY) == MSG_PICK


# ---- 진짜 data 보호 · 기록 지키기
def test_isolated_temp_dir(data_dir):
    assert logic.data_dir() == data_dir
    assert data_dir != ROOT / "data"


def test_append_only_and_backup(data_dir):
    p = data_dir / "contacts.csv"
    logic.add_contact(p, "A", "friend", "en", "casual", TODAY)
    before = p.read_bytes()
    logic.add_contact(p, "B", "boss", "zh", "formal", TODAY)
    assert p.read_bytes().startswith(before)
    assert (data_dir / "backup" / "contacts-2026-11-12.csv").exists()
