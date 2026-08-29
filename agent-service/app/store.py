"""Persistência operacional do atendimento (conversas, mensagens, eventos, fila).

Fonte de verdade da tela administrativa. Escreve durante o atendimento
(ver agents.responder) e lê nos endpoints /conversas, /metrics e /fila.
"""
from __future__ import annotations

import json
from pathlib import Path

from .db import execute, execute_script, query

_HERE = Path(__file__).resolve()
# Candidatos ao schema em diferentes layouts (repo em dev, /app/db no container).
_SCHEMA_CANDIDATES = (
    _HERE.parents[2] / "db" / "schema_ops.sql",  # repo: Paratec/db/schema_ops.sql
    _HERE.parents[1] / "db" / "schema_ops.sql",  # container: /app/db/schema_ops.sql
    Path.cwd() / "db" / "schema_ops.sql",
)


def _schema_path() -> Path:
    for p in _SCHEMA_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "schema_ops.sql não encontrado em: "
        + ", ".join(str(p) for p in _SCHEMA_CANDIDATES)
    )


def ensure_schema() -> None:
    """Aplica o schema operacional (idempotente). Chamado no startup."""
    execute_script(_schema_path().read_text(encoding="utf-8"))


# --- Escrita durante o atendimento ---------------------------------------

def upsert_conversation(
    thread_id: str,
    cliente: str | None = None,
    telefone: str | None = None,
) -> None:
    execute(
        """
        INSERT INTO conversations (thread_id, cliente, telefone, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (thread_id) DO UPDATE
           SET cliente   = COALESCE(EXCLUDED.cliente, conversations.cliente),
               telefone  = COALESCE(EXCLUDED.telefone, conversations.telefone),
               updated_at = now()
        """,
        (thread_id, cliente, telefone or thread_id),
    )


def add_message(
    thread_id: str,
    role: str,
    content: str,
    especialista: str | None = None,
) -> None:
    execute(
        """INSERT INTO messages (thread_id, role, content, especialista)
             VALUES (%s, %s, %s, %s)""",
        (thread_id, role, content, especialista),
    )
    # Atualiza prévia/roteamento; incrementa não-lidas em mensagens do cliente.
    execute(
        """
        UPDATE conversations
           SET last_preview = %s,
               especialista = COALESCE(%s, especialista),
               unread = CASE WHEN %s = 'cliente' THEN unread + 1 ELSE unread END,
               updated_at = now()
         WHERE thread_id = %s
        """,
        (content[:160], especialista, role, thread_id),
    )


def log_event(
    tipo: str,
    thread_id: str | None = None,
    especialista: str | None = None,
    meta: dict | None = None,
) -> None:
    execute(
        """INSERT INTO events (thread_id, tipo, especialista, meta)
             VALUES (%s, %s, %s, %s)""",
        (thread_id, tipo, especialista, json.dumps(meta) if meta else None),
    )


def set_status(thread_id: str, status: str) -> None:
    execute(
        "UPDATE conversations SET status = %s, updated_at = now() WHERE thread_id = %s",
        (status, thread_id),
    )


