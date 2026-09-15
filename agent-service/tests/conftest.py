"""Fixtures de teste. Testes de integração usam o Postgres apontado pelo
ambiente (PGHOST/...); se o banco não estiver acessível, são PULADOS —
assim a suíte roda em qualquer lugar e fica completa quando há DB."""
import os
import tempfile

import pytest

os.environ.setdefault("GOOGLE_API_KEY", "dummy-tests")
# Billing desligado por padrão nos testes (assinatura_ativa libera tudo).
os.environ.setdefault("STRIPE_SECRET_KEY", "")
# Banners de promoção vão para um tempdir nos testes (não polui o repo).
os.environ.setdefault("MEDIA_DIR", tempfile.mkdtemp(prefix="atentbot-media-tests-"))


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

# Tabelas operacionais limpas a cada teste. tenants/users/sessions/subscriptions
# NÃO são truncadas: o tenant 'paratec' semeado no schema (+ assinatura cortesia)
# fica estável e serve de tenant de teste.
_TRUNCATE = (
    "TRUNCATE messages, events, queue_items, conversations, customers, "
    "broadcasts, sellers, agents, instances, usage_events RESTART IDENTITY CASCADE"
)


@pytest.fixture()
def db():
    """Garante o schema operacional e limpa as tabelas antes de cada teste."""
    from app import store
    from app.db import execute

    store.ensure_schema()
    execute(_TRUNCATE)
    yield store


@pytest.fixture()
def tid(db):
    """tenant_id de teste (o 'paratec' semeado no schema)."""
    t = db.get_tenant_by_slug("paratec")
    return int(t["id"])


@pytest.fixture(autouse=True)
def _auth_override():
    """Injeta um tenant fake nos endpoints (sem exigir sessão/assinatura reais).
    tenant_id=1 = 1º tenant (paratec). Só ativa se o app importar (deps ok)."""
    try:
        from app import auth, billing
        from app.main import app
    except Exception:
        yield
        return
    ctx = auth.TenantCtx(tenant_id=1, user_id=1, email="teste@atentbot.com",
                         nome="Teste", role="owner")
    app.dependency_overrides[auth.current_tenant] = lambda: ctx
    app.dependency_overrides[billing.require_active_subscription] = lambda: ctx
    yield
    app.dependency_overrides.pop(auth.current_tenant, None)
    app.dependency_overrides.pop(billing.require_active_subscription, None)
