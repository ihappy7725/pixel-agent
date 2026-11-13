"""웹 배포판(Vercel) 서버 쪽 — 요청을 받아 logic.py · ai.py 로 판단하고 JSON 으로 돌려줘요.

- 판단 규칙 · 안내 문장은 logic.py 한 곳에만 있어요 (Streamlit 앱과 똑같이).
- 기록(상대 카드 · 보관함)은 서버에 저장하지 않아요. 방문자 각자의 브라우저에 저장돼요 (PRD 7장).
- Gemini 는 /api/translate 에서만 불러요. 방문자 · 사이트 하루 횟수 제한을 먼저 확인해요.
"""
import pathlib

import ai
import logic

ROOT = pathlib.Path(__file__).resolve().parent
SEED = ROOT / "seed"
MAX_BODY = 200_000  # 요청 크기 상한 (글자 수 제한 2000자보다 훨씬 넉넉하게)
MAX_LIST = 500      # 브라우저가 보내는 목록 길이 상한

QUOTA = logic.DailyQuota()  # 서버가 켜져 있는 동안 하루 횟수를 세요

MSG_BAD_REQUEST = "요청 모양이 이상해요. 새로고침한 뒤 다시 해 보세요"


def _options():
    return {
        "relations": logic.RELATIONS,
        "languages": logic.LANGUAGES,
        "formalities": logic.FORMALITIES,
        "situations": logic.SITUATIONS,
    }


def _messages():
    return {
        "noContacts": logic.MSG_NO_CONTACTS,
        "noPhrases": logic.MSG_NO_PHRASES,
        "noResults": logic.MSG_NO_RESULTS,
        "tooVerbose": logic.MSG_TOO_VERBOSE,
        "ready": logic.MSG_READY,
        "aiDown": logic.MSG_AI_DOWN,
    }


def _contact(value):
    """브라우저가 보낸 상대 카드 — 모양이 이상하면 '상대 없음'으로 봐요."""
    if not isinstance(value, dict):
        return None
    c = {k: str(value.get(k) or "") for k in logic.CONTACT_FIELDS}
    return c if c["id"] else None


def _rows(value, fields):
    if not isinstance(value, list):
        return []
    rows = []
    for v in value[:MAX_LIST]:
        if isinstance(v, dict):
            rows.append({k: str(v.get(k) or "") for k in fields})
    return rows


def _text(body, key):
    v = body.get(key)
    return v if isinstance(v, str) else ""


# ---------------------------------------------------------------- 길(route)마다 할 일

def seed(body, visitor, today):
    """처음 온 방문자에게 줄 가상 데이터 + 화면에 필요한 선택지 · 문장."""
    return 200, {
        "contacts": logic.read_rows(SEED / "contacts.csv"),
        "phrases": logic.sort_phrases(logic.read_rows(SEED / "phrases.csv")),
        "options": _options(),
        "messages": _messages(),
        "aiReady": ai.has_key(),
        "aiLeft": QUOTA.left(visitor, today),
        "aiLimit": QUOTA.per_visitor,
    }


def add_contact(body, visitor, today):
    """F1 — 검사만 하고, 통과하면 번호를 붙여 돌려줘요 (저장은 브라우저가)."""
    name = _text(body, "name")
    error = logic.validate_contact(name, body.get("relation"), body.get("language"), body.get("formality"))
    if error:
        return 200, {"error": error}
    contacts = _rows(body.get("contacts"), logic.CONTACT_FIELDS)
    return 200, {"contact": {
        "id": str(logic.next_id(contacts)), "name": name.strip(),
        "relation": body["relation"], "language": body["language"], "formality": body["formality"],
    }}


def add_phrase(body, visitor, today):
    """F4 — 검사만 하고, 통과하면 번호 · 날짜를 붙여 돌려줘요 (저장은 브라우저가)."""
    contact = _contact(body.get("contact"))
    language = contact["language"] if contact else body.get("language")
    error = logic.validate_phrase(_text(body, "text"), language, body.get("situation"))
    if error:
        return 200, {"error": error}
    phrases = _rows(body.get("phrases"), logic.PHRASE_FIELDS)
    return 200, {"phrase": {
        "id": str(logic.next_id(phrases)), "date": today.isoformat(),
        "text": _text(body, "text").strip(), "language": language, "situation": body["situation"],
        "contact_id": contact["id"] if contact else "", "source_ko": _text(body, "source_ko").strip(),
    }}


