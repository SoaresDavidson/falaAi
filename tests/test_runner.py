import threading

import pytest
from prometheus_client import CollectorRegistry

from falaai.domain import JobStatus
from falaai.runner import JobEmAndamento, JobRunner
from falaai.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.db")


def test_erro_marca_job(store):
    def executar(job):
        raise RuntimeError("x")

    reg = CollectorRegistry()
    runner = JobRunner(store, executar, "m", registry=reg)
    job, retomado = runner.iniciar()
    runner.aguardar(5)
    assert not retomado
    j = store.job(job.id)
    assert j.status == JobStatus.ERRO
    assert j.erro == "RuntimeError: x"
    assert reg.get_sample_value("falaai_jobs_total", {"status": "erro"}) == 1
    assert reg.get_sample_value("falaai_job_em_andamento") == 0


def test_segundo_iniciar_levanta(store):
    evento = threading.Event()

    def executar(job):
        evento.wait(5)
        store.atualizar_job(job.id, status=JobStatus.SUCESSO, terminar=True)

    reg = CollectorRegistry()
    runner = JobRunner(store, executar, "m", registry=reg)
    runner.iniciar()
    assert reg.get_sample_value("falaai_job_em_andamento") == 1
    with pytest.raises(JobEmAndamento):
        runner.iniciar()
    evento.set()
    runner.aguardar(5)
    assert reg.get_sample_value("falaai_jobs_total", {"status": "sucesso"}) == 1
    assert reg.get_sample_value("falaai_ultimo_sucesso_timestamp_seconds") > 0


def test_retoma_job_com_erro(store):
    antigo = store.criar_job("m")
    store.atualizar_job(antigo.id, status=JobStatus.ERRO, erro="boom", terminar=True)
    runner = JobRunner(store, lambda job: None, "m", registry=CollectorRegistry())
    job, retomado = runner.iniciar()
    runner.aguardar(5)
    assert retomado is True
    assert job.id == antigo.id
    j = store.job(antigo.id)
    assert j.status == JobStatus.ERRO
    assert j.erro == "terminou sem estado final"