def add_queue_item(
    tipo: str,
    resumo: str,
    thread_id: str | None = None,
    cliente: str | None = None,
    telefone: str | None = None,
    payload: dict | None = None,
) -> int:
    rows = execute(
        """
        INSERT INTO queue_items (tipo, thread_id, cliente, telefone, resumo, payload)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (tipo, thread_id, cliente, telefone, resumo, json.dumps(payload) if payload else None),
        returning=True,
    )
    return rows[0]["id"]


# --- Leitura (endpoints da tela adm) -------------------------------------

def list_conversations(status: str | None = None, limit: int = 100) -> list[dict]:
    where = "WHERE status = %s" if status else ""
    params: tuple = (status, limit) if status else (limit,)
    return query(
        f"""
        SELECT thread_id, cliente, telefone, status, especialista, unread,
               last_preview, created_at, updated_at
          FROM conversations
          {where}
         ORDER BY updated_at DESC
         LIMIT %s
        """,
        params,
    )


def get_conversation(thread_id: str) -> dict | None:
    rows = query(
        """SELECT thread_id, cliente, telefone, status, especialista, unread,
                  last_preview, created_at, updated_at
             FROM conversations WHERE thread_id = %s""",
        (thread_id,),
    )
    if not rows:
        return None
    conv = rows[0]
    conv["mensagens"] = query(
        """SELECT role, content, especialista, created_at
             FROM messages WHERE thread_id = %s ORDER BY created_at""",
        (thread_id,),
    )
    return conv


def assumir_conversation(thread_id: str) -> dict | None:
    execute(
        """UPDATE conversations SET status = 'humano', unread = 0, updated_at = now()
             WHERE thread_id = %s""",
        (thread_id,),
    )
    log_event("handoff_humano", thread_id=thread_id, meta={"origem": "manual"})
    return get_conversation(thread_id)


def list_queue(tipo: str | None = None, status: str | None = None) -> list[dict]:
    conds, params = [], []
    if tipo:
        conds.append("tipo = %s")
        params.append(tipo)
    if status:
        conds.append("status = %s")
        params.append(status)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return query(
        f"""
        SELECT id, tipo, thread_id, cliente, telefone, resumo, status,
               responsavel, payload, created_at, updated_at
          FROM queue_items
          {where}
         ORDER BY (status = 'concluido'), created_at DESC
        """,
        tuple(params),
    )


def update_queue_item(
    item_id: int,
    status: str | None = None,
    responsavel: str | None = None,
) -> dict | None:
    rows = execute(
        """
        UPDATE queue_items
           SET status = COALESCE(%s, status),
               responsavel = COALESCE(%s, responsavel),
               updated_at = now()
         WHERE id = %s
        RETURNING id, tipo, thread_id, cliente, telefone, resumo, status,
                  responsavel, payload, created_at, updated_at
        """,
        (status, responsavel, item_id),
        returning=True,
    )
    return rows[0] if rows else None


# --- Métricas (dashboard) -------------------------------------------------

def metrics_overview() -> dict:
    """Agrega eventos/fila para os cards e gráficos do dashboard."""
    # Volume por dia (últimos 7 dias): atendimentos = conversas com mensagem
    # recebida; humano = handoffs. generate_series garante os 7 dias mesmo sem dados.
    semana = query(
        """
        WITH dias AS (
          SELECT generate_series(
                   (now()::date - INTERVAL '6 days'),
                   now()::date, INTERVAL '1 day')::date AS dia
        )
        SELECT d.dia,
               COALESCE(a.n, 0) AS atendimentos,
               COALESCE(h.n, 0) AS humano
          FROM dias d
          LEFT JOIN (
            SELECT created_at::date AS dia, count(DISTINCT thread_id) AS n
              FROM events WHERE tipo = 'mensagem_recebida'
             GROUP BY 1
          ) a ON a.dia = d.dia
          LEFT JOIN (
            SELECT created_at::date AS dia, count(*) AS n
              FROM events WHERE tipo = 'handoff_humano'
             GROUP BY 1
          ) h ON h.dia = d.dia
         ORDER BY d.dia
        """
    )
    especialistas = query(
        """SELECT especialista AS nome, count(*) AS valor
             FROM events
            WHERE tipo = 'roteou_especialista' AND especialista IS NOT NULL
            GROUP BY especialista ORDER BY valor DESC"""
    )
    totais = query(
        """
        SELECT
          (SELECT count(*) FROM conversations)                                AS conversas,
          (SELECT count(*) FROM events WHERE tipo = 'mensagem_recebida')      AS atendimentos,
          (SELECT count(*) FROM events WHERE tipo = 'handoff_humano')         AS handoffs,
          (SELECT count(*) FROM queue_items WHERE status <> 'concluido')      AS na_fila
        """
    )[0]
    atend = totais["atendimentos"] or 0
    handoffs = totais["handoffs"] or 0
    totais["resolvidos_pct"] = (
        round((atend - handoffs) / atend * 100) if atend else 0
    )
    return {"semana": semana, "especialistas": especialistas, "totais": totais}
