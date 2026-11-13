"""다리말 BridgeNote의 검사 · 계산 코드 (화면은 app.py, Gemini 부르기는 ai.py).

여기 있는 함수는 화면 없이도 테스트할 수 있어요.
'오늘 날짜'와 '파일 위치'는 항상 바깥에서 받아요.
"""
import csv
import re
import os
import pathlib
import shutil


def data_dir():
    """데이터 폴더 위치. 평소에는 data/, 테스트할 때는 BRIDGENOTE_DATA_DIR로 임시 폴더를 줘요."""
    return pathlib.Path(
        os.environ.get("BRIDGENOTE_DATA_DIR") or pathlib.Path(__file__).parent / "data"
    )


# ---------------------------------------------------------------- 공통 파일 도우미

def read_rows(path):
    """CSV를 UTF-8로 읽어 줄 목록으로 돌려줘요. 파일이 없거나 머리줄만 있으면 빈 목록."""
    path = pathlib.Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [dict(row) for row in csv.DictReader(f)]


def backup(path, today):
    """저장하기 전에 data/backup/ 에 그날의 사본을 하나 남겨요 (하루 한 번만)."""
    path = pathlib.Path(path)
    if not path.exists():
        return
    dest = path.parent / "backup" / f"{path.stem}-{today.isoformat()}.csv"
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)


