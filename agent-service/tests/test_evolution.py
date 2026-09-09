"""Cliente Evolution (envio de WhatsApp). Sem rede: valida configuração e a
construção da requisição (httpx monkeypatchado)."""
import pytest

from app import evolution
from app.settings import settings


def test_erro_quando_nao_configurado(monkeypatch):
    monkeypatch.setattr(settings, "evolution_api_url", "", raising=False)
    monkeypatch.setattr(settings, "evolution_api_key", "", raising=False)
    with pytest.raises(evolution.EvolutionError):
        evolution.enviar_texto("5511", "oi")


def test_envia_monta_requisicao(monkeypatch):
    monkeypatch.setattr(settings, "evolution_api_url", "http://evo:8080", raising=False)
    monkeypatch.setattr(settings, "evolution_api_key", "k", raising=False)
    monkeypatch.setattr(settings, "evolution_instance", "paratec", raising=False)

    capturado = {}

    class FakeResp:
        status_code = 200
        content = b"{}"

        def json(self):
            return {"ok": True}

    def fake_post(url, headers=None, json=None, timeout=None):
        capturado.update(url=url, headers=headers, json=json)
        return FakeResp()

    monkeypatch.setattr(evolution.httpx, "post", fake_post)
    out = evolution.enviar_texto("5511", "Olá")
    assert out == {"ok": True}
    assert capturado["url"] == "http://evo:8080/message/sendText/paratec"
    assert capturado["headers"]["apikey"] == "k"
    assert capturado["json"] == {"number": "5511", "text": "Olá"}


def test_envia_midia_monta_requisicao(monkeypatch):
    monkeypatch.setattr(settings, "evolution_api_url", "http://evo:8080", raising=False)
    monkeypatch.setattr(settings, "evolution_api_key", "k", raising=False)
    monkeypatch.setattr(settings, "evolution_instance", "paratec", raising=False)

    capturado = {}

    class FakeResp:
        status_code = 200
        content = b"{}"

        def json(self):
            return {"ok": True}

    def fake_post(url, headers=None, json=None, timeout=None):
        capturado.update(url=url, json=json)
        return FakeResp()

    monkeypatch.setattr(evolution.httpx, "post", fake_post)
    out = evolution.enviar_midia(
        "5511", "QkFTRTY0", mimetype="image/png", filename="b.png", caption="Promo"
    )
    assert out == {"ok": True}
    assert capturado["url"] == "http://evo:8080/message/sendMedia/paratec"
    assert capturado["json"] == {
        "number": "5511",
        "mediatype": "image",
        "mimetype": "image/png",
        "media": "QkFTRTY0",
        "fileName": "b.png",
        "caption": "Promo",
    }


def test_envia_midia_sem_caption_omite_campo(monkeypatch):
    monkeypatch.setattr(settings, "evolution_api_url", "http://evo:8080", raising=False)
    monkeypatch.setattr(settings, "evolution_api_key", "k", raising=False)

    capturado = {}

    class FakeResp:
        status_code = 200
        content = b""

        def json(self):  # pragma: no cover - content vazio não chama
            return {}

    monkeypatch.setattr(
        evolution.httpx, "post",
        lambda url, headers=None, json=None, timeout=None: capturado.update(json=json) or FakeResp(),
    )
    evolution.enviar_midia("5511", "QQ==", mimetype="image/jpeg", filename="x.jpg")
    assert "caption" not in capturado["json"]
