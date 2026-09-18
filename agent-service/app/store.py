"""Persistência operacional do atendimento (conversas, mensagens, eventos, fila).

Fonte de verdade da tela administrativa. Escreve durante o atendimento
(ver agents.responder) e lê nos endpoints /conversas, /metrics e /fila.

MULTI-TENANT: toda função operacional recebe `tenant_id` (1º parâmetro) e
filtra/insere por ele. O isolamento entre clientes é garantido aqui — qualquer
query sem o filtro de tenant é uma falha de isolamento. Funções de conta
(tenants/users/sessions/subscriptions/instances) ficam ao final do arquivo.
"""
from __future__ import annotations

import json
from pathlib import Path

from .db import execute, execute_script, get_pool, query

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


def get_customer(tenant_id: int, telefone: str) -> dict | None:
    rows = query(
        """SELECT telefone, razao_social, cnpj, email, nome_contato,
                  status, opt_out, created_at, updated_at
             FROM customers WHERE tenant_id = %s AND telefone = %s""",
        (tenant_id, telefone),
    )
    return rows[0] if rows else None


def cliente_ativo(tenant_id: int, telefone: str) -> bool:
    c = get_customer(tenant_id, telefone)
    return bool(c and c["status"] == "ativo")


def upsert_customer(tenant_id: int, telefone: str, **campos) -> dict:
    """Cria/atualiza o cliente com os campos informados (parciais) e recalcula
    o status: 'ativo' quando os 4 campos obrigatórios estão preenchidos."""
    dados = {k: campos.get(k) for k in CAMPOS_CADASTRO}
    antes = get_customer(tenant_id, telefone)
    execute(
        """
        INSERT INTO customers (tenant_id, telefone, razao_social, cnpj, email, nome_contato)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (tenant_id, telefone) DO UPDATE SET
            razao_social = COALESCE(EXCLUDED.razao_social, customers.razao_social),
            cnpj         = COALESCE(EXCLUDED.cnpj,         customers.cnpj),
            email        = COALESCE(EXCLUDED.email,        customers.email),
            nome_contato = COALESCE(EXCLUDED.nome_contato, customers.nome_contato),
            updated_at   = now()
        """,
        (tenant_id, telefone, dados["razao_social"], dados["cnpj"], dados["email"], dados["nome_contato"]),
    )
    # Recalcula status a partir do estado consolidado.
    execute(
        """
        UPDATE customers SET status = CASE
            WHEN razao_social IS NOT NULL AND cnpj IS NOT NULL
             AND email IS NOT NULL AND nome_contato IS NOT NULL
            THEN 'ativo' ELSE 'pendente' END,
            updated_at = now()
         WHERE tenant_id = %s AND telefone = %s
        """,
        (tenant_id, telefone),
    )
    depois = get_customer(tenant_id, telefone)
    if depois and depois["status"] == "ativo" and (not antes or antes["status"] != "ativo"):
        _webhook(tenant_id, "cliente.cadastro_completo", depois)
    return depois  # type: ignore[return-value]


def list_customers(tenant_id: int, status: str | None = None, limit: int = 200) -> list[dict]:
    where = "WHERE tenant_id = %s"
    params: list = [tenant_id]
    if status:
        where += " AND status = %s"
        params.append(status)
    params.append(limit)
    return query(
        f"""SELECT telefone, razao_social, cnpj, email, nome_contato,
                   status, opt_out, created_at, updated_at
              FROM customers {where}
             ORDER BY created_at DESC LIMIT %s""",
        tuple(params),
    )


def set_opt_out(tenant_id: int, telefone: str, value: bool = True) -> None:
    execute(
        "UPDATE customers SET opt_out = %s, updated_at = now() WHERE tenant_id = %s AND telefone = %s",
        (value, tenant_id, telefone),
    )


def customer_contexto(tenant_id: int, telefone: str, limite: int = 5) -> dict:
    """Contexto COMPACTO do cliente p/ hiperpersonalização (dado estruturado, sem
    LLM): perfil + últimos orçamentos/solicitações + estatísticas. Token-leve."""
    cliente = get_customer(tenant_id, telefone)
    pedidos = query(
        """SELECT tipo, resumo, status, created_at FROM queue_items
            WHERE tenant_id = %s AND (telefone = %s OR thread_id = %s)
            ORDER BY created_at DESC LIMIT %s""",
        (tenant_id, telefone, telefone, limite),
    )
    stats = query(
        """SELECT count(*) FILTER (WHERE tipo = 'pedido') AS orcamentos,
                  count(*) AS solicitacoes
             FROM queue_items
            WHERE tenant_id = %s AND (telefone = %s OR thread_id = %s)""",
        (tenant_id, telefone, telefone),
    )[0]
    return {"cliente": cliente, "pedidos": pedidos, "stats": stats}


# --- Broadcast (envio em massa) ------------------------------------------

# Segmentos: os subselects também filtram pelo tenant do cliente (c.tenant_id).
_SEGMENTOS = {
    "todos": "",
    "com_orcamento": (
        " AND EXISTS (SELECT 1 FROM queue_items q WHERE q.tenant_id = c.tenant_id"
        " AND q.thread_id = c.telefone AND q.tipo = 'pedido' AND q.status <> 'concluido')"
    ),
    "novos": " AND c.created_at >= now() - interval '30 days'",
    "recentes": (
        " AND EXISTS (SELECT 1 FROM conversations cv WHERE cv.tenant_id = c.tenant_id"
        " AND cv.thread_id = c.telefone AND cv.updated_at >= now() - interval '30 days')"
    ),
}


def customers_para_broadcast(tenant_id: int, segmento: str = "todos") -> list[dict]:
    """Clientes ATIVOS sem opt-out, filtrados pelo segmento (ver _SEGMENTOS)."""
    extra = _SEGMENTOS.get(segmento, "")
    return query(
        f"""SELECT c.telefone, c.razao_social, c.nome_contato FROM customers c
             WHERE c.tenant_id = %s AND c.status = 'ativo' AND c.opt_out = false
               AND c.telefone IS NOT NULL
             {extra}""",
        (tenant_id,),
    )


def contar_segmentos(tenant_id: int) -> dict:
    """Quantos clientes elegíveis em cada segmento (para a tela de promoções)."""
    return {seg: len(customers_para_broadcast(tenant_id, seg)) for seg in _SEGMENTOS}


def customers_por_telefones(tenant_id: int, telefones: list[str]) -> list[dict]:
    """Destinatários selecionados manualmente na tela, filtrados por elegibilidade.

    Mantém só quem está ATIVO e sem opt-out (respeita quem pediu para não
    receber, mesmo que tenha sido marcado). Preserva a ordem/unicidade via IN.
    """
    numeros = [t for t in {t.strip() for t in telefones} if t]
    if not numeros:
        return []
    return query(
        """SELECT c.telefone, c.razao_social, c.nome_contato FROM customers c
             WHERE c.tenant_id = %s AND c.status = 'ativo' AND c.opt_out = false
               AND c.telefone = ANY(%s)""",
        (tenant_id, numeros),
    )


