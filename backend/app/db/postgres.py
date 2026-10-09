"""저장소(app/store.py)를 PostgreSQL 에 남기기 — app/db/sqlite.py 와 같은 함수(put · delete · all · put_blob · blobs)

.env 의 DATABASE_URL=postgresql://사용자:비밀번호@호스트:포트/DB (로컬은 저장소 루트 docker-compose.yml 로 띄움).
표 두 개 — SQLite 와 같은 모양:
  docs(id, collection, key, value)  value 는 json (jsonb 는 키 순서를 바꿔서 쓰지 않음). id 는 처음 넣은 순서 — 덮어써도 그대로
  blobs(kind, key, data)            사진 파일 (bytea)
"""
import json
import threading

import psycopg
from psycopg import sql
from psycopg.types.json import Json

SCHEMES = ("postgresql://", "postgres://")


def is_postgres_url(url: str) -> bool:
    return url.startswith(SCHEMES)


class PostgresDatabase:
    def __init__(self, url: str, schema: str | None = None) -> None:
        """schema: 표를 만들 스키마 (테스트 격리용, 없으면 DB 기본 search_path)"""
        self.url = url
        self.schema = schema
        self._lock = threading.Lock()
        self._conn = self._connect()
        with self._conn.cursor() as cur:
            if schema:
                cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
                cur.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            cur.execute("""
                CREATE TABLE IF NOT EXISTS docs (
                    id BIGSERIAL, collection TEXT NOT NULL, key TEXT NOT NULL, value JSON NOT NULL,
                    PRIMARY KEY (collection, key));
                CREATE INDEX IF NOT EXISTS docs_order ON docs (collection, id);
                CREATE TABLE IF NOT EXISTS blobs (
                    kind TEXT NOT NULL, key TEXT NOT NULL, data BYTEA NOT NULL, PRIMARY KEY (kind, key));
            """)

    def _connect(self) -> psycopg.Connection:
        options = f"-c search_path={self.schema}" if self.schema else ""
        return psycopg.connect(self.url, autocommit=True, options=options)

    def _execute(self, query: str, params: tuple = (), fetch: bool = False) -> list[tuple]:
        """한 번에 한 문장 (autocommit). 연결이 끊겼으면(DB 재시작 등) 한 번 다시 연결해 재시도"""
        with self._lock:
            for attempt in (1, 2):
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(query, params)
                        return cur.fetchall() if fetch else []
                except psycopg.OperationalError:
                    if attempt == 2 or not self._conn.closed:
                        raise
                    self._conn = self._connect()
        return []

    def is_empty(self) -> bool:
        return not self._execute("SELECT 1 FROM docs LIMIT 1", fetch=True)

    def put(self, collection: str, key: str, value) -> None:
        """JSON 으로 저장 (이미 있으면 덮어씀 — 순서는 처음 넣은 자리 그대로)"""
        self._execute(
            "INSERT INTO docs (collection, key, value) VALUES (%s, %s, %s) "
            "ON CONFLICT (collection, key) DO UPDATE SET value = EXCLUDED.value",
            (collection, key, Json(value, dumps=_dumps)))

    def delete(self, collection: str, key: str) -> None:
        self._execute("DELETE FROM docs WHERE collection = %s AND key = %s", (collection, key))

    def all(self, collection: str) -> list[tuple[str, object]]:
        """[(key, 값)] 넣은 순서"""
        return [tuple(row) for row in self._execute(
            "SELECT key, value FROM docs WHERE collection = %s ORDER BY id", (collection,), fetch=True)]

    def put_blob(self, kind: str, key: str, data: bytes) -> None:
        self._execute(
            "INSERT INTO blobs (kind, key, data) VALUES (%s, %s, %s) "
            "ON CONFLICT (kind, key) DO UPDATE SET data = EXCLUDED.data", (kind, key, data))

    def blobs(self, kind: str) -> dict[str, bytes]:
        return {key: bytes(data) for key, data in self._execute(
            "SELECT key, data FROM blobs WHERE kind = %s", (kind,), fetch=True)}

    def rows(self) -> list[tuple[str, str, object]]:
        """[(collection, key, 값)] 전체, 넣은 순서 (옮기기용 — app/db/migrate.py)"""
        return [tuple(row) for row in self._execute("SELECT collection, key, value FROM docs ORDER BY id", fetch=True)]

    def blob_rows(self) -> list[tuple[str, str, bytes]]:
        return [(kind, key, bytes(data)) for kind, key, data in self._execute(
            "SELECT kind, key, data FROM blobs", fetch=True)]

    def drop_schema(self) -> None:
        """테스트가 만든 스키마 지우기 (schema 를 준 경우만)"""
        if self.schema:
            self._execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(self.schema)).as_string(self._conn))

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)
