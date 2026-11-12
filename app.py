"""다리말 BridgeNote — 화면 코드.

F1 상대방 카드 · F2 AI 번역 · 다듬기 · F3 검수 요청문 · F4 보관함 · F5 보내기 전 점검
실행: streamlit run app.py
"""
import datetime
import pathlib

import streamlit as st
import streamlit.components.v1 as components

import ai
import logic

DATA_DIR = logic.data_dir()
CONTACTS_PATH = DATA_DIR / "contacts.csv"
PHRASES_PATH = DATA_DIR / "phrases.csv"
RULES_PATH = DATA_DIR / "check_rules.csv"
NO_CONTACT = ""  # 상대 고르기에서 '상대 없이 쓰기'
SAVE_FAILED = "저장하지 못했어요. data 폴더가 열려 있는지 확인해 주세요."


def codes(options):
    return [c for c, _ in options]


def contact_option(contacts, cid):
    if cid == NO_CONTACT:
        return "상대 없이 쓰기"
    c = logic.contact_by_id(contacts, cid)
    if not c:
        return logic.NO_VALUE_MARK
    return " · ".join([
        c.get("name") or logic.NO_VALUE_MARK,
        logic.label(logic.RELATIONS, c.get("relation")),
        logic.label(logic.LANGUAGES, c.get("language")),
        logic.label(logic.FORMALITIES, c.get("formality")),
    ])


def pick_contact(contacts, key):
    """상대 고르기 + (상대가 없을 때만) 언어 고르기. 고른 상대(dict 또는 None)를 돌려줘요."""
    ids = [NO_CONTACT] + [c.get("id") for c in reversed(contacts)]
    cid = st.selectbox("상대", ids, key=f"{key}_contact",
                       format_func=lambda i: contact_option(contacts, i))
    contact = logic.contact_by_id(contacts, cid)
    if not contact:
        st.radio("언어", codes(logic.LANGUAGES), key=f"{key}_language", index=None,
                 horizontal=True, format_func=lambda c: logic.label(logic.LANGUAGES, c))
    return contact


def load_contacts_now():
    try:
        return logic.load_contacts(CONTACTS_PATH)
    except Exception:
        return []


# ---------------------------------------------------------------- 버튼을 누르면 먼저 실행되는 일

def save_contact():
    """F1 저장. 성공하면 입력칸을 비우고, 실패하면 쓴 내용을 그대로 둬요."""
    s = st.session_state
    try:
        error = logic.add_contact(CONTACTS_PATH, s.get("c_name") or "", s.get("c_relation"),
                                  s.get("c_language"), s.get("c_formality"), datetime.date.today())
    except OSError:
        error = SAVE_FAILED
    s["contact_result"] = error
    if not error:
        s["c_name"] = ""
        s["c_relation"] = None
        s["c_language"] = None
        s["c_formality"] = None


def run_translation():
    """F2 번역하기 — 진짜 Gemini 를 부르는 유일한 버튼."""
    s = st.session_state
    contact = logic.contact_by_id(load_contacts_now(), s.get("t_contact"))
    lang, formality, relation = logic.target_of(contact, s.get("t_language"))
    source = s.get("t_source") or ""
    error = logic.validate_source(source, lang)
    s["t_saved"] = None
    if error:
        s["t_error"] = error
        return
    result = ai.translate(logic.build_ai_prompt(source, lang, formality, relation))
    if result is None:
        s["t_error"] = logic.MSG_AI_DOWN
        return
    s["t_error"] = None
    s["t_result"] = result
    s["t_meta"] = {"language": lang, "source": source.strip(),
                   "contact_id": contact.get("id") if contact else ""}


def save_translation():
    """F2 결과를 F4 보관함에 저장 — 내가 버튼을 눌러야만 저장돼요 (CLAUDE.md 6번)."""
    s = st.session_state
    meta = s.get("t_meta") or {}
    try:
        error = logic.add_phrase(PHRASES_PATH, s.get("t_result") or "", meta.get("language"),
                                 s.get("t_situation"), meta.get("contact_id"), meta.get("source"),
                                 datetime.date.today())
    except OSError:
        error = SAVE_FAILED
    s["t_saved"] = error or "ok"


def make_request():
    """F3 검수 요청문 만들기."""
    s = st.session_state
    contact = logic.contact_by_id(load_contacts_now(), s.get("r_contact"))
    text, error = logic.build_review_request(s.get("r_source") or "", s.get("r_situation"),
                                             contact, s.get("r_language"))
    s["r_text"], s["r_error"] = text, error