def create_broadcast(
    tenant_id: int, texto: str, total: int, criado_por: str | None = None, imagem: str | None = None
) -> int:
    return execute(
        """INSERT INTO broadcasts (tenant_id, texto, total, criado_por, imagem)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (tenant_id, texto, total, criado_por, imagem), returning=True,
    )[0]["id"]


def bump_broadcast(tenant_id: int, bid: int, enviados: int = 0, falhas: int = 0) -> None:
    execute(
        """UPDATE broadcasts SET enviados = enviados + %s, falhas = falhas + %s,
               updated_at = now() WHERE tenant_id = %s AND id = %s""",
        (enviados, falhas, tenant_id, bid),
    )


def finish_broadcast(tenant_id: int, bid: int, status: str = "concluido") -> None:
    execute(
        "UPDATE broadcasts SET status = %s, updated_at = now() WHERE tenant_id = %s AND id = %s",
        (status, tenant_id, bid),
    )


def list_broadcasts(tenant_id: int, limit: int = 50) -> list[dict]:
    return query(
        """SELECT id, texto, total, enviados, falhas, status, criado_por, imagem, created_at
             FROM broadcasts WHERE tenant_id = %s ORDER BY created_at DESC LIMIT %s""",
        (tenant_id, limit),
    )


# --- Relatórios (por período) --------------------------------------------

def relatorio_resumo(tenant_id: int, desde: str, ate: str) -> dict:
    """Agregados entre `desde` e `ate` (datas YYYY-MM-DD; `ate` inclusivo)."""
    p = (tenant_id, desde, ate) * 7
    return query(
        """
        SELECT
          (SELECT count(DISTINCT thread_id) FROM events
             WHERE tipo='mensagem_recebida' AND tenant_id=%s AND created_at >= %s AND created_at < (%s::date + 1)) AS atendimentos,
          (SELECT count(*) FROM events
             WHERE tipo='resolvida' AND tenant_id=%s AND created_at >= %s AND created_at < (%s::date + 1)) AS resolvidas,
          (SELECT count(*) FROM events
             WHERE tipo='handoff_humano' AND tenant_id=%s AND created_at >= %s AND created_at < (%s::date + 1)) AS handoffs,
          (SELECT count(*) FROM customers
             WHERE tenant_id=%s AND created_at >= %s AND created_at < (%s::date + 1)) AS novos_clientes,
          (SELECT count(*) FROM queue_items
             WHERE tipo='pedido' AND tenant_id=%s AND created_at >= %s AND created_at < (%s::date + 1)) AS orcamentos,
          (SELECT count(*) FROM broadcasts
             WHERE tenant_id=%s AND created_at >= %s AND created_at < (%s::date + 1)) AS campanhas,
          (SELECT count(*) FROM events
             WHERE tipo='opt_out' AND tenant_id=%s AND created_at >= %s AND created_at < (%s::date + 1)) AS opt_outs
        """,
        p,
    )[0]


def relatorio_conversas(tenant_id: int, desde: str, ate: str, limit: int = 100000) -> list[dict]:
    return query(
        """SELECT thread_id, cliente, telefone, status, especialista, responsavel,
                  created_at, updated_at
             FROM conversations
            WHERE tenant_id = %s AND created_at >= %s AND created_at < (%s::date + 1)
            ORDER BY created_at DESC LIMIT %s""",
        (tenant_id, desde, ate, limit),
    )


# --- Escrita durante o atendimento ---------------------------------------

def upsert_conversation(
    tenant_id: int,
    thread_id: str,
    cliente: str | None = None,
    telefone: str | None = None,
    instancia: str | None = None,
) -> None:
    execute(
        """
        INSERT INTO conversations (tenant_id, thread_id, cliente, telefone, instancia, updated_at)
        VALUES (%s, %s, %s, %s, %s, now())
        ON CONFLICT (tenant_id, thread_id) DO UPDATE
           SET cliente   = COALESCE(EXCLUDED.cliente, conversations.cliente),
               telefone  = COALESCE(EXCLUDED.telefone, conversations.telefone),
               instancia = COALESCE(EXCLUDED.instancia, conversations.instancia),
               updated_at = now()
        """,
        (tenant_id, thread_id, cliente, telefone or thread_id, instancia),
    )


def add_message(
    tenant_id: int,
    thread_id: str,
    role: str,
    content: str,
    especialista: str | None = None,
) -> None:
    execute(
        """INSERT INTO messages (tenant_id, thread_id, role, content, especialista)
             VALUES (%s, %s, %s, %s, %s)""",
        (tenant_id, thread_id, role, content, especialista),
    )
    # Atualiza prévia/roteamento; incrementa não-lidas em mensagens do cliente.
    execute(
        """
        UPDATE conversations
           SET last_preview = %s,
               especialista = COALESCE(%s, especialista),
               unread = CASE WHEN %s = 'cliente' THEN unread + 1 ELSE unread END,
               updated_at = now()
         WHERE tenant_id = %s AND thread_id = %s
        """,
        (content[:160], especialista, role, tenant_id, thread_id),
    )
    _publish(tenant_id, thread_id, {"type": "message", "role": role})
    if role == "cliente":
        _webhook(tenant_id, "mensagem.recebida", {"thread_id": thread_id, "autor": role, "texto": content})
    elif role in ("agente", "humano"):
        _webhook(tenant_id, "mensagem.enviada",
                 {"thread_id": thread_id, "autor": role, "texto": content, "especialista": especialista})


def marcar_lida(tenant_id: int, thread_id: str) -> dict | None:
    """Zera o contador de não-lidas (chamado quando o atendente abre a conversa)."""
    execute(
        "UPDATE conversations SET unread = 0 WHERE tenant_id = %s AND thread_id = %s",
        (tenant_id, thread_id),
    )
    return get_conversation(tenant_id, thread_id)


def log_event(
    tenant_id: int,
    tipo: str,
    thread_id: str | None = None,
    especialista: str | None = None,
    meta: dict | None = None,
) -> None:
    execute(
        """INSERT INTO events (tenant_id, thread_id, tipo, especialista, meta)
             VALUES (%s, %s, %s, %s, %s)""",
        (tenant_id, thread_id, tipo, especialista, json.dumps(meta) if meta else None),
    )


def set_status(tenant_id: int, thread_id: str, status: str) -> None:
    rows = execute(
        """UPDATE conversations SET status = %s, updated_at = now()
            WHERE tenant_id = %s AND thread_id = %s
            RETURNING (SELECT c.status FROM conversations c
                        WHERE c.tenant_id = conversations.tenant_id
                          AND c.thread_id = conversations.thread_id) AS anterior""",
        (status, tenant_id, thread_id),
        returning=True,
    )
    if rows and rows[0]["anterior"] != status:
        _webhook_status(tenant_id, thread_id, status)


def _webhook_status(tenant_id: int, thread_id: str, status: str) -> None:
    evento = {"humano": "conversa.transferida_humano", "resolvida": "conversa.resolvida"}.get(status)
    if evento:
        _webhook(tenant_id, evento, {"thread_id": thread_id, "status": status})


def get_status(tenant_id: int, thread_id: str) -> str | None:
    """Status atual da conversa (ia | humano | resolvida) ou None se não existe.
    Usado pelo /chat para decidir se a IA deve responder automaticamente."""
    rows = query(
        "SELECT status FROM conversations WHERE tenant_id = %s AND thread_id = %s",
        (tenant_id, thread_id),
    )
    return rows[0]["status"] if rows else None


def set_bot(tenant_id: int, thread_id: str, ativo: bool) -> dict | None:
    """Liga/desliga a resposta automática da IA nesta conversa.

    ativo=True  -> status 'ia'     (IA responde automaticamente às mensagens);
    ativo=False -> status 'humano' (atendimento humano; IA pausada).

    É o toggle da tela de conversas. Enquanto 'humano'/'resolvida', o /chat
    não aciona o LLM (ver agents.responder)."""
    if ativo:
        execute(
            "UPDATE conversations SET status = 'ia', updated_at = now() WHERE tenant_id = %s AND thread_id = %s",
            (tenant_id, thread_id),
        )
        log_event(tenant_id, "retomou_ia", thread_id=thread_id, meta={"origem": "manual"})
    else:
        execute(
            """UPDATE conversations SET status = 'humano', unread = 0, updated_at = now()
                 WHERE tenant_id = %s AND thread_id = %s""",
            (tenant_id, thread_id),
        )
        log_event(tenant_id, "handoff_humano", thread_id=thread_id, meta={"origem": "manual"})
        _webhook_status(tenant_id, thread_id, "humano")
    return get_conversation(tenant_id, thread_id)


def add_queue_item(
    tenant_id: int,
    tipo: str,
    resumo: str,
    thread_id: str | None = None,
    cliente: str | None = None,
    telefone: str | None = None,
    payload: dict | None = None,
) -> int:
    rows = execute(
        """
        INSERT INTO queue_items (tenant_id, tipo, thread_id, cliente, telefone, resumo, payload)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (tenant_id, tipo, thread_id, cliente, telefone, resumo, json.dumps(payload) if payload else None),
        returning=True,
    )
    item_id = rows[0]["id"]
    dados = {"id": item_id, "tipo": tipo, "thread_id": thread_id, "cliente": cliente,
             "telefone": telefone, "resumo": resumo, "payload": payload or {}}
    _webhook(tenant_id, "fila.item_criado", dados)
    if tipo == "pedido":
        _webhook(tenant_id, "orcamento.criado", dados)
    return item_id


# --- Leitura (endpoints da tela adm) -------------------------------------

def list_conversations(
    tenant_id: int, status: str | None = None, q: str | None = None, limit: int = 100
) -> list[dict]:
    conds = ["tenant_id = %s"]
    params: list = [tenant_id]
    if status:
        conds.append("status = %s")
        params.append(status)
    if q:
        like = f"%{q}%"
        conds.append("(cliente ILIKE %s OR telefone ILIKE %s OR thread_id ILIKE %s)")
        params += [like, like, like]
    where = "WHERE " + " AND ".join(conds)
    params.append(limit)
    return query(
        f"""
        SELECT thread_id, cliente, telefone, instancia, status, especialista, unread,
               last_preview, responsavel, created_at, updated_at
          FROM conversations
          {where}
         ORDER BY updated_at DESC
         LIMIT %s
        """,
        tuple(params),
    )


def unread_total(tenant_id: int) -> int:
    """Soma de mensagens não-lidas nas conversas do tenant (indicador global)."""
    rows = query(
        "SELECT COALESCE(SUM(unread), 0) AS n FROM conversations WHERE tenant_id = %s",
        (tenant_id,),
    )
    return int(rows[0]["n"]) if rows else 0


def get_conversation(tenant_id: int, thread_id: str) -> dict | None:
    rows = query(
        """SELECT thread_id, cliente, telefone, instancia, status, especialista, unread,
                  last_preview, responsavel, created_at, updated_at
             FROM conversations WHERE tenant_id = %s AND thread_id = %s""",
        (tenant_id, thread_id),
    )
    if not rows:
        return None
    conv = rows[0]
    conv["mensagens"] = query(
        """SELECT role, content, especialista, created_at
             FROM messages WHERE tenant_id = %s AND thread_id = %s ORDER BY created_at""",
        (tenant_id, thread_id),
    )
    return conv


def add_note(tenant_id: int, thread_id: str, texto: str, autor: str | None = None) -> None:
    """Nota interna (não vai ao cliente); não altera prévia/não-lidas."""
    conteudo = f"[{autor}] {texto}" if autor else texto
    execute(
        """INSERT INTO messages (tenant_id, thread_id, role, content) VALUES (%s, %s, 'nota', %s)""",
        (tenant_id, thread_id, conteudo),
    )
    execute(
        "UPDATE conversations SET updated_at = now() WHERE tenant_id = %s AND thread_id = %s",
        (tenant_id, thread_id),
    )
    _publish(tenant_id, thread_id, {"type": "message", "role": "nota"})


def set_responsavel(tenant_id: int, thread_id: str, responsavel: str | None) -> dict | None:
    execute(
        "UPDATE conversations SET responsavel = %s, updated_at = now() WHERE tenant_id = %s AND thread_id = %s",
        (responsavel, tenant_id, thread_id),
    )
    return get_conversation(tenant_id, thread_id)


def assumir_conversation(tenant_id: int, thread_id: str) -> dict | None:
    execute(
        """UPDATE conversations SET status = 'humano', unread = 0, updated_at = now()
             WHERE tenant_id = %s AND thread_id = %s""",
        (tenant_id, thread_id),
    )
    log_event(tenant_id, "handoff_humano", thread_id=thread_id, meta={"origem": "manual"})
    _webhook_status(tenant_id, thread_id, "humano")
    return get_conversation(tenant_id, thread_id)


def resolver_conversation(tenant_id: int, thread_id: str) -> dict | None:
    execute(
        """UPDATE conversations SET status = 'resolvida', unread = 0, updated_at = now()
             WHERE tenant_id = %s AND thread_id = %s""",
        (tenant_id, thread_id),
    )
    log_event(tenant_id, "resolvida", thread_id=thread_id, meta={"origem": "manual"})
    _webhook_status(tenant_id, thread_id, "resolvida")
    return get_conversation(tenant_id, thread_id)


def reabrir_conversation(tenant_id: int, thread_id: str) -> dict | None:
    execute(
        "UPDATE conversations SET status = 'humano', updated_at = now() WHERE tenant_id = %s AND thread_id = %s",
        (tenant_id, thread_id),
    )
    return get_conversation(tenant_id, thread_id)


