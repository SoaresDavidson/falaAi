"""Persistência SQLite de Jobs, Itens, Pauta, Falas e Episódios."""

import json
import sqlite3
import threading
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path

from falaai.domain import (
    Episodio,
    Estagio,
    Fala,
    Item,
    Job,
    JobStatus,
    Newsletter,
    Pauta,
    Topico,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL,
    estagio TEXT NOT NULL,
    iniciado_em TEXT NOT NULL,
    terminado_em TEXT,
    modelo TEXT NOT NULL,
    erro TEXT
);
CREATE TABLE IF NOT EXISTS job_newsletters (
    job_id INTEGER NOT NULL,
    gmail_id TEXT NOT NULL,
    remetente TEXT NOT NULL,
    assunto TEXT NOT NULL,
    recebida_em TEXT NOT NULL,
    texto TEXT NOT NULL,
    PRIMARY KEY (job_id, gmail_id)
);
CREATE TABLE IF NOT EXISTS itens (
    gmail_id TEXT PRIMARY KEY,
    itens TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS pautas (
    job_id INTEGER PRIMARY KEY,
    pauta TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS falas (
    job_id INTEGER NOT NULL,
    chave TEXT NOT NULL,
    falas TEXT NOT NULL,
    PRIMARY KEY (job_id, chave)
);
CREATE TABLE IF NOT EXISTS episodios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    titulo TEXT NOT NULL,
    data TEXT NOT NULL,
    arquivo TEXT NOT NULL,
    duracao_s REAL NOT NULL,
    tamanho_bytes INTEGER NOT NULL,
    shownotes TEXT NOT NULL,
    publicado_em TEXT NOT NULL
);
"""


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _item(d: dict) -> Item:
    return Item(**d)


def _falas(raw: str) -> tuple[Fala, ...]:
    return tuple(Fala(**d) for d in json.loads(raw))


class Store:
    def __init__(self, path: Path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.executescript(SCHEMA)

    def _run(self, sql: str, params: Sequence = ()) -> sqlite3.Cursor:
        with self._lock, self._db:
            return self._db.execute(sql, params)

    def _all(self, sql: str, params: Sequence = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    def _one(self, sql: str, params: Sequence = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._db.execute(sql, params).fetchone()

    # Jobs
    @staticmethod
    def _job(r: sqlite3.Row) -> Job:
        return Job(
            id=r["id"],
            status=JobStatus(r["status"]),
            estagio=Estagio(r["estagio"]),
            iniciado_em=datetime.fromisoformat(r["iniciado_em"]),
            modelo=r["modelo"],
            terminado_em=(datetime.fromisoformat(r["terminado_em"]) if r["terminado_em"] else None),
            erro=r["erro"],
        )

    def criar_job(self, modelo: str) -> Job:
        cur = self._run(
            "INSERT INTO jobs (status, estagio, iniciado_em, modelo) VALUES (?,?,?,?)",
            (JobStatus.RODANDO.value, Estagio.COLETA.value, _agora(), modelo),
        )
        return self.job(cur.lastrowid)

    def job(self, job_id: int) -> Job:
        r = self._one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if r is None:
            raise KeyError(job_id)
        return self._job(r)

    def ultimo_job(self) -> Job | None:
        r = self._one("SELECT * FROM jobs ORDER BY id DESC LIMIT 1")
        return self._job(r) if r else None

    def job_retomavel(self) -> Job | None:
        j = self.ultimo_job()
        return j if j and j.status == JobStatus.ERRO else None

    def atualizar_job(
        self,
        job_id: int,
        *,
        status: JobStatus | None = None,
        estagio: Estagio | None = None,
        erro: str | None = None,
        terminar: bool = False,
    ) -> None:
        campos: list[str] = []
        valores: list = []
        if status is not None:
            campos.append("status=?")
            valores.append(status.value)
        if estagio is not None:
            campos.append("estagio=?")
            valores.append(estagio.value)
        if status == JobStatus.RODANDO:
            campos.append("erro=NULL")
            campos.append("terminado_em=NULL")
        if erro is not None:
            campos.append("erro=?")
            valores.append(erro)
        if terminar:
            campos.append("terminado_em=?")
            valores.append(_agora())
        if not campos:
            return
        self._run(f"UPDATE jobs SET {', '.join(campos)} WHERE id=?", (*valores, job_id))

    def marcar_interrompidos(self) -> int:
        cur = self._run(
            "UPDATE jobs SET status=?, erro='interrompido', terminado_em=? WHERE status=?",
            (JobStatus.ERRO.value, _agora(), JobStatus.RODANDO.value),
        )
        return cur.rowcount

    # Newsletters
    def vincular_newsletters(self, job_id: int, newsletters: Sequence[Newsletter]) -> None:
        with self._lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO job_newsletters VALUES (?,?,?,?,?,?)",
                [
                    (job_id, n.gmail_id, n.remetente, n.assunto, n.recebida_em.isoformat(), n.texto)
                    for n in newsletters
                ],
            )

    def newsletters_do_job(self, job_id: int) -> list[Newsletter]:
        rows = self._all("SELECT * FROM job_newsletters WHERE job_id=? ORDER BY rowid", (job_id,))
        return [
            Newsletter(
                gmail_id=r["gmail_id"],
                remetente=r["remetente"],
                assunto=r["assunto"],
                recebida_em=datetime.fromisoformat(r["recebida_em"]),
                texto=r["texto"],
            )
            for r in rows
        ]

    def desvincular_newsletter(self, job_id: int, gmail_id: str) -> None:
        self._run("DELETE FROM job_newsletters WHERE job_id=? AND gmail_id=?", (job_id, gmail_id))

    # Itens
    def salvar_itens(self, gmail_id: str, itens: Sequence[Item]) -> None:
        self._run(
            "INSERT OR REPLACE INTO itens VALUES (?,?)",
            (gmail_id, json.dumps([asdict(i) for i in itens])),
        )

    def itens_extraidos(self, gmail_id: str) -> list[Item] | None:
        r = self._one("SELECT itens FROM itens WHERE gmail_id=?", (gmail_id,))
        return None if r is None else [_item(d) for d in json.loads(r["itens"])]

    # Pauta
    def salvar_pauta(self, job_id: int, pauta: Pauta) -> None:
        self._run("INSERT OR REPLACE INTO pautas VALUES (?,?)", (job_id, json.dumps(asdict(pauta))))

    def pauta(self, job_id: int) -> Pauta | None:
        r = self._one("SELECT pauta FROM pautas WHERE job_id=?", (job_id,))
        if r is None:
            return None
        d = json.loads(r["pauta"])
        return Pauta(
            topicos=tuple(
                Topico(
                    titulo=t["titulo"],
                    itens=tuple(_item(i) for i in t["itens"]),
                    palavras_alvo=t["palavras_alvo"],
                )
                for t in d["topicos"]
            ),
            fora_do_audio=tuple(_item(i) for i in d["fora_do_audio"]),
        )

    # Falas
    def salvar_falas(self, job_id: int, chave: str, falas: Sequence[Fala]) -> None:
        self._run(
            "INSERT OR REPLACE INTO falas VALUES (?,?,?)",
            (job_id, chave, json.dumps([asdict(f) for f in falas])),
        )

    def falas(self, job_id: int, chave: str) -> tuple[Fala, ...] | None:
        r = self._one("SELECT falas FROM falas WHERE job_id=? AND chave=?", (job_id, chave))
        return None if r is None else _falas(r["falas"])

    # Episódios
    @staticmethod
    def _episodio(r: sqlite3.Row) -> Episodio:
        return Episodio(
            id=r["id"],
            job_id=r["job_id"],
            titulo=r["titulo"],
            data=date.fromisoformat(r["data"]),
            arquivo=r["arquivo"],
            duracao_s=r["duracao_s"],
            tamanho_bytes=r["tamanho_bytes"],
            shownotes=tuple(_item(i) for i in json.loads(r["shownotes"])),
            publicado_em=datetime.fromisoformat(r["publicado_em"]),
        )

    def salvar_episodio(self, ep: Episodio) -> Episodio:
        cur = self._run(
            "INSERT INTO episodios (job_id, titulo, data, arquivo, duracao_s, tamanho_bytes,"
            " shownotes, publicado_em) VALUES (?,?,?,?,?,?,?,?)",
            (
                ep.job_id,
                ep.titulo,
                ep.data.isoformat(),
                ep.arquivo,
                ep.duracao_s,
                ep.tamanho_bytes,
                json.dumps([asdict(i) for i in ep.shownotes]),
                ep.publicado_em.isoformat(),
            ),
        )
        return Episodio(
            job_id=ep.job_id,
            titulo=ep.titulo,
            data=ep.data,
            arquivo=ep.arquivo,
            duracao_s=ep.duracao_s,
            tamanho_bytes=ep.tamanho_bytes,
            shownotes=ep.shownotes,
            publicado_em=ep.publicado_em,
            id=cur.lastrowid,
        )

    def episodio_do_job(self, job_id: int) -> Episodio | None:
        r = self._one("SELECT * FROM episodios WHERE job_id=? ORDER BY id DESC LIMIT 1", (job_id,))
        return self._episodio(r) if r else None

    def episodios(self) -> list[Episodio]:
        return [self._episodio(r) for r in self._all("SELECT * FROM episodios ORDER BY id DESC")]