def save_phrase():
    """F4 보관함에 직접 저장."""
    s = st.session_state
    contact = logic.contact_by_id(load_contacts_now(), s.get("p_contact"))
    lang = contact.get("language") if contact else s.get("p_language")
    try:
        error = logic.add_phrase(PHRASES_PATH, s.get("p_text") or "", lang, s.get("p_situation"),
                                 contact.get("id") if contact else "", s.get("p_source_ko") or "",
                                 datetime.date.today())
    except OSError:
        error = SAVE_FAILED
    s["phrase_result"] = error
    if not error:
        s["p_text"] = ""
        s["p_source_ko"] = ""


def run_check():
    """F5 보내기 전 점검."""
    s = st.session_state
    contact = logic.contact_by_id(load_contacts_now(), s.get("e_contact"))
    lang, _, relation = logic.target_of(contact, s.get("e_language"))
    try:
        rules = logic.load_rules(RULES_PATH)
    except Exception:
        rules = {}
    s["e_result"] = logic.check_email(s.get("e_subject"), s.get("e_body"), lang, relation, rules)


# ---------------------------------------------------------------- 화면

st.set_page_config(page_title="다리말 BridgeNote", page_icon="🌉")
# 뉴욕 트레이드타워 픽셀 오피스 테마 (글꼴 · 색 · 입체 그림자) — 화면 모양만 바꿔요
_THEME_CSS = pathlib.Path(__file__).with_name("theme.css")
if _THEME_CSS.exists():
    # st.html 은 <style> 을 지워 버려서 markdown 으로 넣어요. 줄바꿈은 한 줄로 합쳐요.
    _css = " ".join(_THEME_CSS.read_text(encoding="utf-8").split())
    st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)
st.title("BridgeNote")
st.caption("상대에 맞는 말투로 외국어 이메일 · 채팅 쓰기")

# 뉴욕 트레이드타워 픽셀 오피스 — 서브에이전트들이 탭 · 버튼에 맞춰 움직이는 화면 (기록과는 상관없어요)
_OFFICE_VIEW = pathlib.Path(__file__).with_name("office_view.html")
if _OFFICE_VIEW.exists():
    components.html(_OFFICE_VIEW.read_text(encoding="utf-8"), height=470)

try:
    contacts = logic.load_contacts(CONTACTS_PATH)
except Exception:
    contacts = []
    st.error("상대방 카드 파일을 읽지 못했어요. data/contacts.csv 모양이 바뀌었는지 확인해 주세요.")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["👤 상대방 카드", "✨ AI 번역", "📋 검수 요청문", "📚 보관함", "✅ 보내기 전 점검"]
)

# ---------- F1 상대방 카드
with tab1:
    if not contacts:
        st.info(logic.MSG_NO_CONTACTS)  # 첫 화면: 입력칸 바로 위에서 안내

    with st.form("new_contact"):
        st.text_input("이름", key="c_name", placeholder="예: Emily Carter")
        # 미리 골라 두지 않아요: 상사인데 '친구'로 저장되는 실수를 막으려고 꼭 직접 고르게 (PRD F1 기준 4)
        st.radio("관계", codes(logic.RELATIONS), key="c_relation", index=None,
                 horizontal=True, format_func=lambda c: logic.label(logic.RELATIONS, c))
        st.radio("언어", codes(logic.LANGUAGES), key="c_language", index=None,
                 horizontal=True, format_func=lambda c: logic.label(logic.LANGUAGES, c))
        st.radio("격식", codes(logic.FORMALITIES), key="c_formality", index=None,
                 horizontal=True, format_func=lambda c: logic.label(logic.FORMALITIES, c))
        st.form_submit_button("저장", key="c_save", on_click=save_contact)

    if "contact_result" in st.session_state:
        error = st.session_state.pop("contact_result")
        if error:
            st.error(error)
        else:
            st.success("저장했어요!")

    if contacts:
        st.dataframe(
            [
                {
                    "이름": c.get("name") or logic.NO_VALUE_MARK,
                    "관계": logic.label(logic.RELATIONS, c.get("relation")),
                    "언어": logic.label(logic.LANGUAGES, c.get("language")),
                    "격식": logic.label(logic.FORMALITIES, c.get("formality")),
                }
                for c in reversed(contacts)  # 최근에 등록한 상대가 위
            ],
            hide_index=True,
            key="contacts_table",
        )