def list_queue(tenant_id: int, tipo: str | None = None, status: str | None = None) -> list[dict]:
    conds = ["tenant_id = %s"]
    params: list = [tenant_id]
    if tipo:
        conds.append("tipo = %s")
        params.append(tipo)
    if status:
        conds.append("status = %s")
        params.append(status)
    where = "WHERE " + " AND ".join(conds)
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
    tenant_id: int,
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
         WHERE tenant_id = %s AND id = %s
        RETURNING id, tipo, thread_id, cliente, telefone, resumo, status,
                  responsavel, payload, created_at, updated_at
        """,
        (status, responsavel, tenant_id, item_id),
        returning=True,
    )
    if rows:
        _webhook(tenant_id, "fila.item_atualizado", rows[0])
    return rows[0] if rows else None


# --- Equipe de vendas (vendedores) ---------------------------------------

_SELLER_COLS = "id, nome, telefone, email, ativo, created_at, updated_at"


def list_sellers(tenant_id: int, only_ativo: bool = False) -> list[dict]:
    where = "WHERE tenant_id = %s"
    if only_ativo:
        where += " AND ativo = true"
    return query(f"SELECT {_SELLER_COLS} FROM sellers {where} ORDER BY nome", (tenant_id,))


def get_seller(tenant_id: int, seller_id: int) -> dict | None:
    rows = query(
        f"SELECT {_SELLER_COLS} FROM sellers WHERE tenant_id = %s AND id = %s",
        (tenant_id, seller_id),
    )
    return rows[0] if rows else None


def create_seller(
    tenant_id: int, nome: str, telefone: str, email: str | None = None, ativo: bool = True
) -> dict:
    rows = execute(
        f"""INSERT INTO sellers (tenant_id, nome, telefone, email, ativo)
             VALUES (%s, %s, %s, %s, %s) RETURNING {_SELLER_COLS}""",
        (tenant_id, nome, telefone, email, ativo),
        returning=True,
    )
    return rows[0]


def update_seller(
    tenant_id: int,
    seller_id: int,
    nome: str | None = None,
    telefone: str | None = None,
    email: str | None = None,
    ativo: bool | None = None,
) -> dict | None:
    rows = execute(
        f"""
        UPDATE sellers SET
            nome     = COALESCE(%s, nome),
            telefone = COALESCE(%s, telefone),
            email    = COALESCE(%s, email),
            ativo    = COALESCE(%s, ativo),
            updated_at = now()
         WHERE tenant_id = %s AND id = %s
        RETURNING {_SELLER_COLS}
        """,
        (nome, telefone, email, ativo, tenant_id, seller_id),
        returning=True,
    )
    return rows[0] if rows else None


def delete_seller(tenant_id: int, seller_id: int) -> bool:
    rows = execute(
        "DELETE FROM sellers WHERE tenant_id = %s AND id = %s RETURNING id",
        (tenant_id, seller_id), returning=True,
    )
    return bool(rows)


# --- Agentes (multi-agente por número de WhatsApp) ------------------------

_AGENT_COLS = (
    "id, tenant_id, nome, descricao, instancia, persona, capacidades, ativo, is_default, "
    "hiperpersonalizacao, created_at, updated_at"
)


def list_agents(tenant_id: int) -> list[dict]:
    # Padrão sempre primeiro; demais por nome.
    return query(
        f"SELECT {_AGENT_COLS} FROM agents WHERE tenant_id = %s ORDER BY is_default DESC, nome",
        (tenant_id,),
    )


def get_default_agent(tenant_id: int) -> dict | None:
    rows = query(
        f"SELECT {_AGENT_COLS} FROM agents WHERE tenant_id = %s AND is_default LIMIT 1",
        (tenant_id,),
    )
    return rows[0] if rows else None


def ensure_default_agent(tenant_id: int) -> dict:
    """Garante que o tenant tenha um agente padrão (catch-all). Idempotente —
    chamado ao criar um tenant novo (o da Paratec é semeado no schema)."""
    existing = get_default_agent(tenant_id)
    if existing:
        return existing
    rows = execute(
        f"""INSERT INTO agents (tenant_id, nome, descricao, persona, capacidades, ativo, is_default)
             VALUES (%s, 'Agente padrão',
                     'Atende todos os números que não têm um agente próprio.',
                     NULL, ARRAY['catalogo','pedidos','entrega','boletos','conhecimento'],
                     true, true)
             RETURNING {_AGENT_COLS}""",
        (tenant_id,),
        returning=True,
    )
    return rows[0]


def get_agent(tenant_id: int, agent_id: int) -> dict | None:
    rows = query(
        f"SELECT {_AGENT_COLS} FROM agents WHERE tenant_id = %s AND id = %s",
        (tenant_id, agent_id),
    )
    return rows[0] if rows else None


def get_agent_by_instancia(instancia: str) -> dict | None:
    """Agente ATIVO amarrado a esta instância Evolution (número de WhatsApp).
    A instância é única global, então não precisa de tenant_id — mas o resultado
    inclui tenant_id (usado para resolver o tenant no caminho /chat)."""
    rows = query(
        f"SELECT {_AGENT_COLS} FROM agents WHERE instancia = %s AND ativo = true",
        (instancia,),
    )
    return rows[0] if rows else None


def create_agent(
    tenant_id: int,
    nome: str,
    descricao: str | None,
    instancia: str | None,
    persona: str | None,
    capacidades: list[str],
    ativo: bool = True,
    hiperpersonalizacao: bool = False,
) -> dict:
    rows = execute(
        f"""INSERT INTO agents (tenant_id, nome, descricao, instancia, persona,
                                capacidades, ativo, hiperpersonalizacao)
             VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING {_AGENT_COLS}""",
        (tenant_id, nome, descricao, instancia or None, persona, capacidades, ativo,
         hiperpersonalizacao),
        returning=True,
    )
    return rows[0]


def update_agent(
    tenant_id: int,
    agent_id: int,
    nome: str | None = None,
    descricao: str | None = None,
    instancia: str | None = None,
    persona: str | None = None,
    capacidades: list[str] | None = None,
    ativo: bool | None = None,
    hiperpersonalizacao: bool | None = None,
    *,
    limpar_instancia: bool = False,
) -> dict | None:
    """Atualiza campos informados. `limpar_instancia=True` desamarra o número
    (grava NULL), já que COALESCE sozinho não permite voltar a NULL."""
    inst_sql = "instancia = NULL" if limpar_instancia else "instancia = COALESCE(%s, instancia)"
    params: list = [nome, descricao]
    if not limpar_instancia:
        params.append(instancia or None)
    params += [persona, capacidades, ativo, hiperpersonalizacao, tenant_id, agent_id]
    rows = execute(
        f"""
        UPDATE agents SET
            nome        = COALESCE(%s, nome),
            descricao   = COALESCE(%s, descricao),
            {inst_sql},
            persona     = COALESCE(%s, persona),
            capacidades = COALESCE(%s, capacidades),
            ativo       = COALESCE(%s, ativo),
            hiperpersonalizacao = COALESCE(%s, hiperpersonalizacao),
            updated_at  = now()
         WHERE tenant_id = %s AND id = %s
        RETURNING {_AGENT_COLS}
        """,
        tuple(params),
        returning=True,
    )
    return rows[0] if rows else None


def delete_agent(tenant_id: int, agent_id: int) -> bool:
    rows = execute(
        "DELETE FROM agents WHERE tenant_id = %s AND id = %s AND is_default = false RETURNING id",
        (tenant_id, agent_id), returning=True,
    )
    return bool(rows)


# --- Métricas (dashboard) -------------------------------------------------

def metrics_overview(tenant_id: int) -> dict:
    """Agrega eventos/fila para os cards e gráficos do dashboard (por tenant)."""
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
              FROM events WHERE tipo = 'mensagem_recebida' AND tenant_id = %s
             GROUP BY 1
          ) a ON a.dia = d.dia
          LEFT JOIN (
            SELECT created_at::date AS dia, count(*) AS n
              FROM events WHERE tipo = 'handoff_humano' AND tenant_id = %s
             GROUP BY 1
          ) h ON h.dia = d.dia
         ORDER BY d.dia
        """,
        (tenant_id, tenant_id),
    )
    especialistas = query(
        """SELECT especialista AS nome, count(*) AS valor
             FROM events
            WHERE tipo = 'roteou_especialista' AND especialista IS NOT NULL AND tenant_id = %s
            GROUP BY especialista ORDER BY valor DESC""",
        (tenant_id,),
    )
    totais = query(
        """
        SELECT
          (SELECT count(*) FROM conversations WHERE tenant_id=%s)                          AS conversas,
          (SELECT count(*) FROM events WHERE tipo='mensagem_recebida' AND tenant_id=%s)    AS atendimentos,
          (SELECT count(*) FROM events WHERE tipo='handoff_humano' AND tenant_id=%s)       AS handoffs,
          (SELECT count(*) FROM queue_items WHERE status<>'concluido' AND tenant_id=%s)    AS na_fila,
          (SELECT count(*) FROM conversations WHERE status<>'resolvida' AND tenant_id=%s)  AS abertas,
          (SELECT count(*) FROM conversations WHERE status='resolvida' AND tenant_id=%s)   AS resolvidas,
          (SELECT count(*) FROM customers WHERE tenant_id=%s)                              AS clientes_total,
          (SELECT count(*) FROM customers WHERE status='ativo' AND tenant_id=%s)           AS clientes_ativos,
          (SELECT count(*) FROM customers WHERE opt_out AND tenant_id=%s)                  AS opt_outs,
          (SELECT count(*) FROM queue_items
             WHERE tipo='pedido' AND status<>'concluido' AND tenant_id=%s)                 AS orcamentos_abertos,
          (SELECT count(*) FROM broadcasts WHERE tenant_id=%s)                             AS campanhas
        """,
        (tenant_id,) * 11,
    )[0]
    atend = totais["atendimentos"] or 0
    handoffs = totais["handoffs"] or 0
    totais["resolvidos_pct"] = (
        round((atend - handoffs) / atend * 100) if atend else 0
    )
    return {"semana": semana, "especialistas": especialistas, "totais": totais}


# =========================================================================
# CONTAS: tenants, usuários, sessões, assinaturas, instâncias
# =========================================================================

