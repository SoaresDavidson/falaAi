"""Executa o Job numa thread, com exclusão mútua e métricas Prometheus."""

import logging
import threading
import time
from collections.abc import Callable

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

    def iniciar(self) -> tuple[Job, bool]:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise JobEmAndamento()
            job = self.store.job_retomavel()
            retomado = job is not None
            if job is None:
                job = self.store.criar_job(self._modelo)
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
            try:
                self._executar(job)
                if self.store.job(job.id).status == JobStatus.RODANDO:
                    self.store.atualizar_job(
                        job.id,
                        status=JobStatus.ERRO,
                        erro="terminou sem estado final",
                        terminar=True,
                    )
            except Exception as e:
                log.exception("Job %s falhou", job.id)
                self.store.atualizar_job(
                    job.id,
                    status=JobStatus.ERRO,
                    erro=f"{type(e).__name__}: {e}",
                    terminar=True,
                )
            status = self.store.job(job.id).status
            self._jobs.labels(status=status.value).inc()
            if status == JobStatus.SUCESSO:
                self._sucesso.set(time.time())
        finally:
            self._em_andamento.set(0)

    def aguardar(self, timeout: float) -> None:
        t = self._thread
        if t is not None:
            t.join(timeout)
