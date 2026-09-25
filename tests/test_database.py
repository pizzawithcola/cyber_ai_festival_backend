"""Guard the PostgreSQL driver pinning that prevents import-time crashes."""

from app.database import _postgres_driver_url


def test_postgres_url_forces_psycopg2():
    assert (
        _postgres_driver_url("postgresql://u:p@h:5432/db")
        == "postgresql+psycopg2://u:p@h:5432/db"
    )
    assert (
        _postgres_driver_url("postgres://u:p@h/db")
        == "postgresql+psycopg2://u:p@h/db"
    )


def test_already_pinned_or_non_postgres_urls_are_untouched():
    assert (
        _postgres_driver_url("postgresql+psycopg2://u:p@h/db")
        == "postgresql+psycopg2://u:p@h/db"
    )
    assert _postgres_driver_url("sqlite://") == "sqlite://"