def _webhook(tenant_id: int, evento: str, dados: dict) -> None:
    """Dispara webhooks de saída do tenant (best-effort, assíncrono)."""
    try:
        from . import webhooks

        webhooks.disparar(tenant_id, evento, dados)
    except Exception:  # pragma: no cover
        pass


def _publish(tenant_id: int, thread_id: str, payload: dict) -> None:
    """Publica evento SSE em canal namespaced por tenant (best-effort)."""
    try:
        from . import realtime

        realtime.broker.publish(f"{tenant_id}:{thread_id}", payload)
    except Exception:  # pragma: no cover
        pass


# --- Tenants --------------------------------------------------------------

def create_tenant(slug: str, nome: str) -> dict:
    rows = execute(
        """INSERT INTO tenants (slug, nome) VALUES (%s, %s)
             RETURNING id, slug, nome, status, stripe_customer_id, created_at""",
        (slug, nome), returning=True,
    )
    return rows[0]


def get_tenant(tenant_id: int) -> dict | None:
    rows = query(
        "SELECT id, slug, nome, status, stripe_customer_id, created_at FROM tenants WHERE id = %s",
        (tenant_id,),
    )
    return rows[0] if rows else None


def get_tenant_by_slug(slug: str) -> dict | None:
    rows = query(
        "SELECT id, slug, nome, status, stripe_customer_id, created_at FROM tenants WHERE slug = %s",
        (slug,),
    )
    return rows[0] if rows else None


def get_tenant_by_instancia(instancia: str) -> int | None:
    """tenant_id dono desta instância Evolution (ou None se não mapeada)."""
    rows = query("SELECT tenant_id FROM instances WHERE instancia = %s", (instancia,))
    return int(rows[0]["tenant_id"]) if rows else None


def set_tenant_stripe_customer(tenant_id: int, customer_id: str) -> None:
    execute(
        "UPDATE tenants SET stripe_customer_id = %s, updated_at = now() WHERE id = %s",
        (customer_id, tenant_id),
    )


# --- Instâncias -----------------------------------------------------------

def register_instance(tenant_id: int, instancia: str) -> None:
    execute(
        """INSERT INTO instances (instancia, tenant_id) VALUES (%s, %s)
             ON CONFLICT (instancia) DO UPDATE SET tenant_id = EXCLUDED.tenant_id""",
        (instancia, tenant_id),
    )


def list_instances(tenant_id: int) -> list[str]:
    """Nomes das instâncias Evolution que pertencem ao tenant."""
    rows = query("SELECT instancia FROM instances WHERE tenant_id = %s ORDER BY instancia",
                 (tenant_id,))
    return [r["instancia"] for r in rows]


def unregister_instance(tenant_id: int, instancia: str) -> None:
    execute(
        "DELETE FROM instances WHERE tenant_id = %s AND instancia = %s",
        (tenant_id, instancia),
    )


# --- Usuários -------------------------------------------------------------

def create_user(
    tenant_id: int, email: str, password_hash: str, nome: str | None = None, role: str = "owner",
    whatsapp: str | None = None,
) -> dict:
    rows = execute(
        """INSERT INTO users (tenant_id, email, password_hash, nome, role, whatsapp)
             VALUES (%s, %s, %s, %s, %s, %s)
             RETURNING id, tenant_id, email, nome, role, ativo, whatsapp, created_at""",
        (tenant_id, email, password_hash, nome, role, whatsapp), returning=True,
    )
    return rows[0]


def get_user_by_email(email: str) -> dict | None:
    """Inclui password_hash (para o login) e tenant_id."""
    rows = query(
        """SELECT id, tenant_id, email, password_hash, nome, role, ativo,
                  email_verificado_em
             FROM users WHERE lower(email) = lower(%s)""",
        (email,),
    )
    return rows[0] if rows else None


def get_user(user_id: int) -> dict | None:
    rows = query(
        "SELECT id, tenant_id, email, nome, role, ativo FROM users WHERE id = %s",
        (user_id,),
    )
    return rows[0] if rows else None


def get_password_hash(user_id: int) -> str | None:
    rows = query("SELECT password_hash FROM users WHERE id = %s", (user_id,))
    return rows[0]["password_hash"] if rows else None


def set_password(user_id: int, password_hash: str) -> None:
    execute(
        "UPDATE users SET password_hash = %s, updated_at = now() WHERE id = %s",
        (password_hash, user_id),
    )


# --- Verificação de e-mail -----------------------------------------------

def create_email_verification(user_id: int, token_hash: str, expires_at) -> None:
    execute(
        "INSERT INTO email_verifications (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user_id, token_hash, expires_at),
    )


def count_recent_email_verifications(user_id: int, minutes: int) -> int:
    rows = query(
        """SELECT count(*) AS n FROM email_verifications
            WHERE user_id = %s AND created_at > now() - make_interval(mins => %s)""",
        (user_id, minutes),
    )
    return int(rows[0]["n"])


def consume_email_verification(token_hash: str) -> dict | None:
    """Consome o token (uso único, não expirado) e marca o e-mail do usuário
    como verificado. Devolve o usuário, ou None se o token é inválido."""
    rows = execute(
        """WITH v AS (
               UPDATE email_verifications SET used_at = now()
                WHERE token_hash = %s AND used_at IS NULL AND expires_at > now()
                RETURNING user_id
           )
           UPDATE users u
              SET email_verificado_em = COALESCE(u.email_verificado_em, now()),
                  updated_at = now()
             FROM v
            WHERE u.id = v.user_id AND u.ativo = true
        RETURNING u.id, u.tenant_id, u.email, u.nome, u.role""",
        (token_hash,), returning=True,
    )
    return rows[0] if rows else None


def mark_email_verified(user_id: int) -> None:
    execute(
        """UPDATE users SET email_verificado_em = COALESCE(email_verificado_em, now()),
                            updated_at = now() WHERE id = %s""",
        (user_id,),
    )


# --- Configurações da plataforma ------------------------------------------

def get_platform_setting(chave: str) -> str | None:
    rows = query("SELECT valor FROM platform_settings WHERE chave = %s", (chave,))
    return rows[0]["valor"] if rows else None


def set_platform_setting(chave: str, valor: str | None, user_id: int | None = None) -> None:
    """Grava (ou apaga, com valor None) uma configuração da plataforma."""
    if valor is None:
        execute("DELETE FROM platform_settings WHERE chave = %s", (chave,))
        return
    execute(
        """INSERT INTO platform_settings (chave, valor, updated_by) VALUES (%s, %s, %s)
             ON CONFLICT (chave) DO UPDATE
                SET valor = EXCLUDED.valor, updated_by = EXCLUDED.updated_by, updated_at = now()""",
        (chave, valor, user_id),
    )


# --- Verificação de WhatsApp ---------------------------------------------

def create_whatsapp_verification(user_id: int, telefone: str, code_hash: str, expires_at) -> None:
    """Novo código para o usuário; os anteriores ainda não usados deixam de valer."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE whatsapp_verifications SET used_at = now()
                    WHERE user_id = %s AND used_at IS NULL""",
                (user_id,),
            )
            cur.execute(
                """INSERT INTO whatsapp_verifications (user_id, telefone, code_hash, expires_at)
                   VALUES (%s, %s, %s, %s)""",
                (user_id, telefone, code_hash, expires_at),
            )


def whatsapp_verifications_recentes(user_id: int, minutes: int) -> dict:
    """Quantos códigos foram gerados na janela e quando saiu o último."""
    rows = query(
        """SELECT count(*) AS n, max(created_at) AS ultimo FROM whatsapp_verifications
            WHERE user_id = %s AND created_at > now() - make_interval(mins => %s)""",
        (user_id, minutes),
    )
    return {"n": int(rows[0]["n"]), "ultimo": rows[0]["ultimo"]}


def get_active_whatsapp_verification(user_id: int) -> dict | None:
    rows = query(
        """SELECT id, telefone, code_hash, tentativas FROM whatsapp_verifications
            WHERE user_id = %s AND used_at IS NULL AND expires_at > now()
            ORDER BY created_at DESC LIMIT 1""",
        (user_id,),
    )
    return rows[0] if rows else None


def increment_whatsapp_attempt(verification_id: int) -> None:
    execute(
        "UPDATE whatsapp_verifications SET tentativas = tentativas + 1 WHERE id = %s",
        (verification_id,),
    )


def whatsapp_em_uso(telefone: str, exceto_user_id: int) -> bool:
    rows = query(
        """SELECT 1 FROM users WHERE whatsapp = %s AND whatsapp_verificado_em IS NOT NULL
              AND id <> %s LIMIT 1""",
        (telefone, exceto_user_id),
    )
    return bool(rows)


