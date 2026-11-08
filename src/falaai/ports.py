"""Fronteiras com o mundo externo: Gmail, LLM e TTS."""

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from falaai.domain import Fala, Newsletter


class FonteNewsletters(Protocol):
    def pendentes(self, dia: date | None = None) -> list[Newsletter]: ...
    def arquivar(self, gmail_ids: Sequence[str]) -> None: ...


class Llm(Protocol):
    modelo: str

    def json(self, sistema: str, usuario: str, schema: dict) -> dict: ...
    def descarregar(self) -> None: ...


class Tts(Protocol):
    def sintetizar(self, fala: Fala) -> bytes: ...  # WAV PCM16 mono 24000 Hz
