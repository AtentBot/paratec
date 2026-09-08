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


# --- Clientes (cadastro) --------------------------------------------------

# Campos obrigatórios p/ o cadastro ser considerado 'ativo'.
CAMPOS_CADASTRO = ("razao_social", "cnpj", "email", "nome_contato")


def get_customer(telefone: str) -> dict | None:
    rows = query(
        """SELECT telefone, razao_social, cnpj, email, nome_contato,
                  status, opt_out, created_at, updated_at
             FROM customers WHERE telefone = %s""",
        (telefone,),
    )
    return rows[0] if rows else None


def cliente_ativo(telefone: str) -> bool:
    c = get_customer(telefone)
    return bool(c and c["status"] == "ativo")


def upsert_customer(telefone: str, **campos) -> dict:
    """Cria/atualiza o cliente com os campos informados (parciais) e recalcula
    o status: 'ativo' quando os 4 campos obrigatórios estão preenchidos."""
    dados = {k: campos.get(k) for k in CAMPOS_CADASTRO}
    execute(
        """
        INSERT INTO customers (telefone, razao_social, cnpj, email, nome_contato)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (telefone) DO UPDATE SET
            razao_social = COALESCE(EXCLUDED.razao_social, customers.razao_social),
            cnpj         = COALESCE(EXCLUDED.cnpj,         customers.cnpj),
            email        = COALESCE(EXCLUDED.email,        customers.email),
            nome_contato = COALESCE(EXCLUDED.nome_contato, customers.nome_contato),
            updated_at   = now()
        """,
        (telefone, dados["razao_social"], dados["cnpj"], dados["email"], dados["nome_contato"]),
    )
    # Recalcula status a partir do estado consolidado.
    execute(
        """
        UPDATE customers SET status = CASE
            WHEN razao_social IS NOT NULL AND cnpj IS NOT NULL
             AND email IS NOT NULL AND nome_contato IS NOT NULL
            THEN 'ativo' ELSE 'pendente' END,
            updated_at = now()
         WHERE telefone = %s
        """,
        (telefone,),
    )
    return get_customer(telefone)  # type: ignore[return-value]


def list_customers(status: str | None = None, limit: int = 200) -> list[dict]:
    where = "WHERE status = %s" if status else ""
    params: tuple = (status, limit) if status else (limit,)
    return query(
        f"""SELECT telefone, razao_social, cnpj, email, nome_contato,
                   status, opt_out, created_at, updated_at
              FROM customers {where}
             ORDER BY created_at DESC LIMIT %s""",
        params,
    )


def set_opt_out(telefone: str, value: bool = True) -> None:
    execute(
        "UPDATE customers SET opt_out = %s, updated_at = now() WHERE telefone = %s",
        (value, telefone),
    )


# --- Broadcast (envio em massa) ------------------------------------------

def customers_para_broadcast() -> list[dict]:
    """Clientes ATIVOS que não pediram opt-out (destinatários de campanha)."""
    return query(
        """SELECT telefone, razao_social, nome_contato FROM customers
            WHERE status = 'ativo' AND opt_out = false AND telefone IS NOT NULL"""
    )


def create_broadcast(texto: str, total: int, criado_por: str | None = None) -> int:
    return execute(
        """INSERT INTO broadcasts (texto, total, criado_por) VALUES (%s, %s, %s)
           RETURNING id""",
        (texto, total, criado_por), returning=True,
    )[0]["id"]


def bump_broadcast(bid: int, enviados: int = 0, falhas: int = 0) -> None:
    execute(
        """UPDATE broadcasts SET enviados = enviados + %s, falhas = falhas + %s,
               updated_at = now() WHERE id = %s""",
        (enviados, falhas, bid),
    )


def finish_broadcast(bid: int, status: str = "concluido") -> None:
    execute(
        "UPDATE broadcasts SET status = %s, updated_at = now() WHERE id = %s",
        (status, bid),
    )


def list_broadcasts(limit: int = 50) -> list[dict]:
    return query(
        """SELECT id, texto, total, enviados, falhas, status, criado_por, created_at
             FROM broadcasts ORDER BY created_at DESC LIMIT %s""",
        (limit,),
    )


# --- Relatórios (por período) --------------------------------------------

def relatorio_resumo(desde: str, ate: str) -> dict:
    """Agregados entre `desde` e `ate` (datas YYYY-MM-DD; `ate` inclusivo)."""
    p = (desde, ate) * 7
    return query(
        """
        SELECT
          (SELECT count(DISTINCT thread_id) FROM events
             WHERE tipo='mensagem_recebida' AND created_at >= %s AND created_at < (%s::date + 1)) AS atendimentos,
          (SELECT count(*) FROM events
             WHERE tipo='resolvida' AND created_at >= %s AND created_at < (%s::date + 1)) AS resolvidas,
          (SELECT count(*) FROM events
             WHERE tipo='handoff_humano' AND created_at >= %s AND created_at < (%s::date + 1)) AS handoffs,
          (SELECT count(*) FROM customers
             WHERE created_at >= %s AND created_at < (%s::date + 1)) AS novos_clientes,
          (SELECT count(*) FROM queue_items
             WHERE tipo='pedido' AND created_at >= %s AND created_at < (%s::date + 1)) AS orcamentos,
          (SELECT count(*) FROM broadcasts
             WHERE created_at >= %s AND created_at < (%s::date + 1)) AS campanhas,
          (SELECT count(*) FROM events
             WHERE tipo='opt_out' AND created_at >= %s AND created_at < (%s::date + 1)) AS opt_outs
        """,
        p,
    )[0]


