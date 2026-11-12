"""Gemini 부르기 (CLAUDE.md 3번: 설치 없이 파이썬 기본 기능 urllib 로).

- 키는 환경변수 GEMINI_API_KEY 또는 .env 의 GEMINI_API_KEY 에서만 읽어요. 코드 · 화면 · 로그에 키를 쓰지 않아요.
- 키는 주소(URL)가 아니라 요청 머리(header)에 실어 보내요 → 오류 메시지 · 기록에 키가 찍히지 않게.
- 키가 없거나 · 한도를 넘었거나 · 인터넷이 끊기면 오류 대신 None 을 돌려줘요 (PRD F2 기준 3).
- 테스트에서는 이 파일의 _send 를 가짜로 바꿔요. 진짜 호출 0회 (CLAUDE.md 2번).
"""
import json
import os
import pathlib
import ssl
import urllib.error
import urllib.request

# 무료 등급에서 빠르게 답하는 가벼운 모델. .env 의 GEMINI_MODEL 로 바꿀 수 있어요
# (2026-11-12 확인: gemini-2.5-flash 는 새 키에서 404, gemini-flash-latest 는 30초 넘게 응답 없음 → 3.5-flash-lite 2.6초)
DEFAULT_MODEL = "gemini-3.5-flash-lite"
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_SECONDS = 30


def _env_file():
    return pathlib.Path(
        os.environ.get("BRIDGENOTE_ENV_FILE") or pathlib.Path(__file__).parent / ".env"
    )


def _read_env_file():
    """.env 를 KEY=VALUE 줄로 읽어요. 파일이 없으면 빈 사전."""
    values = {}
    path = _env_file()
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _setting(name):
    return (os.environ.get(name) or _read_env_file().get(name) or "").strip()


def has_key():
    """키가 있는지만 알려 줘요 (키 값은 돌려주지 않아요)."""
    return bool(_setting("GEMINI_API_KEY"))


def _ssl_context():
    """보안 인증서 목록. macOS의 python.org 파이썬은 기본 목록을 못 찾는 일이 있어서,
    이미 설치된 certifi 가 있으면 그 목록을 써요 (없으면 파이썬 기본값)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _send(url, body, key):
    """진짜로 인터넷에 보내는 유일한 곳. 테스트에서는 가짜로 바꿔요."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=_ssl_context()) as resp:
        return json.loads(resp.read().decode("utf-8"))


def translate(prompt):
    """Gemini 에게 요청을 보내고 결과 글을 돌려줘요. 무엇이든 실패하면 None."""
    key = _setting("GEMINI_API_KEY")
    if not key:
        return None
    model = _setting("GEMINI_MODEL") or DEFAULT_MODEL
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        data = _send(API_URL.format(model=model), body, key)
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
        return text or None
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError):
        return None
