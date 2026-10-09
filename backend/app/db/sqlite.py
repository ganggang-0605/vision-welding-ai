"""저장소(app/store.py)를 SQLite 파일에 남기기 — 서버를 다시 켜도 워크스페이스 · 작업 · 사진 · 해석 결과가 그대로 있게

기본 DB 는 PostgreSQL(app/db/postgres.py). SQLite 는 PostgreSQL 없이 개발할 때 쓴다 (app/db/connect.py 가 주소로 고름).
.env 의 DATABASE_URL (sqlite:///경로). 상대 경로는 backend/ 기준. 비우거나 sqlite:///:memory: 면 남기지 않음 (테스트).
표 두 개만 쓴다 — 바뀐 항목 하나씩 JSON 으로 덮어쓰고(docs), 사진 파일은 따로(blobs).
  docs(collection, key, value)  collection: users · meta · workspaces · members · symbols · projects · trees · jobs · images · analyses
  blobs(kind, key, data)        kind: image(올린 원본) · preprocessed(1단계 보정본)
읽는 순서는 처음 넣은 순서(rowid) — 저장소의 dict 순서(시드 순 → 새로 만든 순)와 같게.
표준 용접 기준은 읽기 전용이라 남기지 않고 늘 data/seed/welding_standards.csv 에서 읽는다.
"""
import json
import sqlite3
import threading
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def database_path(url: str | None) -> Path | None:
    """DATABASE_URL → 파일 경로 (남기지 않으면 None). sqlite 가 아닌 주소는 아직 지원하지 않음"""
    url = (url or "").split("#")[0].strip()
    if not url or url in ("sqlite://", "sqlite:///:memory:"):
        return None
    if not url.startswith("sqlite:///"):
        raise ValueError(f"DATABASE_URL 은 sqlite:///경로 만 지원합니다: {url}")
    path = Path(url.removeprefix("sqlite:///"))
    return path if path.is_absolute() else BACKEND_DIR / path


class Database:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript("""
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS docs (
                collection TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (collection, key));
            CREATE TABLE IF NOT EXISTS blobs (
                kind TEXT NOT NULL, key TEXT NOT NULL, data BLOB NOT NULL, PRIMARY KEY (kind, key));
        """)

    def is_empty(self) -> bool:
        with self._lock:
            return self._conn.execute("SELECT 1 FROM docs LIMIT 1").fetchone() is None

    def put(self, collection: str, key: str, value) -> None:
        """JSON 으로 저장 (이미 있으면 덮어씀 — 순서는 처음 넣은 자리 그대로)"""
        data = json.dumps(value, ensure_ascii=False, default=str)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO docs (collection, key, value) VALUES (?, ?, ?) "
                "ON CONFLICT (collection, key) DO UPDATE SET value = excluded.value", (collection, key, data))

    def delete(self, collection: str, key: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM docs WHERE collection = ? AND key = ?", (collection, key))

    def all(self, collection: str) -> list[tuple[str, object]]:
        """[(key, 값)] 넣은 순서"""
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM docs WHERE collection = ? ORDER BY rowid", (collection,))
            return [(key, json.loads(value)) for key, value in rows.fetchall()]

    def put_blob(self, kind: str, key: str, data: bytes) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO blobs (kind, key, data) VALUES (?, ?, ?) "
                "ON CONFLICT (kind, key) DO UPDATE SET data = excluded.data", (kind, key, data))

    def blobs(self, kind: str) -> dict[str, bytes]:
        with self._lock:
            return dict(self._conn.execute("SELECT key, data FROM blobs WHERE kind = ?", (kind,)).fetchall())

    def rows(self) -> list[tuple[str, str, object]]:
        """[(collection, key, 값)] 전체, 넣은 순서 (옮기기용 — app/db/migrate.py)"""
        with self._lock:
            rows = self._conn.execute("SELECT collection, key, value FROM docs ORDER BY rowid").fetchall()
            return [(collection, key, json.loads(value)) for collection, key, value in rows]

    def blob_rows(self) -> list[tuple[str, str, bytes]]:
        with self._lock:
            return self._conn.execute("SELECT kind, key, data FROM blobs").fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()
