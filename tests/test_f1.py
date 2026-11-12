"""F1 상대방 카드 — PRD 완료 기준 검사. 진짜 data/는 쓰지 않아요(임시 폴더만 사용)."""
import datetime

from streamlit.testing.v1 import AppTest

import logic
from conftest import ROOT

TODAY = datetime.date(2026, 11, 12)
APP = str(ROOT / "app.py")


def contacts_file(data_dir):
    return data_dir / "contacts.csv"


def run_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    return at


def fill_and_save(at, name, relation, language, formality):
    at.text_input(key="c_name").input(name)
    if relation:
        at.radio(key="c_relation").set_value(relation)
    if language:
        at.radio(key="c_language").set_value(language)
    if formality:
        at.radio(key="c_formality").set_value(formality)
    at.button(key="c_save").click()
    at.run()
    return at


# ---------- 완료 기준 1: 이름(1~30자) · 관계 · 언어 · 격식을 모두 고르면 저장되고 목록에 보인다

def test_one_char_name_saved(data_dir):
    p = contacts_file(data_dir)
    assert logic.add_contact(p, "가", "friend", "en", "casual", TODAY) is None
    assert logic.load_contacts(p) == [
        {"id": "1", "name": "가", "relation": "friend", "language": "en", "formality": "casual"}
    ]


def test_thirty_char_name_saved(data_dir):
    p = contacts_file(data_dir)
    assert logic.add_contact(p, "a" * 30, "boss", "zh", "formal", TODAY) is None
    assert logic.load_contacts(p)[0]["name"] == "a" * 30


def test_every_choice_can_be_saved(data_dir):
    p = contacts_file(data_dir)
    for rel, _ in logic.RELATIONS:
        for lang, _ in logic.LANGUAGES:
            for form, _ in logic.FORMALITIES:
                assert logic.add_contact(p, "Kim", rel, lang, form, TODAY) is None
    assert len(logic.load_contacts(p)) == 4 * 3 * 3


def test_chinese_and_japanese_names_not_broken(data_dir):
    p = contacts_file(data_dir)
    logic.add_contact(p, "王小明", "boss", "zh", "formal", TODAY)
    logic.add_contact(p, "佐藤健", "client", "ja", "formal", TODAY)
    assert [c["name"] for c in logic.load_contacts(p)] == ["王小明", "佐藤健"]


# ---------- 완료 기준 4: 관계 · 언어 · 격식 중 하나라도 안 고르면 저장되지 않고 안내가 보인다

def test_pick_all_message_matches_prd():
    assert logic.MSG_PICK_ALL == "관계 · 언어 · 격식을 모두 골라 주세요"


def test_screen_missing_choice_shows_message(data_dir):
    at = fill_and_save(run_app(), "Jake", "friend", "en", None)
    assert "관계 · 언어 · 격식을 모두 골라 주세요" in [e.value for e in at.tabs[0].error]
    assert not contacts_file(data_dir).exists()


def test_missing_choice_not_saved(data_dir):
    p = contacts_file(data_dir)
    assert logic.add_contact(p, "Jake", None, "en", "casual", TODAY) == logic.MSG_PICK_ALL
    assert logic.add_contact(p, "Jake", "friend", None, "casual", TODAY) == logic.MSG_PICK_ALL
    assert logic.add_contact(p, "Jake", "friend", "en", None, TODAY) == logic.MSG_PICK_ALL
    assert logic.add_contact(p, "Jake", "family", "en", "casual", TODAY) == logic.MSG_PICK_ALL
    assert not p.exists()


def test_screen_saves_and_lists_contact(data_dir):
    at = fill_and_save(run_app(), "Emily Carter", "client", "en", "formal")
    assert "저장했어요!" in [s.value for s in at.tabs[0].success]
    table = at.dataframe[0].value
    assert table.iloc[0].to_dict() == {"이름": "Emily Carter", "관계": "거래처", "언어": "영어", "격식": "격식"}
    assert logic.MSG_NO_CONTACTS not in [i.value for i in at.tabs[0].info]


