"""Pool de conexões Postgres (compartilhado pelas ferramentas do agente)."""
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row

from .settings import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.pg_dsn,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            # Revalida a conexão ao pegá-la do pool e recicla conexões ociosas:
            # a rede overlay do Swarm derruba conexões TCP paradas, causando
            # "server closed the connection unexpectedly".
            check=ConnectionPool.check_connection,
            max_idle=60.0,
            open=True,
        )
    return _pool


def query(sql: str, params: tuple = ()) -> list[dict]:
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def execute(sql: str, params: tuple = (), *, returning: bool = False):
    """Executa INSERT/UPDATE/DDL (commit no fim do bloco `with`).

    Com `returning=True`, devolve as linhas do RETURNING; senão, None.
    """
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            if returning:
                return cur.fetchall()
    return None


def execute_script(sql: str) -> None:
    """Executa um script SQL multi-statement (ex: schema idempotente)."""
    with get_pool().connection() as conn:
        conn.execute(sql)