def confirm_whatsapp_verification(verification_id: int, user_id: int, telefone: str) -> None:
    """Consome o código e grava o número como WhatsApp verificado do usuário."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE whatsapp_verifications SET used_at = now() WHERE id = %s",
                (verification_id,),
            )
            cur.execute(
                """UPDATE users SET whatsapp = %s, whatsapp_verificado_em = now(),
                                    updated_at = now() WHERE id = %s""",
                (telefone, user_id),
            )


def mark_whatsapp_verified(user_id: int) -> None:
    """Marca como verificado sem código (contas semeadas pela equipe)."""
    execute(
        """UPDATE users SET whatsapp_verificado_em = COALESCE(whatsapp_verificado_em, now()),
                            updated_at = now() WHERE id = %s""",
        (user_id,),
    )


def set_user_whatsapp(user_id: int, telefone: str) -> None:
    """Troca o número (ainda não verificado) informado pelo usuário."""
    execute(
        """UPDATE users SET whatsapp = %s, whatsapp_verificado_em = NULL, updated_at = now()
            WHERE id = %s AND whatsapp_verificado_em IS NULL""",
        (telefone, user_id),
    )


# --- Sessões --------------------------------------------------------------

def create_session(user_id: int, token_hash: str, expires_at) -> None:
    execute(
        "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user_id, token_hash, expires_at),
    )


def get_session(token_hash: str) -> dict | None:
    """Sessão válida (não expirada) + dados do usuário e tenant."""
    rows = query(
        """SELECT s.id, s.user_id, s.expires_at,
                  u.tenant_id, u.email, u.nome, u.role, u.ativo, u.is_staff,
                  u.whatsapp, u.whatsapp_verificado_em
             FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.expires_at > now() AND u.ativo = true
              AND u.email_verificado_em IS NOT NULL""",
        (token_hash,),
    )
    return rows[0] if rows else None


def touch_session(token_hash: str) -> None:
    execute(
        "UPDATE sessions SET last_seen_at = now() WHERE token_hash = %s",
        (token_hash,),
    )


def delete_session(token_hash: str) -> None:
    execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash,))


# --- Assinaturas ----------------------------------------------------------

def upsert_subscription(
    tenant_id: int,
    *,
    stripe_subscription_id: str | None = None,
    stripe_customer_id: str | None = None,
    plan: str | None = None,
    stripe_price_id: str | None = None,
    status: str | None = None,
    cancel_at_period_end: bool | None = None,
    current_period_end=None,
    current_period_start=None,
) -> dict:
    """Cria/atualiza a assinatura do tenant (1 por tenant). COALESCE mantém os
    campos não informados."""
    rows = execute(
        """
        INSERT INTO subscriptions
            (tenant_id, stripe_subscription_id, stripe_customer_id, plan,
             stripe_price_id, status, cancel_at_period_end, current_period_end,
             current_period_start)
        VALUES (%s, %s, %s, %s, %s, COALESCE(%s,'incomplete'), COALESCE(%s,false), %s, %s)
        ON CONFLICT (tenant_id) DO UPDATE SET
            stripe_subscription_id = COALESCE(EXCLUDED.stripe_subscription_id, subscriptions.stripe_subscription_id),
            stripe_customer_id     = COALESCE(EXCLUDED.stripe_customer_id, subscriptions.stripe_customer_id),
            plan                   = COALESCE(EXCLUDED.plan, subscriptions.plan),
            stripe_price_id        = COALESCE(EXCLUDED.stripe_price_id, subscriptions.stripe_price_id),
            status                 = COALESCE(%s, subscriptions.status),
            cancel_at_period_end   = COALESCE(%s, subscriptions.cancel_at_period_end),
            current_period_end     = COALESCE(EXCLUDED.current_period_end, subscriptions.current_period_end),
            current_period_start   = COALESCE(EXCLUDED.current_period_start, subscriptions.current_period_start),
            updated_at             = now()
        RETURNING tenant_id, stripe_subscription_id, stripe_customer_id, plan,
                  stripe_price_id, status, cancel_at_period_end, current_period_end,
                  current_period_start
        """,
        (tenant_id, stripe_subscription_id, stripe_customer_id, plan, stripe_price_id,
         status, cancel_at_period_end, current_period_end, current_period_start,
         status, cancel_at_period_end),
        returning=True,
    )
    return rows[0]


def get_subscription(tenant_id: int) -> dict | None:
    rows = query(
        """SELECT tenant_id, stripe_subscription_id, stripe_customer_id, plan,
                  stripe_price_id, status, cancel_at_period_end, current_period_end,
                  current_period_start
             FROM subscriptions WHERE tenant_id = %s""",
        (tenant_id,),
    )
    return rows[0] if rows else None


def get_subscription_tenant_by_customer(stripe_customer_id: str) -> int | None:
    rows = query(
        "SELECT tenant_id FROM subscriptions WHERE stripe_customer_id = %s",
        (stripe_customer_id,),
    )
    if rows:
        return int(rows[0]["tenant_id"])
    # fallback: pelo customer gravado no tenant (antes do 1º webhook de subscription)
    rows = query("SELECT id FROM tenants WHERE stripe_customer_id = %s", (stripe_customer_id,))
    return int(rows[0]["id"]) if rows else None


# --- Idempotência de webhooks --------------------------------------------

def stripe_event_seen(event_id: str, tipo: str | None = None) -> bool:
    """Registra o evento; retorna True se JÁ foi visto antes (deve ser ignorado)."""
    rows = execute(
        "INSERT INTO stripe_events (id, type) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING RETURNING id",
        (event_id, tipo), returning=True,
    )
    return not rows  # sem linha inserida = conflito = já visto


# --- Medição de consumo (pay-per-use por tokens) --------------------------

def record_usage(
    tenant_id: int, tipo: str, tokens: int, custo_estimado: float, meta: dict | None = None
) -> None:
    """Registra um evento de consumo (best-effort — nunca deve quebrar o fluxo)."""
    if tokens <= 0:
        return
    execute(
        """INSERT INTO usage_events (tenant_id, tipo, tokens, custo_estimado, meta)
             VALUES (%s, %s, %s, %s, %s)""",
        (tenant_id, tipo, int(tokens), custo_estimado, json.dumps(meta) if meta else None),
    )


def usage_periodo(tenant_id: int) -> dict:
    """Resumo do consumo do MÊS corrente (total + quebra por tipo)."""
    total = query(
        """SELECT COALESCE(SUM(tokens),0) AS tokens,
                  COALESCE(SUM(custo_estimado),0) AS custo,
                  count(*) AS eventos
             FROM usage_events
            WHERE tenant_id = %s AND created_at >= date_trunc('month', now())""",
        (tenant_id,),
    )[0]
    por_tipo = query(
        """SELECT tipo, COALESCE(SUM(tokens),0) AS tokens,
                  COALESCE(SUM(custo_estimado),0) AS custo, count(*) AS eventos
             FROM usage_events
            WHERE tenant_id = %s AND created_at >= date_trunc('month', now())
            GROUP BY tipo ORDER BY custo DESC""",
        (tenant_id,),
    )
    return {"tokens": int(total["tokens"]), "custo": float(total["custo"]),
            "eventos": int(total["eventos"]), "por_tipo": por_tipo}


def usage_recentes(tenant_id: int, limit: int = 20) -> list[dict]:
    return query(
        """SELECT tipo, tokens, custo_estimado, meta, created_at
             FROM usage_events WHERE tenant_id = %s
            ORDER BY created_at DESC LIMIT %s""",
        (tenant_id, limit),
    )


# --- Pesquisa de cancelamento --------------------------------------------

def record_cancellation_feedback(
    tenant_id: int, respostas: dict | None, comentario: str | None
) -> None:
    """Guarda a pesquisa de cancelamento (motivos + relato). Best-effort."""
    execute(
        """INSERT INTO cancellation_feedback (tenant_id, respostas, comentario)
             VALUES (%s, %s, %s)""",
        (tenant_id, json.dumps(respostas) if respostas else None, comentario),
    )


# --- Suporte: chamados (tickets) ------------------------------------------

_TICKET_COLS = ("id, assunto, categoria, prioridade, status, created_at, updated_at")


def create_ticket(
    tenant_id: int, user_id: int | None, assunto: str, categoria: str,
    prioridade: str, descricao: str,
) -> dict:
    rows = execute(
        f"""INSERT INTO tickets (tenant_id, user_id, assunto, categoria, prioridade)
             VALUES (%s, %s, %s, %s, %s) RETURNING {_TICKET_COLS}""",
        (tenant_id, user_id, assunto, categoria, prioridade), returning=True,
    )
    t = rows[0]
    # a descrição inicial vira a primeira mensagem do chamado
    execute(
        """INSERT INTO ticket_mensagens (ticket_id, tenant_id, autor, corpo)
             VALUES (%s, %s, 'cliente', %s)""",
        (t["id"], tenant_id, descricao),
    )
    return t


def list_tickets(tenant_id: int, status: str | None = None) -> list[dict]:
    where = "WHERE t.tenant_id = %s"
    params: list = [tenant_id]
    if status:
        where += " AND t.status = %s"
        params.append(status)
    return query(
        f"""SELECT {', '.join('t.' + c for c in _TICKET_COLS.split(', '))},
                  (SELECT count(*) FROM ticket_mensagens m WHERE m.ticket_id = t.id) AS mensagens
             FROM tickets t {where}
            ORDER BY (t.status IN ('resolvido','fechado')), t.updated_at DESC""",
        tuple(params),
    )


def get_ticket(tenant_id: int, ticket_id: int) -> dict | None:
    rows = query(
        f"SELECT {_TICKET_COLS} FROM tickets WHERE tenant_id = %s AND id = %s",
        (tenant_id, ticket_id),
    )
    if not rows:
        return None
    t = rows[0]
    t["mensagens"] = query(
        """SELECT autor, corpo, created_at FROM ticket_mensagens
            WHERE ticket_id = %s AND tenant_id = %s ORDER BY created_at""",
        (ticket_id, tenant_id),
    )
    return t


def add_ticket_message(
    tenant_id: int, ticket_id: int, autor: str, corpo: str
) -> dict | None:
    """Adiciona mensagem ao chamado e atualiza o updated_at (best-effort de status:
    mensagem do cliente reabre um chamado resolvido)."""
    if not get_ticket(tenant_id, ticket_id):
        return None
    execute(
        """INSERT INTO ticket_mensagens (ticket_id, tenant_id, autor, corpo)
             VALUES (%s, %s, %s, %s)""",
        (ticket_id, tenant_id, autor, corpo),
    )
    novo_status = "aberto" if autor == "cliente" else "em_andamento"
    execute(
        """UPDATE tickets SET updated_at = now(),
               status = CASE WHEN status IN ('resolvido','fechado') THEN %s ELSE status END
             WHERE tenant_id = %s AND id = %s""",
        (novo_status, tenant_id, ticket_id),
    )
    return get_ticket(tenant_id, ticket_id)


def set_ticket_status(tenant_id: int, ticket_id: int, status: str) -> dict | None:
    rows = execute(
        f"""UPDATE tickets SET status = %s, updated_at = now()
             WHERE tenant_id = %s AND id = %s RETURNING {_TICKET_COLS}""",
        (status, tenant_id, ticket_id), returning=True,
    )
    if not rows:
        return None
    return get_ticket(tenant_id, ticket_id)


# =========================================================================
# ADMIN (central da equipe Dew) — consultas CROSS-TENANT. Só devem ser
# chamadas por endpoints protegidos por current_admin (auth.is_staff).
# =========================================================================

def set_user_staff(email: str, value: bool = True) -> bool:
    rows = execute(
        "UPDATE users SET is_staff = %s, updated_at = now() WHERE lower(email) = lower(%s) RETURNING id",
        (value, email), returning=True,
    )
    return bool(rows)


def admin_overview() -> dict:
    return query(
        """SELECT
             (SELECT count(*) FROM tenants)                                             AS tenants,
             (SELECT count(*) FROM subscriptions WHERE status = 'active')              AS ativos,
             (SELECT count(*) FROM tickets WHERE status IN ('aberto','em_andamento'))   AS chamados_abertos,
             (SELECT COALESCE(SUM(custo_estimado),0) FROM usage_events
                WHERE created_at >= date_trunc('month', now()))                         AS consumo_mes
        """
    )[0]


def admin_list_tenants(q: str | None = None, limit: int = 25, offset: int = 0) -> list[dict]:
    where, params = "", []
    if q:
        where = "WHERE (t.nome ILIKE %s OR t.slug ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    return query(
        f"""SELECT t.id, t.nome, t.slug, t.status AS tenant_status, t.created_at,
                  s.plan, s.status AS sub_status, s.cancel_at_period_end, s.current_period_end,
                  (SELECT count(*) FROM users u WHERE u.tenant_id = t.id) AS usuarios
             FROM tenants t LEFT JOIN subscriptions s ON s.tenant_id = t.id
            {where}
            ORDER BY t.created_at
            LIMIT %s OFFSET %s""",
        (*params, limit, offset),
    )


def admin_count_tenants(q: str | None = None) -> int:
    where, params = "", []
    if q:
        where = "WHERE (nome ILIKE %s OR slug ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    return int(query(f"SELECT count(*) AS n FROM tenants {where}", tuple(params))[0]["n"])


def admin_set_subscription(tenant_id: int, status: str, plan: str | None = None) -> dict:
    """Override manual da assinatura (comp/suspensão). Mantém o restante."""
    return upsert_subscription(tenant_id, status=status, plan=plan)


# --- Planos (preço base parametrizável) -----------------------------------

_PLAN_COLS = """id, nome, preco::float AS preco, descricao, ordem, stripe_product_id,
                stripe_price_id, mensagens_incluidas, updated_by, updated_at"""


def list_plans() -> list[dict]:
    return query(f"SELECT {_PLAN_COLS} FROM plans ORDER BY ordem, id")


def get_plan(plan_id: str) -> dict | None:
    rows = query(f"SELECT {_PLAN_COLS} FROM plans WHERE id = %s", (plan_id,))
    return rows[0] if rows else None


def plan_by_price_id(price_id: str) -> str | None:
    """Plano de um price id do Stripe: o vigente ou qualquer um do histórico."""
    rows = query(
        """SELECT id FROM plans WHERE stripe_price_id = %s
           UNION
           SELECT plan_id FROM plan_price_history
            WHERE stripe_price_id_novo = %s OR stripe_price_id_anterior = %s
           LIMIT 1""",
        (price_id, price_id, price_id),
    )
    return rows[0]["id"] if rows else None


def update_plan_price(plan_id: str, preco: float, *, stripe_price_id: str | None,
                      stripe_product_id: str | None, preco_anterior: float | None,
                      stripe_price_id_anterior: str | None, migradas: int, falhas: int,
                      alterado_por: str | None) -> dict | None:
    """Grava o novo preço vigente + a linha de histórico (mesma transação)."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE plans SET preco = %s,
                       stripe_price_id   = COALESCE(%s, stripe_price_id),
                       stripe_product_id = COALESCE(%s, stripe_product_id),
                       updated_by = %s, updated_at = now()
                 WHERE id = %s""",
                (preco, stripe_price_id, stripe_product_id, alterado_por, plan_id),
            )
            cur.execute(
                """INSERT INTO plan_price_history
                     (plan_id, preco_anterior, preco_novo, stripe_price_id_anterior,
                      stripe_price_id_novo, assinaturas_migradas, assinaturas_falhas, alterado_por)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (plan_id, preco_anterior, preco, stripe_price_id_anterior, stripe_price_id,
                 migradas, falhas, alterado_por),
            )
    return get_plan(plan_id)


