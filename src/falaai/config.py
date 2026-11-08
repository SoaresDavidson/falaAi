import dataclasses
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data_dir: Path = Path("/data")
    ollama_url: str = "http://100.74.37.102:11434"
    ollama_modelo: str = "qwen3:30b-a3b-instruct-2507-q4_K_M"
    tts_url: str = "http://100.74.37.102:8880"
    gmail_rotulo: str = "newsletter"
    # Aplicado às Newsletters de um Episódio publicado; quem tem esse rótulo não é mais pendente.
    gmail_rotulo_processada: str = "falaai-processada"
    gmail_token: Path = Path("/data/gmail-token.json")
    max_minutos: int = 15
    palavras_por_minuto: int = 150
    pausa_ms: int = 300
    texto_max_chars: int = 30000
    feed_base_url: str = "http://falaai"
    # Sem `?dia=`, o Job só coleta Newsletters dos últimos N dias (0 = todas as pendentes).
    gmail_janela_dias: int = 2
    fuso: str = "America/Sao_Paulo"

    @classmethod
    def do_ambiente(cls) -> "Config":
        valores = {}
        for campo in dataclasses.fields(cls):
            bruto = os.environ.get(f"FALAAI_{campo.name.upper()}")
            if bruto is not None:
                valores[campo.name] = type(campo.default)(bruto)
        return cls(**valores)

    @property
    def palavras_max(self) -> int:
        return self.max_minutos * self.palavras_por_minuto

    @property
    def db_path(self) -> Path:
        return self.data_dir / "falaai.db"

    @property
    def episodios_dir(self) -> Path:
        return self.data_dir / "episodes"

    @property
    def feed_path(self) -> Path:
        return self.data_dir / "feed.xml"
