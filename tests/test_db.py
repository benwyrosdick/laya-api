from laya_api.db import normalize_database_url


def test_plain_postgres_url_uses_asyncpg():
    assert (
        normalize_database_url("postgresql://laya:secret@host.docker.internal:5432/laya")
        == "postgresql+asyncpg://laya:secret@host.docker.internal:5432/laya"
    )


def test_postgres_scheme_alias():
    assert normalize_database_url("postgres://u:p@db/laya") == "postgresql+asyncpg://u:p@db/laya"


def test_asyncpg_url_unchanged():
    url = "postgresql+asyncpg://laya:secret@db:5432/laya"
    assert normalize_database_url(url) == url


def test_sqlite_url_unchanged():
    assert normalize_database_url("sqlite+aiosqlite://") == "sqlite+aiosqlite://"
