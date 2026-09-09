"""Fixtures de teste. Testes de integração usam o Postgres apontado pelo
ambiente (PGHOST/...); se o banco não estiver acessível, são PULADOS —
assim a suíte roda em qualquer lugar e fica completa quando há DB."""
import os
import tempfile

import pytest

os.environ.setdefault("GOOGLE_API_KEY", "dummy-tests")
# Banners de promoção vão para um tempdir nos testes (não polui o repo).
os.environ.setdefault("MEDIA_DIR", tempfile.mkdtemp(prefix="paratec-media-tests-"))


def _db_disponivel() -> bool:
    try:
        from app.db import get_pool

        with get_pool().connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


DB_OK = _db_disponivel()
requires_db = pytest.mark.skipif(not DB_OK, reason="Postgres indisponível")


@pytest.fixture()
def db():
    """Garante o schema operacional e limpa as tabelas antes de cada teste."""
    from app import store
    from app.db import execute

    store.ensure_schema()
    execute(
        "TRUNCATE messages, events, queue_items, conversations, customers, broadcasts "
        "RESTART IDENTITY CASCADE"
    )
    yield store
