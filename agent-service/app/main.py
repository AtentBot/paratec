"""API HTTP do serviço de agentes — chamada pelo N8N (fluxo do WhatsApp)."""
from fastapi import FastAPI
from pydantic import BaseModel

from .agents import responder
from .db import get_pool
from .settings import settings

app = FastAPI(title="Paratec Agent Service", version="0.1.0")


class ChatRequest(BaseModel):
    mensagem: str
    # id da conversa (ex: número do WhatsApp) — mantém o histórico por cliente
    thread_id: str = "default"


class ChatResponse(BaseModel):
    resposta: str


@app.get("/health")
def health():
    try:
        with get_pool().connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM products")
                n = cur.fetchone()["n"]
        return {"status": "ok", "produtos": n, "model": settings.llm_model}
    except Exception as e:  # pragma: no cover
        return {"status": "degraded", "erro": str(e)}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    resposta = responder(req.mensagem, req.thread_id)
    return ChatResponse(resposta=resposta)