def relatorio_conversas(desde: str, ate: str, limit: int = 100000) -> list[dict]:
    return query(
        """SELECT thread_id, cliente, telefone, status, especialista, responsavel,
                  created_at, updated_at
             FROM conversations
            WHERE created_at >= %s AND created_at < (%s::date + 1)
            ORDER BY created_at DESC LIMIT %s""",
        (desde, ate, limit),
    )


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


def get_status(thread_id: str) -> str | None:
    """Status atual da conversa (ia | humano | resolvida) ou None se não existe.
    Usado pelo /chat para decidir se a IA deve responder automaticamente."""
    rows = query("SELECT status FROM conversations WHERE thread_id = %s", (thread_id,))
    return rows[0]["status"] if rows else None


def set_bot(thread_id: str, ativo: bool) -> dict | None:
    """Liga/desliga a resposta automática da IA nesta conversa.

    ativo=True  -> status 'ia'     (IA responde automaticamente às mensagens);
    ativo=False -> status 'humano' (atendimento humano; IA pausada).

    É o toggle da tela de conversas. Enquanto 'humano'/'resolvida', o /chat
    não aciona o LLM (ver agents.responder)."""
    if ativo:
        execute(
            "UPDATE conversations SET status = 'ia', updated_at = now() WHERE thread_id = %s",
            (thread_id,),
        )
        log_event("retomou_ia", thread_id=thread_id, meta={"origem": "manual"})
    else:
        execute(
            """UPDATE conversations SET status = 'humano', unread = 0, updated_at = now()
                 WHERE thread_id = %s""",
            (thread_id,),
        )
        log_event("handoff_humano", thread_id=thread_id, meta={"origem": "manual"})
    return get_conversation(thread_id)


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

def list_conversations(
    status: str | None = None, q: str | None = None, limit: int = 100
) -> list[dict]:
    conds, params = [], []
    if status:
        conds.append("status = %s")
        params.append(status)
    if q:
        like = f"%{q}%"
        conds.append("(cliente ILIKE %s OR telefone ILIKE %s OR thread_id ILIKE %s)")
        params += [like, like, like]
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    params.append(limit)
    return query(
        f"""
        SELECT thread_id, cliente, telefone, status, especialista, unread,
               last_preview, responsavel, created_at, updated_at
          FROM conversations
          {where}
         ORDER BY updated_at DESC
         LIMIT %s
        """,
        tuple(params),
    )


def get_conversation(thread_id: str) -> dict | None:
    rows = query(
        """SELECT thread_id, cliente, telefone, status, especialista, unread,
                  last_preview, responsavel, created_at, updated_at
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


def add_note(thread_id: str, texto: str, autor: str | None = None) -> None:
    """Nota interna (não vai ao cliente); não altera prévia/não-lidas."""
    conteudo = f"[{autor}] {texto}" if autor else texto
    execute(
        """INSERT INTO messages (thread_id, role, content) VALUES (%s, 'nota', %s)""",
        (thread_id, conteudo),
    )
    execute("UPDATE conversations SET updated_at = now() WHERE thread_id = %s", (thread_id,))


def set_responsavel(thread_id: str, responsavel: str | None) -> dict | None:
    execute(
        "UPDATE conversations SET responsavel = %s, updated_at = now() WHERE thread_id = %s",
        (responsavel, thread_id),
    )
    return get_conversation(thread_id)


def assumir_conversation(thread_id: str) -> dict | None:
    execute(
        """UPDATE conversations SET status = 'humano', unread = 0, updated_at = now()
             WHERE thread_id = %s""",
        (thread_id,),
    )
    log_event("handoff_humano", thread_id=thread_id, meta={"origem": "manual"})
    return get_conversation(thread_id)


def resolver_conversation(thread_id: str) -> dict | None:
    execute(
        """UPDATE conversations SET status = 'resolvida', unread = 0, updated_at = now()
             WHERE thread_id = %s""",
        (thread_id,),
    )
    log_event("resolvida", thread_id=thread_id, meta={"origem": "manual"})
    return get_conversation(thread_id)


def reabrir_conversation(thread_id: str) -> dict | None:
    execute(
        "UPDATE conversations SET status = 'humano', updated_at = now() WHERE thread_id = %s",
        (thread_id,),
    )
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
          (SELECT count(*) FROM queue_items WHERE status <> 'concluido')      AS na_fila,
          (SELECT count(*) FROM conversations WHERE status <> 'resolvida')    AS abertas,
          (SELECT count(*) FROM conversations WHERE status = 'resolvida')     AS resolvidas,
          (SELECT count(*) FROM customers)                                    AS clientes_total,
          (SELECT count(*) FROM customers WHERE status = 'ativo')             AS clientes_ativos,
          (SELECT count(*) FROM customers WHERE opt_out)                      AS opt_outs,
          (SELECT count(*) FROM queue_items
             WHERE tipo = 'pedido' AND status <> 'concluido')                 AS orcamentos_abertos,
          (SELECT count(*) FROM broadcasts)                                   AS campanhas
        """
    )[0]
    atend = totais["atendimentos"] or 0
    handoffs = totais["handoffs"] or 0
    totais["resolvidos_pct"] = (
        round((atend - handoffs) / atend * 100) if atend else 0
    )
    return {"semana": semana, "especialistas": especialistas, "totais": totais}