# ---------- F2 AI 번역 · 다듬기
with tab2:
    st.text_area("한국어 원문", key="t_source", height=140, max_chars=None,
                 placeholder="보낼 내용을 한국어로 써 보세요 (2000자까지)")
    pick_contact(contacts, "t")
    st.radio("상황", codes(logic.SITUATIONS), key="t_situation", horizontal=True,
             format_func=lambda c: logic.label(logic.SITUATIONS, c))
    if not ai.has_key():
        st.caption("Gemini 키가 아직 없어요. `.env` 에 GEMINI_API_KEY 를 넣으면 번역할 수 있어요.")
    st.button("번역하기", key="t_go", on_click=run_translation, type="primary")

    if st.session_state.get("t_error"):
        st.error(st.session_state["t_error"])

    if st.session_state.get("t_meta"):
        st.text_area("결과 (직접 고칠 수 있어요)", key="t_result", height=160)
        meta = st.session_state["t_meta"]
        if logic.is_too_verbose(meta["source"], st.session_state.get("t_result")):
            st.warning(logic.MSG_TOO_VERBOSE)
        st.button("보관함에 저장", key="t_save", on_click=save_translation)
        saved = st.session_state.get("t_saved")
        if saved == "ok":
            st.success("보관함에 저장했어요!")
        elif saved:
            st.error(saved)

# ---------- F3 검수 요청문 생성기
with tab3:
    st.caption("AI 키가 없거나 한도를 넘었을 때, ChatGPT 등에 그대로 붙여 넣을 요청문을 만들어요.")
    st.text_area("한국어 원문", key="r_source", height=140)
    pick_contact(contacts, "r")
    st.radio("상황", codes(logic.SITUATIONS), key="r_situation", horizontal=True,
             format_func=lambda c: logic.label(logic.SITUATIONS, c))
    st.button("요청문 만들기", key="r_go", on_click=make_request, type="primary")
    if st.session_state.get("r_error"):
        st.error(st.session_state["r_error"])
    elif st.session_state.get("r_text"):
        st.code(st.session_state["r_text"], language=None)
        st.caption("오른쪽 위 복사 버튼을 눌러 그대로 붙여 넣으세요.")

# ---------- F4 검수 완료 문장 보관함
with tab4:
    try:
        phrases = logic.load_phrases(PHRASES_PATH)
    except Exception:
        phrases = []
        st.error("보관함 파일을 읽지 못했어요. data/phrases.csv 모양이 바뀌었는지 확인해 주세요.")

    with st.expander("✍️ 문장 직접 저장하기", expanded=not phrases):
        st.text_area("최종 문장", key="p_text", height=100)
        st.text_input("한국어 원문 (없어도 돼요)", key="p_source_ko")
        pick_contact(contacts, "p")
        st.radio("상황", codes(logic.SITUATIONS), key="p_situation", index=None, horizontal=True,
                 format_func=lambda c: logic.label(logic.SITUATIONS, c))
        st.button("보관함에 저장", key="p_save", on_click=save_phrase)
        if "phrase_result" in st.session_state:
            error = st.session_state.pop("phrase_result")
            if error:
                st.error(error)
            else:
                st.success("저장했어요!")

    col_word, col_who = st.columns(2)
    col_word.text_input("단어로 찾기", key="q_word", placeholder="예: meeting, 회의")
    contact_ids = [NO_CONTACT] + [c.get("id") for c in reversed(contacts)]
    col_who.selectbox("상대로 찾기", contact_ids, key="q_contact",
                      format_func=lambda i: "전체" if i == NO_CONTACT else contact_option(contacts, i))

    shown = logic.search_phrases(phrases, st.session_state.get("q_word"),
                                 st.session_state.get("q_contact"))
    if not phrases:
        st.info(logic.MSG_NO_PHRASES)
    elif not shown:
        st.info(logic.MSG_NO_RESULTS)
    else:
        # st.table: 탭 안에서도 폭이 제대로 잡히고, 긴 문장도 줄바꿈해서 다 보여요
        # (st.dataframe 은 숨어 있던 탭에서 열면 폭이 몇 픽셀로 쪼그라드는 문제가 있었음)
        st.table(
            [
                {
                    "날짜": p.get("date") or logic.NO_VALUE_MARK,
                    "문장": p.get("text") or "",
                    "상대": logic.contact_label(contacts, p.get("contact_id")),
                    "언어": logic.label(logic.LANGUAGES, p.get("language")),
                    "상황": logic.label(logic.SITUATIONS, p.get("situation")),
                }
                for p in shown
            ],
            hide_index=True,
        )

# ---------- F5 보내기 전 점검 (이메일)
with tab5:
    st.text_input("제목", key="e_subject")
    st.text_area("본문", key="e_body", height=180)
    pick_contact(contacts, "e")
    st.button("점검하기", key="e_go", on_click=run_check, type="primary")

    res = st.session_state.get("e_result")
    if res:
        if res["error"]:
            st.error(res["error"])
        else:
            if res["missing"]:
                st.error("빠진 항목: " + " · ".join(res["missing"]))
            if res["casual"]:
                st.warning("상사 · 거래처에게 피할 표현: " + ", ".join(res["casual"]))
            if res["note"]:
                st.info(res["note"])
            if res["ready"]:
                st.success(logic.MSG_READY)
