"""Dublês das fronteiras (ports.py). Testes nunca chamam Gmail, Ollama ou Kokoro reais."""

import io
import wave
from collections.abc import Sequence
from datetime import UTC, date, datetime

from falaai.domain import Fala, Item, Newsletter


class FakeFonte:
    def __init__(self, newsletters: list[Newsletter]):
        self.newsletters = list(newsletters)
        self.arquivados: list[str] = []
        self.dias: list[date | None] = []

    def pendentes(self, dia: date | None = None) -> list[Newsletter]:
        self.dias.append(dia)
        return list(self.newsletters)

    def arquivar(self, gmail_ids: Sequence[str]) -> None:
        self.arquivados.extend(gmail_ids)


class FakeLlm:
    def __init__(self, respostas: list[dict | Exception], modelo: str = "fake"):
        self.respostas = list(respostas)
        self.modelo = modelo
        self.chamadas: list[tuple[str, str, dict]] = []
        self.descarregado = 0

    def json(self, sistema: str, usuario: str, schema: dict) -> dict:
        self.chamadas.append((sistema, usuario, schema))
        if not self.respostas:
            raise AssertionError("FakeLlm sem respostas restantes")
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    def descarregar(self) -> None:
        self.descarregado += 1


def wav_silencio(segundos: float = 0.2, taxa: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(taxa)
        w.writeframes(b"\x00\x00" * int(segundos * taxa))
    return buffer.getvalue()


class FakeTts:
    def __init__(self):
        self.falas: list[Fala] = []

    def sintetizar(self, fala: Fala) -> bytes:
        self.falas.append(fala)
        return wav_silencio()


def newsletter(gmail_id: str = "n1", **kw) -> Newsletter:
    padrao = {
        "remetente": "Fonte <fonte@exemplo.com>",
        "assunto": f"Assunto {gmail_id}",
        "recebida_em": datetime(2026, 11, 8, 6, 0, tzinfo=UTC),
        "texto": f"Texto da newsletter {gmail_id}",
    }
    return Newsletter(gmail_id=gmail_id, **(padrao | kw))


def item(titulo: str = "t", newsletter_id: str = "n1", **kw) -> Item:
    padrao = {
        "descricao": f"Descrição de {titulo}",
        "link": f"https://exemplo.com/{titulo}",
        "fonte": "Fonte",
    }
    return Item(titulo=titulo, newsletter_id=newsletter_id, **(padrao | kw))