def search(body, visitor, today):
    """F4 — 최신순 정렬 + 단어 · 상대로 찾기 + 상대 이름(없으면 '—')."""
    contacts = _rows(body.get("contacts"), logic.CONTACT_FIELDS)
    phrases = logic.sort_phrases(_rows(body.get("phrases"), logic.PHRASE_FIELDS))
    found = logic.search_phrases(phrases, _text(body, "word"), _text(body, "contact_id"))
    for p in found:
        p["contact_name"] = logic.contact_label(contacts, p.get("contact_id"))
    return 200, {"total": len(phrases), "phrases": found}


def translate(body, visitor, today):
    """F2 — 검사 → 횟수 제한 확인 → Gemini. 실패해도 안내 문장으로 돌려줘요."""
    contact = _contact(body.get("contact"))
    lang, formality, relation = logic.target_of(contact, body.get("language"))
    source = _text(body, "source")
    error = logic.validate_source(source, lang)
    if error:
        return 200, {"error": error, "aiLeft": QUOTA.left(visitor, today)}
    limit = QUOTA.check(visitor, today)
    if limit:
        return 200, {"error": limit, "aiLeft": 0}
    QUOTA.use(visitor, today)  # AI 를 부르기 전에 센다 → 실패를 반복해도 한도를 넘지 않게
    result = ai.translate(logic.build_ai_prompt(source, lang, formality, relation))
    if result is None:
        return 200, {"error": logic.MSG_AI_DOWN, "aiLeft": QUOTA.left(visitor, today)}
    return 200, {
        "result": result, "language": lang, "source": source.strip(),
        "contact_id": contact["id"] if contact else "",
        "verbose": logic.is_too_verbose(source, result),
        "aiLeft": QUOTA.left(visitor, today),
    }


def verbose(body, visitor, today):
    """F2 기준 4 — 결과를 고칠 때마다 문장 수를 다시 봐요."""
    return 200, {"verbose": logic.is_too_verbose(_text(body, "source"), _text(body, "result"))}


def review_request(body, visitor, today):
    """F3 — 검수 요청문."""
    text, error = logic.build_review_request(
        _text(body, "source"), body.get("situation"), _contact(body.get("contact")), body.get("language"))
    return 200, ({"error": error} if error else {"text": text})


def check(body, visitor, today):
    """F5 — 보내기 전 점검. 점검 단어는 seed/check_rules.csv 에서 읽기만 해요."""
    contact = _contact(body.get("contact"))
    lang, _, relation = logic.target_of(contact, body.get("language"))
    try:
        rules = logic.load_rules(SEED / "check_rules.csv")
    except Exception:
        rules = {}
    return 200, logic.check_email(_text(body, "subject"), _text(body, "body"), lang, relation, rules)


ROUTES = {
    ("GET", "/api/seed"): seed,
    ("POST", "/api/contact"): add_contact,
    ("POST", "/api/phrase"): add_phrase,
    ("POST", "/api/search"): search,
    ("POST", "/api/translate"): translate,
    ("POST", "/api/verbose"): verbose,
    ("POST", "/api/request"): review_request,
    ("POST", "/api/check"): check,
}


def handle(method, path, body, visitor, today):
    """(상태 번호, JSON 으로 보낼 사전)을 돌려줘요. 어떤 경우에도 오류로 멈추지 않아요."""
    fn = ROUTES.get((method, path.rstrip("/") or "/"))
    if not fn:
        return 404, {"error": "없는 주소예요"}
    if method == "POST" and not isinstance(body, dict):
        return 400, {"error": MSG_BAD_REQUEST}
    try:
        return fn(body or {}, visitor or "?", today)
    except Exception:
        return 500, {"error": "잠깐 문제가 생겼어요. 새로고침한 뒤 다시 해 보세요"}
