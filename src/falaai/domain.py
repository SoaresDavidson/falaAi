"""Tipos do domínio do Fala Aí. Os nomes seguem o glossário em CONTEXT.md."""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

Apresentador = Literal["dora", "alex"]


@dataclass(frozen=True)
class Newsletter:
    gmail_id: str
    remetente: str
    assunto: str
    recebida_em: datetime
    texto: str  # markdown, já truncado em Config.texto_max_chars


@dataclass(frozen=True)
class Item:
    titulo: str
    descricao: str
    link: str | None
    fonte: str
    newsletter_id: str


@dataclass(frozen=True)
class Topico:
    titulo: str
    itens: tuple[Item, ...]
    palavras_alvo: int


@dataclass(frozen=True)
class Pauta:
    topicos: tuple[Topico, ...]
    fora_do_audio: tuple[Item, ...]


@dataclass(frozen=True)
class Fala:
    apresentador: Apresentador
    texto: str


@dataclass(frozen=True)
class Roteiro:
    abertura: tuple[Fala, ...]
    blocos: tuple[tuple[Fala, ...], ...]  # um por Topico, mesma ordem da Pauta
    fechamento: tuple[Fala, ...]

    def falas(self) -> list[Fala]:
        return [*self.abertura, *(f for bloco in self.blocos for f in bloco), *self.fechamento]

    def palavras(self) -> int:
        return sum(len(f.texto.split()) for f in self.falas())


@dataclass(frozen=True)
class Episodio:
    job_id: int
    titulo: str
    data: date
    arquivo: str  # nome do arquivo, sem diretório
    duracao_s: float
    tamanho_bytes: int
    shownotes: tuple[Item, ...]
    publicado_em: datetime
    id: int | None = None


class JobStatus(StrEnum):
    RODANDO = "rodando"
    SUCESSO = "sucesso"
    ERRO = "erro"
    SEM_EPISODIO = "sem_episodio"


class Estagio(StrEnum):
    COLETA = "coleta"
    EXTRACAO = "extracao"
    PAUTA = "pauta"
    DIALOGO = "dialogo"
    AUDIO = "audio"
    PUBLICACAO = "publicacao"
    ARQUIVAMENTO = "arquivamento"


@dataclass
class Job:
    id: int
    status: JobStatus
    estagio: Estagio
    iniciado_em: datetime
    modelo: str
    terminado_em: datetime | None = None
    erro: str | None = None
