"""Executa o Job numa thread, com exclusão mútua e métricas Prometheus."""

import logging
import threading
import time
from collections.abc import Callable
from datetime import date

from prometheus_client import CollectorRegistry, Counter, Gauge

from falaai.domain import Job, JobStatus
from falaai.store import Store

log = logging.getLogger(__name__)


class JobEmAndamento(Exception):
    pass


class JobRunner:
    def __init__(
        self,
        store: Store,
        executar: Callable[[Job], None],
        modelo: str,
        registry: CollectorRegistry | None = None,
    ):
        self.store = store
        self.registry = registry if registry is not None else CollectorRegistry()
        self._executar = executar
        self._modelo = modelo
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._jobs = Counter("falaai_jobs", "Jobs terminados", ["status"], registry=self.registry)
        self._em_andamento = Gauge(
            "falaai_job_em_andamento", "1 enquanto um Job roda", registry=self.registry
        )
        self._iniciado = Gauge(
            "falaai_job_iniciado_timestamp_seconds",
            "Início do último Job",
            registry=self.registry,
        )
        self._sucesso = Gauge(
            "falaai_ultimo_sucesso_timestamp_seconds",
            "Fim do último Job com sucesso",
            registry=self.registry,
        )
        self._em_andamento.set(0)
        # Séries nascem em 0: increase() precisa ver o primeiro erro depois do start.
        for s in JobStatus:
            self._jobs.labels(status=s.value)

    def registrar_interrompidos(self, n: int) -> None:
        if n:
            self._jobs.labels(status=JobStatus.ERRO.value).inc(n)

    def iniciar(self, novo: bool = False, dia: date | None = None) -> tuple[Job, bool]:
        """Com `dia`, sempre cria um Job novo, restrito às Newsletters daquele dia."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise JobEmAndamento()
            job = None if novo or dia else self.store.job_retomavel()
            retomado = job is not None
            if job is None:
                job = self.store.criar_job(self._modelo, dia)
            else:
                self.store.atualizar_job(job.id, status=JobStatus.RODANDO)
                job = self.store.job(job.id)
            self._em_andamento.set(1)
            self._iniciado.set(time.time())
            self._thread = threading.Thread(
                target=self._rodar, args=(job,), name=f"job-{job.id}", daemon=True
            )
            self._thread.start()
            return job, retomado

    def _rodar(self, job: Job) -> None:
        try:
            self._executar_e_finalizar(job)
            status = self._status_final(job)
            self._jobs.labels(status=status.value).inc()
            if status == JobStatus.SUCESSO:
                self._sucesso.set(time.time())
        finally:
            self._em_andamento.set(0)

    def _executar_e_finalizar(self, job: Job) -> None:
        try:
            self._executar(job)
            erro = None
            if self.store.job(job.id).status == JobStatus.RODANDO:
                erro = "terminou sem estado final"
        except Exception as e:
            log.exception("Job %s falhou", job.id)
            erro = f"{type(e).__name__}: {e}"
        if erro is None:
            return
        try:
            self.store.atualizar_job(job.id, status=JobStatus.ERRO, erro=erro, terminar=True)
        except Exception:
            log.exception("Job %s: falha ao gravar estado de erro", job.id)

    def _status_final(self, job: Job) -> JobStatus:
        try:
            status = self.store.job(job.id).status
        except Exception:
            log.exception("Job %s: falha ao ler estado final", job.id)
            return JobStatus.ERRO
        return JobStatus.ERRO if status == JobStatus.RODANDO else status

    def aguardar(self, timeout: float) -> None:
        t = self._thread
        if t is not None:
            t.join(timeout)
