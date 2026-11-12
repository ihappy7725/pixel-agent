"""모든 테스트가 쓰는 준비물.

- 테스트마다 데이터 폴더를 처음부터 임시 폴더로 줘요 (BRIDGENOTE_DATA_DIR). 진짜 data/는 쓰지 않아요.
- 테스트가 모두 끝나면 진짜 data/ 파일의 지문을 처음과 비교해요. 달라졌으면 테스트 전체를 실패로 만들어요.
  (CLAUDE.md '실수에서 배운 규칙')
"""
import hashlib
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
REAL_DATA = ROOT / "data"


def _fingerprint():
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(REAL_DATA.glob("*.csv"))
    }


def pytest_sessionstart(session):
    session.config._real_data_fp = _fingerprint()


def pytest_sessionfinish(session, exitstatus):
    if _fingerprint() != session.config._real_data_fp:
        print("\n❌ 테스트가 진짜 data/ 파일을 바꿨어요! data/backup/ 사본으로 되돌려 주세요.")
        session.exitstatus = 1


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    monkeypatch.setenv("BRIDGENOTE_DATA_DIR", str(d))
    return d


@pytest.fixture(autouse=True)
def no_real_gemini(tmp_path, monkeypatch):
    """진짜 Gemini 호출 0회 (CLAUDE.md 2번).

    - 진짜 .env 와 환경변수의 키를 읽지 않게 막는다
    - 인터넷으로 보내는 유일한 곳(ai._send)을 '부르면 실패'로 바꿔 둔다
    """
    import ai

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setenv("BRIDGENOTE_ENV_FILE", str(tmp_path / "no.env"))

    def refuse(*args, **kwargs):
        raise AssertionError("테스트에서 진짜 Gemini를 부르려고 했어요!")

    monkeypatch.setattr(ai, "_send", refuse)