def append_row(path, fields, row):
    """한 줄을 덧붙이기만 해요 (파일 전체를 새로 쓰지 않아요)."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    if not is_new:
        # 마지막 줄이 줄바꿈 없이 끝나 있으면 새 줄이 그 뒤에 붙어 버려요 → 줄바꿈부터 넣기
        with path.open("rb") as f:
            f.seek(-1, os.SEEK_END)
            needs_newline = f.read(1) not in (b"\n", b"\r")
    with path.open("a", newline="", encoding="utf-8") as f:
        if not is_new and needs_newline:
            f.write("\n")
        w = csv.DictWriter(f, fieldnames=fields)
        if is_new:
            w.writeheader()
        w.writerow(row)


def next_id(rows):
    """지금 있는 번호 중 가장 큰 번호 + 1 (숫자가 아닌 번호는 건너뛰어요)."""
    ids = [int(r["id"]) for r in rows if str(r.get("id") or "").strip().isdigit()]
    return max(ids, default=0) + 1


def label(options, code):
    """('friend', '친구') 같은 목록에서 이름을 찾아요. 모르는 값이면 '—'."""
    return dict(options).get(code, NO_VALUE_MARK)


NO_VALUE_MARK = "—"


# ---------------------------------------------------------------- F1 상대방 카드

CONTACT_FIELDS = ["id", "name", "relation", "language", "formality"]
NAME_MAX = 30

RELATIONS = [("friend", "친구"), ("colleague", "동료"), ("boss", "상사"), ("client", "거래처")]
LANGUAGES = [("en", "영어"), ("zh", "중국어"), ("ja", "일본어")]
FORMALITIES = [("casual", "편하게"), ("normal", "보통"), ("formal", "격식")]

MSG_NAME_LENGTH = "이름은 1~30자로 써 주세요"
MSG_NO_CONTACTS = "첫 상대를 등록해 보세요"
# PRD F1 기준 4 — 관계 · 언어 · 격식 중 하나라도 안 골랐을 때
MSG_PICK_ALL = "관계 · 언어 · 격식을 모두 골라 주세요"


def load_contacts(path):
    return read_rows(path)


def validate_contact(name, relation, language, formality):
    """문제가 있으면 안내 문장을, 없으면 None을 돌려줘요."""
    name = (name or "").strip()
    if not 1 <= len(name) <= NAME_MAX:
        return MSG_NAME_LENGTH
    if (
        relation not in dict(RELATIONS)
        or language not in dict(LANGUAGES)
        or formality not in dict(FORMALITIES)
    ):
        return MSG_PICK_ALL
    return None


def add_contact(path, name, relation, language, formality, today):
    """상대방 카드를 한 장 저장해요. 성공하면 None, 저장하지 않았으면 안내 문장."""
    error = validate_contact(name, relation, language, formality)
    if error:
        return error
    row = {
        "id": next_id(load_contacts(path)),
        "name": name.strip(),
        "relation": relation,
        "language": language,
        "formality": formality,
    }
    backup(path, today)
    append_row(path, CONTACT_FIELDS, row)
    return None


def contact_by_id(contacts, contact_id):
    """번호로 상대를 찾아요. 비었거나 없는 번호면 None."""
    cid = str(contact_id or "").strip()
    if not cid:
        return None
    for c in contacts:
        if str(c.get("id") or "").strip() == cid:
            return c
    return None


def contact_label(contacts, contact_id):
    """보관함 목록의 '상대' 칸. 비었거나 없는 번호면 '—' (PRD F4 기준 5)."""
    c = contact_by_id(contacts, contact_id)
    return (c.get("name") or NO_VALUE_MARK) if c else NO_VALUE_MARK


# ---------------------------------------------------------------- F2 AI 번역 · 다듬기

TEXT_MAX = 2000
SITUATIONS = [("email", "이메일"), ("chat", "채팅")]

MSG_SOURCE_LENGTH = "1~2000자로 써 주세요"
MSG_PICK_LANGUAGE = "번역할 언어를 골라 주세요"
MSG_AI_DOWN = "지금은 AI를 쓸 수 없어요 — 검수 요청문으로 이어서 해 보세요"
MSG_TOO_VERBOSE = "원문보다 길어졌어요, 줄여 볼까요?"
VERBOSE_LIMIT = 2  # ✍️ 내 기준: 원문보다 문장이 2개 이상 많으면 경고

# AI에게 보낼 언어 이름
LANGUAGE_PROMPT_NAMES = {"en": "영어", "zh": "중국어(간체자)", "ja": "일본어"}

# 문장 끝: . ! ? 。 ！ ？  — 단, 3.5 처럼 숫자 사이의 점은 문장 끝이 아니다
_SENTENCE_END = re.compile(r"[!?。！？]|\.(?!\d)")


def count_sentences(text):
    """문장 수를 세요 (PRD F2 기준 4). 문장부호가 하나도 없으면 1문장, 빈 글은 0문장."""
    text = (text or "").strip()
    if not text:
        return 0
    parts = [p for p in _SENTENCE_END.split(text) if p.strip()]
    return max(len(parts), 1)


def is_too_verbose(source, result):
    """결과 문장 수가 원문보다 2개 이상 많으면 True."""
    return count_sentences(result) - count_sentences(source) >= VERBOSE_LIMIT


def target_of(contact, language):
    """상대를 골랐으면 상대의 언어 · 격식 · 관계, 안 골랐으면 직접 고른 언어 + '보통' 격식."""
    if contact:
        return contact.get("language"), contact.get("formality"), contact.get("relation")
    return language, "normal", None


def validate_source(source, language):
    """원문(1~2000자)과 언어를 검사해요. 문제가 있으면 안내 문장, 없으면 None."""
    source = (source or "").strip()
    if not 1 <= len(source) <= TEXT_MAX:
        return MSG_SOURCE_LENGTH
    if language not in dict(LANGUAGES):
        return MSG_PICK_LANGUAGE
    return None


def build_ai_prompt(source, language, formality, relation=None):
    """Gemini에게 보낼 요청. CLAUDE.md 6번 — 두 규칙을 꼭 넣는다."""
    relation_text = label(RELATIONS, relation) if relation else "지정 안 함"
    return (
        f"다음 한국어 원문을 {LANGUAGE_PROMPT_NAMES[language]}로 옮겨 주세요.\n"
        f"- 받는 사람과의 관계: {relation_text}\n"
        f"- 격식: {label(FORMALITIES, formality)}\n"
        "- 원문에 없는 내용을 덧붙이지 말 것.\n"
        "- 상대의 격식에 맞출 것.\n"
        "- 숫자 · 날짜 · 시간 · 이름은 바꾸지 말 것.\n"
        "- 번역문만 쓰고, 설명이나 따옴표는 붙이지 말 것.\n"
        "\n"
        f"[원문]\n{source.strip()}"
    )


# ---------------------------------------------------------------- F3 검수 요청문 생성기

MSG_NEED_SOURCE = "검수할 문장을 넣어 주세요"


def build_review_request(source, situation, contact=None, language=None):
    """ChatGPT 등에 붙여 넣을 검수 요청문. 문제가 있으면 (None, 안내 문장)."""
    source = (source or "").strip()
    if not source:
        return None, MSG_NEED_SOURCE
    lang, formality, relation = target_of(contact, language)
    if lang not in dict(LANGUAGES):
        return None, MSG_PICK_LANGUAGE
    who = f"{contact.get('name')} ({label(RELATIONS, relation)})" if contact else "지정 안 함"
    text = (
        f"다음 한국어 원문을 {label(LANGUAGES, lang)}로 번역하고 검수해 주세요.\n"
        f"- 상대: {who}\n"
        f"- 관계: {label(RELATIONS, relation) if contact else '지정 안 함'}\n"
        f"- 언어: {label(LANGUAGES, lang)}\n"
        f"- 격식: {label(FORMALITIES, formality)}\n"
        f"- 상황: {label(SITUATIONS, situation)}\n"
        "- 지켜 주세요: 원문에 없는 내용을 덧붙이지 말 것 · 상대의 격식에 맞출 것 · 숫자 · 날짜 · 이름은 바꾸지 말 것\n"
        "- 번역문을 먼저 주고, 고친 곳이 있으면 아래에 짧게 알려 주세요.\n"
        "\n"
        f"[원문]\n{source}"
    )
    return text, None


# ---------------------------------------------------------------- F4 검수 완료 문장 보관함

PHRASE_FIELDS = ["id", "date", "text", "language", "situation", "contact_id", "source_ko"]

MSG_EMPTY_PHRASE = "저장할 문장을 넣어 주세요"
MSG_NO_PHRASES = "첫 문장을 저장해 보세요"
MSG_NO_RESULTS = "찾는 문장이 없어요"
MSG_PICK_SITUATION = "상황(이메일/채팅)을 골라 주세요"


def _id_number(row):
    s = str(row.get("id") or "").strip()
    return int(s) if s.isdigit() else -1


def sort_phrases(rows):
    """최신이 위 (같은 날이면 나중에 저장한 것이 위)."""
    return sorted(rows, key=lambda r: (r.get("date") or "", _id_number(r)), reverse=True)


def load_phrases(path):
    """보관함 문장 — 최신이 위 (같은 날이면 나중에 저장한 것이 위)."""
    return sort_phrases(read_rows(path))


def validate_phrase(text, language, situation):
    """보관함에 넣을 문장 검사 (PRD F4 기준 1 · 2 · 6). 문제가 있으면 안내 문장, 없으면 None."""
    text = (text or "").strip()
    if not text:
        return MSG_EMPTY_PHRASE
    if len(text) > TEXT_MAX:
        return MSG_SOURCE_LENGTH
    if language not in dict(LANGUAGES):
        return MSG_PICK_LANGUAGE
    if situation not in dict(SITUATIONS):
        return MSG_PICK_SITUATION
    return None


def add_phrase(path, text, language, situation, contact_id, source_ko, today):
    """문장을 보관함에 저장해요. 성공하면 None, 저장하지 않았으면 안내 문장."""
    error = validate_phrase(text, language, situation)
    if error:
        return error
    text = text.strip()
    row = {
        "id": next_id(read_rows(path)),
        "date": today.isoformat(),
        "text": text,
        "language": language,
        "situation": situation,
        "contact_id": str(contact_id or "").strip(),
        "source_ko": (source_ko or "").strip(),
    }
    backup(path, today)
    append_row(path, PHRASE_FIELDS, row)
    return None


def search_phrases(phrases, word="", contact_id=""):
    """✍️ 내 기준(F4 기준 4): 단어 · 상대로 찾기. 둘 다 비면 전체.

    단어는 문장과 한국어 원문에서 찾고, 영어는 대문자 · 소문자를 가리지 않는다.
    """
    word = (word or "").strip().casefold()
    cid = str(contact_id or "").strip()
    found = []
    for p in phrases:
        if cid and str(p.get("contact_id") or "").strip() != cid:
            continue
        haystack = f"{p.get('text') or ''}\n{p.get('source_ko') or ''}".casefold()
        if word and word not in haystack:
            continue
        found.append(p)
    return found


# ---------------------------------------------------------------- F5 보내기 전 점검 (이메일)

MSG_EMPTY_BODY = "점검할 글을 넣어 주세요"
MSG_READY = "보낼 준비 완료"
MSG_NO_RULES = "점검 단어 목록(data/check_rules.csv)을 찾지 못해서 인사말 · 맺음말은 점검하지 못했어요"
STRICT_RELATIONS = {"boss", "client"}  # 상사 · 거래처


def load_rules(path):
    """점검 단어 목록 — 앱은 읽기만 한다 (CLAUDE.md 1번)."""
    rules = {}
    for r in read_rows(path):
        lang, kind, word = r.get("language"), r.get("type"), (r.get("word") or "").strip()
        if lang and kind and word:
            rules.setdefault(lang, {}).setdefault(kind, []).append(word)
    return rules


def contains_word(text, word, language):
    """영어는 단어 단위 · 대소문자 구분 없이, 중국어 · 일본어는 글자가 들어 있는지로 찾는다."""
    if language == "en":
        pattern = r"(?<![A-Za-z])" + re.escape(word) + r"(?![A-Za-z])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    return word in text


def check_email(subject, body, language, relation, rules):
    """보내기 전 점검 결과.

    돌려주는 값: {"error": 안내 문장 또는 None,
                  "missing": 빠진 항목 이름 목록 (제목 · 인사말 · 맺음말),
                  "casual": 상사 · 거래처에게 피할 표현 목록,
                  "note": 점검하지 못한 것 안내 또는 None,
                  "ready": 문제가 0개면 True}
    """
    result = {"error": None, "missing": [], "casual": [], "note": None, "ready": False}
    body = body or ""
    if not body.strip():
        result["error"] = MSG_EMPTY_BODY
        return result
    if language not in dict(LANGUAGES):
        result["error"] = MSG_PICK_LANGUAGE
        return result
    words = rules.get(language, {})
    if not (subject or "").strip():
        result["missing"].append("제목")
    if words.get("greeting") or words.get("closing"):
        if not any(contains_word(body, w, language) for w in words.get("greeting", [])):
            result["missing"].append("인사말")
        if not any(contains_word(body, w, language) for w in words.get("closing", [])):
            result["missing"].append("맺음말")
    else:
        result["note"] = MSG_NO_RULES
    # 상대를 안 골랐으면(relation 없음) 상사 · 거래처인지 모르므로 검사하지 않는다 (PRD F5 기준 4)
    if relation in STRICT_RELATIONS:
        result["casual"] = [w for w in words.get("casual", []) if contains_word(body, w, language)]
    result["ready"] = not result["missing"] and not result["casual"] and not result["note"]
    return result


# ---------------------------------------------------------------- 웹 배포판 — AI 번역 횟수 제한 (PRD 7장)

VISITOR_DAILY_LIMIT = 3   # 방문자 한 명당 하루 AI 번역 횟수
SITE_DAILY_LIMIT = 50     # 사이트 전체 하루 AI 번역 횟수 (무료 한도 보호)
MSG_LIMIT_VISITOR = "오늘 쓸 수 있는 AI 번역 3번을 다 썼어요 — 검수 요청문으로 이어서 해 보세요"
MSG_LIMIT_SITE = "오늘 사이트 전체 AI 번역 한도를 다 썼어요 — 검수 요청문으로 이어서 해 보세요"


class DailyQuota:
    """하루 단위로 AI 번역 횟수를 세요. 날짜가 바뀌면 처음부터 다시 세요."""

    def __init__(self, per_visitor=VISITOR_DAILY_LIMIT, per_site=SITE_DAILY_LIMIT):
        self.per_visitor, self.per_site = per_visitor, per_site
        self.day, self.site, self.visitors = None, 0, {}

    def _roll(self, today):
        if self.day != today:
            self.day, self.site, self.visitors = today, 0, {}

    def check(self, visitor, today):
        """더 쓸 수 있으면 None, 아니면 안내 문장."""
        self._roll(today)
        if self.visitors.get(visitor, 0) >= self.per_visitor:
            return MSG_LIMIT_VISITOR
        if self.site >= self.per_site:
            return MSG_LIMIT_SITE
        return None

    def use(self, visitor, today):
        self._roll(today)
        self.visitors[visitor] = self.visitors.get(visitor, 0) + 1
        self.site += 1

    def left(self, visitor, today):
        self._roll(today)
        return max(0, min(self.per_visitor - self.visitors.get(visitor, 0), self.per_site - self.site))