def test_screen_newest_contact_on_top(data_dir):
    at = fill_and_save(run_app(), "Jake", "friend", "en", "casual")
    at = fill_and_save(at, "李娜", "colleague", "zh", "normal")
    assert list(at.dataframe[0].value["이름"]) == ["李娜", "Jake"]


# ---------- 완료 기준 2: 이름이 비었거나 31자 이상이면 저장되지 않고 "이름은 1~30자로 써 주세요"

def test_empty_name_not_saved(data_dir):
    p = contacts_file(data_dir)
    assert logic.add_contact(p, "", "friend", "en", "casual", TODAY) == "이름은 1~30자로 써 주세요"
    assert logic.add_contact(p, "   ", "friend", "en", "casual", TODAY) == "이름은 1~30자로 써 주세요"
    assert not p.exists()


def test_31_char_name_not_saved(data_dir):
    p = contacts_file(data_dir)
    logic.add_contact(p, "Jake", "friend", "en", "casual", TODAY)
    before = p.read_bytes()
    assert logic.add_contact(p, "a" * 31, "friend", "en", "casual", TODAY) == "이름은 1~30자로 써 주세요"
    assert p.read_bytes() == before


def test_screen_shows_name_error_and_keeps_input(data_dir):
    at = fill_and_save(run_app(), "a" * 31, "friend", "en", "casual")
    assert "이름은 1~30자로 써 주세요" in [e.value for e in at.tabs[0].error]
    assert at.text_input(key="c_name").value == "a" * 31  # 고쳐 쓰기 편하게 남겨 둔다
    assert not contacts_file(data_dir).exists()


# ---------- 완료 기준 3: 카드가 0개여도 화면이 열리고 "첫 상대를 등록해 보세요"가 보인다

def test_no_file_screen_opens(data_dir):
    at = run_app()
    assert not at.exception
    assert "첫 상대를 등록해 보세요" in [i.value for i in at.tabs[0].info]


def test_header_only_screen_opens(data_dir):
    contacts_file(data_dir).write_text("id,name,relation,language,formality\n", encoding="utf-8")
    at = run_app()
    assert not at.exception
    assert "첫 상대를 등록해 보세요" in [i.value for i in at.tabs[0].info]


# ---------- CLAUDE.md 규칙 검사 (기록 지키기 · 기록이 없어도 열리기)

def test_append_only_keeps_old_lines(data_dir):
    p = contacts_file(data_dir)
    logic.add_contact(p, "Jake", "friend", "en", "casual", TODAY)
    before = p.read_bytes()
    logic.add_contact(p, "李娜", "colleague", "zh", "normal", TODAY)
    assert p.read_bytes().startswith(before)


def test_ids_keep_counting_up(data_dir):
    p = contacts_file(data_dir)
    p.write_text("id,name,relation,language,formality\n7,Old,friend,en,casual\n", encoding="utf-8")
    logic.add_contact(p, "New", "friend", "en", "casual", TODAY)
    assert [c["id"] for c in logic.load_contacts(p)] == ["7", "8"]


def test_file_without_last_newline_not_broken(data_dir):
    p = contacts_file(data_dir)
    p.write_text("id,name,relation,language,formality\n1,Old,friend,en,casual", encoding="utf-8")
    logic.add_contact(p, "New", "boss", "ja", "formal", TODAY)
    assert [c["name"] for c in logic.load_contacts(p)] == ["Old", "New"]


def test_backup_made_before_save(data_dir):
    p = contacts_file(data_dir)
    logic.add_contact(p, "Jake", "friend", "en", "casual", TODAY)
    first = p.read_bytes()
    logic.add_contact(p, "Emily", "client", "en", "formal", TODAY)
    backup = data_dir / "backup" / "contacts-2026-11-12.csv"
    assert backup.read_bytes() == first  # 그날 첫 저장 직전 모습 그대로 (하루 한 번)


def test_unknown_values_shown_as_dash(data_dir):
    contacts_file(data_dir).write_text(
        "id,name,relation,language,formality\n1,Odd,family,ko,super\n", encoding="utf-8"
    )
    at = run_app()
    assert not at.exception
    assert at.dataframe[0].value.iloc[0].to_dict() == {"이름": "Odd", "관계": "—", "언어": "—", "격식": "—"}
