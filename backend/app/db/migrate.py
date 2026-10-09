"""저장소 DB 옮기기 — 예: 쓰던 SQLite 파일 → PostgreSQL (넣은 순서 그대로)

사용 (backend/ 에서):  python -m app.db.migrate sqlite:///./vision_welding.db postgresql://vision:vision@localhost:5432/vision_welding
받는 쪽이 비어 있어야 함 (덮어쓰지 않음). 표준 용접 기준은 DB 에 없고 늘 data/seed/welding_standards.csv 에서 읽음.
"""
import sys

from app.db.connect import DocumentDB, describe, open_database


def migrate(source: DocumentDB, target: DocumentDB) -> tuple[int, int]:
    """(옮긴 문서 수, 옮긴 사진 수)"""
    if not target.is_empty():
        raise ValueError("받는 DB 가 비어 있지 않습니다 — 덮어쓰지 않으려고 멈춤")
    docs = source.rows()
    for collection, key, value in docs:
        target.put(collection, key, value)
    blobs = source.blob_rows()
    for kind, key, data in blobs:
        target.put_blob(kind, key, data)
    return len(docs), len(blobs)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    source, target = open_database(argv[0]), open_database(argv[1])
    if source is None or target is None:
        print("두 주소 모두 DB 여야 합니다 (메모리는 옮길 수 없음)")
        return 2
    try:
        docs, blobs = migrate(source, target)
    except ValueError as e:
        print(e)
        return 1
    finally:
        source.close()
        target.close()
    print(f"{describe(argv[0])} → {describe(argv[1])}: 문서 {docs}개, 사진 {blobs}개")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