def plan_price_history(plan_id: str | None = None, limit: int = 20) -> list[dict]:
    where, params = "", []
    if plan_id:
        where = "WHERE plan_id = %s"
        params.append(plan_id)
    return query(
        f"""SELECT id, plan_id, preco_anterior::float AS preco_anterior,
                   preco_novo::float AS preco_novo, stripe_price_id_novo,
                   assinaturas_migradas, assinaturas_falhas, alterado_por, created_at
              FROM plan_price_history {where}
             ORDER BY created_at DESC LIMIT %s""",
        (*params, limit),
    )


def assinaturas_do_plano(plan_id: str) -> list[dict]:
    """Assinaturas Stripe vivas de um plano (candidatas a migrar de preço)."""
    return query(
        """SELECT tenant_id, stripe_subscription_id, stripe_price_id, status
             FROM subscriptions
            WHERE plan = %s AND stripe_subscription_id IS NOT NULL
              AND status IN ('active','trialing','past_due','unpaid')""",
        (plan_id,),
    )


def contagem_assinantes_por_plano() -> dict[str, int]:
    rows = query(
        """SELECT plan, count(*) AS n FROM subscriptions
            WHERE plan IS NOT NULL AND stripe_subscription_id IS NOT NULL
              AND status IN ('active','trialing','past_due','unpaid')
            GROUP BY plan"""
    )
    return {r["plan"]: int(r["n"]) for r in rows}


def set_plan_mensagens(plan_id: str, mensagens: int, alterado_por: str | None) -> dict | None:
    execute(
        """UPDATE plans SET mensagens_incluidas = %s, updated_by = %s, updated_at = now()
            WHERE id = %s""",
        (int(mensagens), alterado_por, plan_id),
    )
    return get_plan(plan_id)


# --- Cota de mensagens + pacotes avulsos ----------------------------------

_PACK_COLS = "id, nome, mensagens, preco::float AS preco, ativo, ordem, updated_by, updated_at"


def list_message_packs(apenas_ativos: bool = True) -> list[dict]:
    where = "WHERE ativo" if apenas_ativos else ""
    return query(f"SELECT {_PACK_COLS} FROM message_packs {where} ORDER BY ordem, mensagens")


def get_message_pack(pack_id: str) -> dict | None:
    rows = query(f"SELECT {_PACK_COLS} FROM message_packs WHERE id = %s", (pack_id,))
    return rows[0] if rows else None


def update_message_pack(pack_id: str, *, nome: str | None, mensagens: int | None,
                        preco: float | None, ativo: bool | None,
                        alterado_por: str | None) -> dict | None:
    execute(
        """UPDATE message_packs SET
               nome = COALESCE(%s, nome), mensagens = COALESCE(%s, mensagens),
               preco = COALESCE(%s, preco), ativo = COALESCE(%s, ativo),
               updated_by = %s, updated_at = now()
            WHERE id = %s""",
        (nome, mensagens, preco, ativo, alterado_por, pack_id),
    )
    return get_message_pack(pack_id)


def create_pack_purchase(tenant_id: int, pack: dict, comprado_por: str | None) -> int:
    rows = execute(
        """INSERT INTO message_pack_purchases (tenant_id, pack_id, mensagens, preco, comprado_por)
           VALUES (%s, %s, %s, %s, %s) RETURNING id""",
        (tenant_id, pack["id"], int(pack["mensagens"]), pack["preco"], comprado_por),
        returning=True,
    )
    return int(rows[0]["id"])


def set_pack_purchase_session(purchase_id: int, session_id: str) -> None:
    execute("UPDATE message_pack_purchases SET stripe_session_id = %s WHERE id = %s",
            (session_id, purchase_id))


def confirmar_pack_purchase(purchase_id: int, tenant_id: int, valido_ate) -> dict | None:
    """Marca como pago (idempotente: só a 1ª confirmação grava a validade)."""
    rows = execute(
        """UPDATE message_pack_purchases SET status = 'pago', pago_em = now(), valido_ate = %s
            WHERE id = %s AND tenant_id = %s AND status IN ('pendente','falhou')
        RETURNING id, tenant_id, mensagens, valido_ate""",
        (valido_ate, purchase_id, tenant_id), returning=True,
    )
    return rows[0] if rows else None


def falhar_pack_purchase(purchase_id: int, tenant_id: int) -> None:
    execute(
        """UPDATE message_pack_purchases SET status = 'falhou'
            WHERE id = %s AND tenant_id = %s AND status = 'pendente'""",
        (purchase_id, tenant_id),
    )


def pacotes_validos(tenant_id: int) -> list[dict]:
    """Pacotes pagos ainda dentro da validade (somam à cota do ciclo)."""
    return query(
        """SELECT id, pack_id, mensagens, preco::float AS preco, pago_em, valido_ate
             FROM message_pack_purchases
            WHERE tenant_id = %s AND status = 'pago' AND valido_ate > now()
            ORDER BY pago_em""",
        (tenant_id,),
    )


def mensagens_ia_desde(tenant_id: int, inicio) -> int:
    """Respostas da IA (eventos de consumo 'chat') a partir de `inicio`."""
    return int(query(
        """SELECT count(*) AS n FROM usage_events
            WHERE tenant_id = %s AND tipo = 'chat' AND created_at >= %s""",
        (tenant_id, inicio),
    )[0]["n"])


def conversas_pausadas_pela_cota(tenant_id: int, desde) -> list[str]:
    """Conversas que foram para a fila humana SÓ porque a cota acabou (evento
    'cota_esgotada' no ciclo) e em que a equipe ainda não interveio (nenhuma
    mensagem ou nota humana depois disso). São as que podem voltar para a IA."""
    rows = query(
        """SELECT c.thread_id
             FROM conversations c
             JOIN LATERAL (
                   SELECT max(e.created_at) AS em FROM events e
                    WHERE e.tenant_id = c.tenant_id AND e.thread_id = c.thread_id
                      AND e.tipo = 'cota_esgotada' AND e.created_at >= %s) ev ON ev.em IS NOT NULL
            WHERE c.tenant_id = %s AND c.status = 'humano'
              AND NOT EXISTS (
                   SELECT 1 FROM messages m
                    WHERE m.tenant_id = c.tenant_id AND m.thread_id = c.thread_id
                      AND m.role IN ('humano', 'nota') AND m.created_at > ev.em)""",
        (desde, tenant_id),
    )
    return [r["thread_id"] for r in rows]


