"""DATABASE_URL 로 저장소 DB 고르기 — postgresql://… 이면 PostgreSQL(기본), sqlite:///… 이면 SQLite 파일, 비우면 메모리만"""
from typing import Protocol

from app.db.postgres import PostgresDatabase, is_postgres_url
from app.db.sqlite import Database, database_path


class DocumentDB(Protocol):
    """저장소(app/store.py)가 쓰는 DB 함수 — SQLite · PostgreSQL 이 같은 모양"""

    def is_empty(self) -> bool: ...
    def put(self, collection: str, key: str, value) -> None: ...
    def delete(self, collection: str, key: str) -> None: ...
    def all(self, collection: str) -> list[tuple[str, object]]: ...
    def put_blob(self, kind: str, key: str, data: bytes) -> None: ...
    def blobs(self, kind: str) -> dict[str, bytes]: ...
    def rows(self) -> list[tuple[str, str, object]]: ...
    def blob_rows(self) -> list[tuple[str, str, bytes]]: ...
    def close(self) -> None: ...


def clean_url(url: str | None) -> str:
    """.env 의 값 (뒤에 붙은 # 주석 · 공백 제거)"""
    return (url or "").split("#")[0].strip()


def open_database(url: str | None) -> DocumentDB | None:
    url = clean_url(url)
    if is_postgres_url(url):
        return PostgresDatabase(url)
    path = database_path(url)  # sqlite:///… 가 아니면 ValueError
    return Database(path) if path else None


def describe(url: str | None) -> str:
    """로그·상태 표시용 (비밀번호 가림)"""
    url = clean_url(url)
    if is_postgres_url(url):
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds, host = rest.rsplit("@", 1)
            rest = f"{creds.split(':', 1)[0]}:***@{host}" if ":" in creds else rest
        return f"PostgreSQL ({scheme}://{rest})"
    path = database_path(url)
    return f"SQLite ({path})" if path else "메모리 (남기지 않음)"
