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
    vistos = []

    def executar(job):
        vistos.append(store.job(job.id))
        store.atualizar_job(job.id, status=JobStatus.SUCESSO, terminar=True)

    runner = JobRunner(store, executar, "m", registry=CollectorRegistry())
    job, retomado = runner.iniciar()
    runner.aguardar(5)
    assert retomado is True
    assert job.id == antigo.id
    meio = vistos[0]
    assert meio.status == JobStatus.RODANDO
    assert meio.erro is None
    assert meio.terminado_em is None
    assert store.job(antigo.id).status == JobStatus.SUCESSO


def test_sem_estado_final_vira_erro(store):
    runner = JobRunner(store, lambda job: None, "m", registry=CollectorRegistry())
    job, _ = runner.iniciar()
    runner.aguardar(5)
    j = store.job(job.id)
    assert j.status == JobStatus.ERRO
    assert j.erro == "terminou sem estado final"


def test_falha_no_tratamento_ainda_conta_erro(store, monkeypatch):
    def executar(job):
        raise RuntimeError("x")

    def quebrado(*a, **kw):
        raise OSError("db")

    reg = CollectorRegistry()
    runner = JobRunner(store, executar, "m", registry=reg)
    monkeypatch.setattr(store, "atualizar_job", quebrado)
    runner.iniciar()
    runner.aguardar(5)
    assert reg.get_sample_value("falaai_jobs_total", {"status": "erro"}) == 1
    assert reg.get_sample_value("falaai_job_em_andamento") == 0


def test_series_existem_antes_do_primeiro_job(store):
    reg = CollectorRegistry()
    JobRunner(store, lambda job: None, "m", registry=reg)
    for s in JobStatus:
        assert reg.get_sample_value("falaai_jobs_total", {"status": s.value}) == 0


def test_novo_cria_job_mesmo_com_retomavel(store):
    antigo = store.criar_job("m")
    store.atualizar_job(antigo.id, status=JobStatus.ERRO, erro="boom", terminar=True)

    def executar(job):
        store.atualizar_job(job.id, status=JobStatus.SUCESSO, terminar=True)

    runner = JobRunner(store, executar, "m", registry=CollectorRegistry())
    job, retomado = runner.iniciar(novo=True)
    runner.aguardar(5)
    assert retomado is False
    assert job.id != antigo.id
    assert store.job(antigo.id).status == JobStatus.ERRO
    assert store.job(antigo.id).erro == "boom"


def test_novo_respeita_409(store):
    evento = threading.Event()

    def executar(job):
        evento.wait(5)
        store.atualizar_job(job.id, status=JobStatus.SUCESSO, terminar=True)

    runner = JobRunner(store, executar, "m", registry=CollectorRegistry())
    runner.iniciar()
    with pytest.raises(JobEmAndamento):
        runner.iniciar(novo=True)
    evento.set()
    runner.aguardar(5)


def test_registrar_interrompidos_conta_erro(store):
    reg = CollectorRegistry()
    runner = JobRunner(store, lambda job: None, "m", registry=reg)
    runner.registrar_interrompidos(2)
    assert reg.get_sample_value("falaai_jobs_total", {"status": "erro"}) == 2


def test_dia_ignora_retomada(store):
    from datetime import date

    antigo = store.criar_job("m")
    store.atualizar_job(antigo.id, status=JobStatus.ERRO, erro="x", terminar=True)
    runner = JobRunner(store, lambda job: None, "m", registry=CollectorRegistry())
    job, retomado = runner.iniciar(dia=date(2026, 11, 6))
    runner.aguardar(5)
    assert not retomado
    assert job.id != antigo.id
    assert job.dia == date(2026, 11, 6)