def registrar_alerta_cota(tenant_id: int, periodo_inicio, nivel: int, limite: int) -> bool:
    """True só na 1ª vez que o nível é atingido no ciclo com esse limite (o aviso
    dispara uma vez; comprar pacote muda o limite e rearma o aviso)."""
    rows = execute(
        """INSERT INTO message_quota_alerts (tenant_id, periodo_inicio, nivel, limite)
           VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING RETURNING nivel""",
        (tenant_id, periodo_inicio, nivel, limite), returning=True,
    )
    return bool(rows)


def emails_owners(tenant_id: int) -> list[str]:
    rows = query(
        "SELECT email FROM users WHERE tenant_id = %s AND role = 'owner' AND ativo ORDER BY id",
        (tenant_id,),
    )
    return [r["email"] for r in rows]


def _ticket_filtros(status, prioridade, q) -> tuple[str, list]:
    conds, params = [], []
    if status:
        conds.append("tk.status = %s"); params.append(status)
    if prioridade:
        conds.append("tk.prioridade = %s"); params.append(prioridade)
    if q:
        conds.append("(tk.assunto ILIKE %s OR t.nome ILIKE %s)")
        params += [f"%{q}%", f"%{q}%"]
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return where, params


def admin_list_tickets(status: str | None = None, prioridade: str | None = None,
                       q: str | None = None, limit: int = 25, offset: int = 0) -> list[dict]:
    where, params = _ticket_filtros(status, prioridade, q)
    return query(
        f"""SELECT tk.id, tk.assunto, tk.categoria, tk.prioridade, tk.status,
                   tk.created_at, tk.updated_at, t.id AS tenant_id, t.nome AS tenant_nome,
                   (SELECT count(*) FROM ticket_mensagens m WHERE m.ticket_id = tk.id) AS mensagens
              FROM tickets tk JOIN tenants t ON t.id = tk.tenant_id
              {where}
             ORDER BY (tk.status IN ('resolvido','fechado')),
                      CASE tk.prioridade WHEN 'alta' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                      tk.updated_at DESC
             LIMIT %s OFFSET %s""",
        (*params, limit, offset),
    )


def admin_count_tickets(status: str | None = None, prioridade: str | None = None,
                        q: str | None = None) -> int:
    where, params = _ticket_filtros(status, prioridade, q)
    return int(query(
        f"SELECT count(*) AS n FROM tickets tk JOIN tenants t ON t.id = tk.tenant_id {where}",
        tuple(params),
    )[0]["n"])


def admin_get_ticket(ticket_id: int) -> dict | None:
    rows = query(
        """SELECT tk.id, tk.tenant_id, tk.assunto, tk.categoria, tk.prioridade, tk.status,
                  tk.created_at, tk.updated_at, t.nome AS tenant_nome, u.email AS cliente_email
             FROM tickets tk JOIN tenants t ON t.id = tk.tenant_id
             LEFT JOIN users u ON u.id = tk.user_id
            WHERE tk.id = %s""",
        (ticket_id,),
    )
    if not rows:
        return None
    tk = rows[0]
    tk["mensagens"] = query(
        "SELECT autor, corpo, created_at FROM ticket_mensagens WHERE ticket_id = %s ORDER BY created_at",
        (ticket_id,),
    )
    return tk


def admin_add_ticket_message(ticket_id: int, autor: str, corpo: str) -> dict | None:
    tk = admin_get_ticket(ticket_id)
    if not tk:
        return None
    execute(
        """INSERT INTO ticket_mensagens (ticket_id, tenant_id, autor, corpo)
             VALUES (%s, %s, %s, %s)""",
        (ticket_id, tk["tenant_id"], autor, corpo),
    )
    novo = "em_andamento" if autor == "suporte" else "aberto"
    execute(
        """UPDATE tickets SET updated_at = now(),
               status = CASE WHEN status IN ('resolvido','fechado') THEN %s ELSE status END
             WHERE id = %s""",
        (novo, ticket_id),
    )
    return admin_get_ticket(ticket_id)


def admin_set_ticket(ticket_id: int, status: str | None = None,
                     prioridade: str | None = None) -> dict | None:
    execute(
        """UPDATE tickets SET status = COALESCE(%s, status),
               prioridade = COALESCE(%s, prioridade), updated_at = now()
             WHERE id = %s""",
        (status, prioridade, ticket_id),
    )
    return admin_get_ticket(ticket_id)


def admin_usage_por_tenant(q: str | None = None, limit: int = 25, offset: int = 0) -> list[dict]:
    where, params = "", []
    if q:
        where = "WHERE t.nome ILIKE %s"
        params.append(f"%{q}%")
    return query(
        f"""SELECT t.id, t.nome,
                  COALESCE(SUM(u.tokens),0) AS tokens,
                  COALESCE(SUM(u.custo_estimado),0) AS custo
             FROM tenants t
             LEFT JOIN usage_events u
               ON u.tenant_id = t.id AND u.created_at >= date_trunc('month', now())
            {where}
            GROUP BY t.id, t.nome
            ORDER BY custo DESC
            LIMIT %s OFFSET %s""",
        (*params, limit, offset),
    )


def admin_usage_totais(q: str | None = None) -> dict:
    """Totais do mês em TODOS os tenants que casam com a busca (p/ o card)."""
    where, params = "", []
    if q:
        where = "WHERE t.nome ILIKE %s"
        params.append(f"%{q}%")
    return query(
        f"""SELECT count(DISTINCT t.id) AS tenants,
                  COALESCE(SUM(u.tokens),0) AS tokens,
                  COALESCE(SUM(u.custo_estimado),0) AS custo
             FROM tenants t
             LEFT JOIN usage_events u
               ON u.tenant_id = t.id AND u.created_at >= date_trunc('month', now())
            {where}""",
        tuple(params),
    )[0]


# --- API pública: chaves de integração + auditoria --------------------------
# Chaves são POR TENANT. Só o SHA-256 é persistido; key_hash nunca sai daqui
# (_API_KEY_COLS não o inclui).

_API_KEY_COLS = """id, tenant_id, nome, prefixo, escopos, ips_permitidos, rate_limit_min,
                   expires_at, revoked_at, last_used_at, last_used_ip, created_by,
                   created_at, updated_at"""


def create_api_key(
    tenant_id: int, nome: str, prefixo: str, key_hash: str, escopos: list[str],
    ips_permitidos: list[str], rate_limit_min: int, expires_at, created_by: int | None,
) -> dict:
    rows = execute(
        f"""INSERT INTO api_keys (tenant_id, nome, prefixo, key_hash, escopos,
                                  ips_permitidos, rate_limit_min, expires_at, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_API_KEY_COLS}""",
        (tenant_id, nome, prefixo, key_hash, escopos, ips_permitidos, rate_limit_min,
         expires_at, created_by),
        returning=True,
    )
    return rows[0]


def list_api_keys(tenant_id: int) -> list[dict]:
    return query(
        f"""SELECT {_API_KEY_COLS},
                   (SELECT count(*) FROM api_request_log l
                     WHERE l.api_key_id = k.id AND l.created_at >= now() - interval '24 hours'
                   ) AS chamadas_24h
              FROM api_keys k WHERE tenant_id = %s
             ORDER BY revoked_at IS NOT NULL, created_at DESC""",
        (tenant_id,),
    )


def get_api_key(tenant_id: int, key_id: int) -> dict | None:
    rows = query(
        f"SELECT {_API_KEY_COLS} FROM api_keys WHERE tenant_id = %s AND id = %s",
        (tenant_id, key_id),
    )
    return rows[0] if rows else None


def get_api_key_by_hash(key_hash: str) -> dict | None:
    """Resolve a chave apresentada na requisição (inclui status do tenant)."""
    rows = query(
        f"""SELECT {', '.join('k.' + c.strip() for c in _API_KEY_COLS.split(','))},
                   t.status AS tenant_status
              FROM api_keys k JOIN tenants t ON t.id = k.tenant_id
             WHERE k.key_hash = %s""",
        (key_hash,),
    )
    return rows[0] if rows else None


def update_api_key(
    tenant_id: int, key_id: int, *, nome: str | None = None, escopos: list[str] | None = None,
    ips_permitidos: list[str] | None = None, rate_limit_min: int | None = None,
) -> dict | None:
    rows = execute(
        f"""UPDATE api_keys
               SET nome = COALESCE(%s, nome),
                   escopos = COALESCE(%s, escopos),
                   ips_permitidos = COALESCE(%s, ips_permitidos),
                   rate_limit_min = COALESCE(%s, rate_limit_min),
                   updated_at = now()
             WHERE tenant_id = %s AND id = %s AND revoked_at IS NULL
            RETURNING {_API_KEY_COLS}""",
        (nome, escopos, ips_permitidos, rate_limit_min, tenant_id, key_id),
        returning=True,
    )
    return rows[0] if rows else None


def revoke_api_key(tenant_id: int, key_id: int) -> dict | None:
    rows = execute(
        f"""UPDATE api_keys SET revoked_at = COALESCE(revoked_at, now()), updated_at = now()
             WHERE tenant_id = %s AND id = %s
            RETURNING {_API_KEY_COLS}""",
        (tenant_id, key_id),
        returning=True,
    )
    return rows[0] if rows else None


def touch_api_key(key_id: int, ip: str | None) -> None:
    execute(
        "UPDATE api_keys SET last_used_at = now(), last_used_ip = %s WHERE id = %s",
        (ip, key_id),
    )


