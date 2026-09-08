"""Broker in-process para notificações em tempo real (SSE).

O agent-service roda em 1 worker/replica (uvicorn sem --workers), então um
pub/sub em memória basta: os endpoints que GRAVAM mensagem (via store.add_message,
em threads do threadpool) publicam um sinal; o endpoint SSE (async, no event loop)
assina por thread_id e repassa ao navegador. A publicação usa call_soon_threadsafe
porque vem de outra thread (código síncrono) para o loop do FastAPI.

Se o SSE não chegar ao navegador (proxy bufferizando), a tela ainda tem o polling
como rede de segurança — este broker é um acelerador, não a única via.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

log = logging.getLogger("paratec.realtime")


class Broker:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Chamado no startup (dentro do event loop) para permitir publicação
        thread-safe a partir de código síncrono."""
        self._loop = loop

    async def subscribe(self, thread_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subs[thread_id].add(q)
        return q

    def unsubscribe(self, thread_id: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(thread_id)
        if subs is not None:
            subs.discard(q)
            if not subs:
                self._subs.pop(thread_id, None)

    def publish(self, thread_id: str, data: dict) -> None:
        """Publica um evento para os assinantes da thread. Seguro de chamar de
        qualquer thread (agenda no event loop). Best-effort: nunca levanta."""
        loop = self._loop
        if loop is None:
            return
        subs = list(self._subs.get(thread_id, ()))
        for q in subs:
            try:
                loop.call_soon_threadsafe(q.put_nowait, data)
            except Exception as e:  # pragma: no cover
                log.debug("publish falhou: %s", e)


broker = Broker()