def log_api_request(
    tenant_id: int, key_id: int | None, metodo: str, rota: str, status: int,
    duracao_ms: int, ip: str | None,
) -> None:
    execute(
        """INSERT INTO api_request_log (tenant_id, api_key_id, metodo, rota, status, duracao_ms, ip)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (tenant_id, key_id, metodo, rota[:300], status, duracao_ms, ip),
    )


def list_api_logs(tenant_id: int, key_id: int | None = None, limit: int = 50,
                  offset: int = 0) -> dict:
    conds = ["l.tenant_id = %s"]
    params: list = [tenant_id]
    if key_id:
        conds.append("l.api_key_id = %s")
        params.append(key_id)
    where = " AND ".join(conds)
    total = query(f"SELECT count(*) AS n FROM api_request_log l WHERE {where}", tuple(params))[0]["n"]
    items = query(
        f"""SELECT l.id, l.api_key_id, k.nome AS chave, k.prefixo, l.metodo, l.rota,
                   l.status, l.duracao_ms, l.ip, l.created_at
              FROM api_request_log l LEFT JOIN api_keys k ON k.id = l.api_key_id
             WHERE {where}
             ORDER BY l.created_at DESC LIMIT %s OFFSET %s""",
        tuple(params + [limit, offset]),
    )
    return {"items": items, "total": int(total)}


def api_uso_resumo(tenant_id: int) -> dict:
    """Chamadas das últimas 24h (total/erros) + chaves ativas do tenant."""
    r = query(
        """SELECT count(*) AS chamadas,
                  count(*) FILTER (WHERE status >= 400) AS erros
             FROM api_request_log
            WHERE tenant_id = %s AND created_at >= now() - interval '24 hours'""",
        (tenant_id,),
    )[0]
    ativas = query(
        """SELECT count(*) AS n FROM api_keys
            WHERE tenant_id = %s AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > now())""",
        (tenant_id,),
    )[0]["n"]
    return {"chamadas_24h": int(r["chamadas"]), "erros_24h": int(r["erros"]),
            "chaves_ativas": int(ativas)}


def purge_api_logs(dias: int = 90) -> int:
    rows = execute(
        "DELETE FROM api_request_log WHERE created_at < now() - make_interval(days => %s) RETURNING id",
        (dias,), returning=True,
    )
    return len(rows or [])


def admin_list_api_keys(q: str | None = None, limit: int = 25, offset: int = 0) -> dict:
    """CROSS-TENANT (só via current_admin): todas as chaves p/ auditoria/revogação."""
    conds, params = ["TRUE"], []
    if q:
        like = f"%{q}%"
        conds.append("(t.nome ILIKE %s OR k.nome ILIKE %s OR k.prefixo ILIKE %s)")
        params += [like, like, like]
    where = " AND ".join(conds)
    total = query(
        f"SELECT count(*) AS n FROM api_keys k JOIN tenants t ON t.id = k.tenant_id WHERE {where}",
        tuple(params),
    )[0]["n"]
    items = query(
        f"""SELECT k.id, k.tenant_id, t.nome AS tenant_nome, k.nome, k.prefixo, k.escopos,
                   k.ips_permitidos, k.expires_at, k.revoked_at, k.last_used_at,
                   k.last_used_ip, k.created_at,
                   (SELECT count(*) FROM api_request_log l
                     WHERE l.api_key_id = k.id AND l.created_at >= now() - interval '24 hours'
                   ) AS chamadas_24h
              FROM api_keys k JOIN tenants t ON t.id = k.tenant_id
             WHERE {where}
             ORDER BY k.revoked_at IS NOT NULL, k.last_used_at DESC NULLS LAST, k.created_at DESC
             LIMIT %s OFFSET %s""",
        tuple(params + [limit, offset]),
    )
    return {"items": items, "total": int(total)}


def admin_revoke_api_key(key_id: int) -> dict | None:
    rows = execute(
        f"""UPDATE api_keys SET revoked_at = COALESCE(revoked_at, now()), updated_at = now()
             WHERE id = %s RETURNING {_API_KEY_COLS}""",
        (key_id,), returning=True,
    )
    return rows[0] if rows else None


# --- Webhooks de saída ------------------------------------------------------
# `segredo` só sai por get_webhook_segredo (assinatura/revelação ao owner).

_WEBHOOK_COLS = """id, tenant_id, url, descricao, eventos, ativo, desativado_motivo,
                   falhas_consecutivas, ultimo_status, ultimo_envio_at, created_by,
                   created_at, updated_at"""


def create_webhook(tenant_id: int, url: str, descricao: str | None, eventos: list[str],
                   segredo: str, created_by: int | None) -> dict:
    rows = execute(
        f"""INSERT INTO webhooks (tenant_id, url, descricao, eventos, segredo, created_by)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING {_WEBHOOK_COLS}""",
        (tenant_id, url, descricao, eventos, segredo, created_by), returning=True,
    )
    return rows[0]


def list_webhooks(tenant_id: int) -> list[dict]:
    return query(
        f"""SELECT {_WEBHOOK_COLS},
                   (SELECT count(*) FROM webhook_entregas e
                     WHERE e.webhook_id = w.id AND e.created_at >= now() - interval '24 hours'
                   ) AS entregas_24h,
                   (SELECT count(*) FROM webhook_entregas e
                     WHERE e.webhook_id = w.id AND NOT e.sucesso
                       AND e.created_at >= now() - interval '24 hours'
                   ) AS falhas_24h
              FROM webhooks w WHERE tenant_id = %s ORDER BY created_at DESC""",
        (tenant_id,),
    )


def count_webhooks(tenant_id: int) -> int:
    return int(query("SELECT count(*) AS n FROM webhooks WHERE tenant_id = %s", (tenant_id,))[0]["n"])


def get_webhook(tenant_id: int, webhook_id: int) -> dict | None:
    rows = query(f"SELECT {_WEBHOOK_COLS} FROM webhooks WHERE tenant_id = %s AND id = %s",
                 (tenant_id, webhook_id))
    return rows[0] if rows else None


def get_webhook_segredo(tenant_id: int, webhook_id: int) -> str | None:
    rows = query("SELECT segredo FROM webhooks WHERE tenant_id = %s AND id = %s",
                 (tenant_id, webhook_id))
    return rows[0]["segredo"] if rows else None


def webhooks_do_evento(tenant_id: int, evento: str) -> list[dict]:
    """Webhooks ATIVOS do tenant assinando o evento (inclui o segredo p/ assinar)."""
    return query(
        """SELECT id, tenant_id, url, segredo FROM webhooks
            WHERE tenant_id = %s AND ativo AND %s = ANY(eventos)""",
        (tenant_id, evento),
    )


def update_webhook(tenant_id: int, webhook_id: int, *, url: str | None = None,
                   descricao: str | None = None, eventos: list[str] | None = None,
                   ativo: bool | None = None) -> dict | None:
    rows = execute(
        f"""UPDATE webhooks
               SET url = COALESCE(%s, url),
                   descricao = COALESCE(%s, descricao),
                   eventos = COALESCE(%s, eventos),
                   ativo = COALESCE(%s::boolean, ativo),
                   -- reativar manualmente zera o histórico de falhas
                   falhas_consecutivas = CASE WHEN %s::boolean IS TRUE THEN 0 ELSE falhas_consecutivas END,
                   desativado_motivo = CASE WHEN %s::boolean IS TRUE THEN NULL ELSE desativado_motivo END,
                   updated_at = now()
             WHERE tenant_id = %s AND id = %s
            RETURNING {_WEBHOOK_COLS}""",
        (url, descricao, eventos, ativo, ativo, ativo, tenant_id, webhook_id), returning=True,
    )
    return rows[0] if rows else None


def set_webhook_segredo(tenant_id: int, webhook_id: int, segredo: str) -> bool:
    rows = execute(
        "UPDATE webhooks SET segredo = %s, updated_at = now() WHERE tenant_id = %s AND id = %s RETURNING id",
        (segredo, tenant_id, webhook_id), returning=True,
    )
    return bool(rows)


def delete_webhook(tenant_id: int, webhook_id: int) -> bool:
    rows = execute("DELETE FROM webhooks WHERE tenant_id = %s AND id = %s RETURNING id",
                   (tenant_id, webhook_id), returning=True)
    return bool(rows)


def registrar_entrega_webhook(
    webhook_id: int, tenant_id: int, evento_id: str, evento: str, payload: dict,
    sucesso: bool, status_code: int | None, tentativas: int, erro: str | None,
    duracao_ms: int, max_falhas: int,
) -> None:
    """Grava a entrega e atualiza a saúde do webhook; desativa após `max_falhas`
    falhas seguidas (evita martelar um endpoint fora do ar indefinidamente)."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO webhook_entregas (webhook_id, tenant_id, evento_id, evento, payload,
                                                 sucesso, status_code, tentativas, erro, duracao_ms)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (webhook_id, tenant_id, evento_id, evento, json.dumps(payload, default=str),
                 sucesso, status_code, tentativas, (erro or None) and erro[:500], duracao_ms),
            )
            cur.execute(
                """UPDATE webhooks
                      SET ultimo_status = %s, ultimo_envio_at = now(),
                          falhas_consecutivas = CASE WHEN %s THEN 0 ELSE falhas_consecutivas + 1 END,
                          ativo = CASE WHEN NOT %s AND falhas_consecutivas + 1 >= %s THEN false ELSE ativo END,
                          desativado_motivo = CASE WHEN NOT %s AND falhas_consecutivas + 1 >= %s
                              THEN 'desativado automaticamente após ' || %s::text || ' falhas seguidas'
                              ELSE desativado_motivo END
                    WHERE id = %s AND tenant_id = %s""",
                (status_code, sucesso, sucesso, max_falhas, sucesso, max_falhas, max_falhas,
                 webhook_id, tenant_id),
            )


def list_entregas_webhook(tenant_id: int, webhook_id: int | None = None, limit: int = 25,
                          offset: int = 0) -> dict:
    conds, params = ["tenant_id = %s"], [tenant_id]
    if webhook_id:
        conds.append("webhook_id = %s")
        params.append(webhook_id)
    where = " AND ".join(conds)
    total = query(f"SELECT count(*) AS n FROM webhook_entregas WHERE {where}", tuple(params))[0]["n"]
    items = query(
        f"""SELECT id, webhook_id, evento_id, evento, payload, sucesso, status_code, tentativas,
                   erro, duracao_ms, created_at
              FROM webhook_entregas WHERE {where}
             ORDER BY created_at DESC LIMIT %s OFFSET %s""",
        tuple(params + [limit, offset]),
    )
    return {"items": items, "total": int(total)}


def get_entrega_webhook(tenant_id: int, entrega_id: int) -> dict | None:
    rows = query(
        """SELECT id, webhook_id, evento_id, evento, payload FROM webhook_entregas
            WHERE tenant_id = %s AND id = %s""",
        (tenant_id, entrega_id),
    )
    return rows[0] if rows else None


def purge_webhook_entregas(dias: int = 30) -> int:
    rows = execute(
        "DELETE FROM webhook_entregas WHERE created_at < now() - make_interval(days => %s) RETURNING id",
        (dias,), returning=True,
    )
    return len(rows or [])
