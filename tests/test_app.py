import threading

import pytest
from prometheus_client import CollectorRegistry
from starlette.testclient import TestClient

from falaai.app import criar_app
from falaai.config import Config
from falaai.domain import JobStatus
from falaai.runner import JobRunner
from falaai.store import Store


@pytest.fixture
def config(tmp_path):
    c = Config(data_dir=tmp_path)
    c.episodios_dir.mkdir()
    return c


@pytest.fixture
def store(config):
    return Store(config.db_path)


def _app(config, store, executar=lambda job: None):
    reg = CollectorRegistry()
    runner = JobRunner(store, executar, "m", registry=reg)
    return TestClient(criar_app(config, runner, reg)), runner


def test_post_jobs_202_e_409(config, store):
    evento = threading.Event()

    def executar(job):
        evento.wait(5)
        store.atualizar_job(job.id, status=JobStatus.SUCESSO, terminar=True)

    client, runner = _app(config, store, executar)
    r = client.post("/jobs")
    assert r.status_code == 202
    assert r.json()["retomado"] is False
    assert isinstance(r.json()["job_id"], int)
    r2 = client.post("/jobs")
    assert r2.status_code == 409
    assert r2.json() == {"erro": "job em andamento"}
    evento.set()
    runner.aguardar(5)
    ultimo = client.get("/jobs/ultimo")
    assert ultimo.status_code == 200
    assert ultimo.json()["status"] == "sucesso"


def test_ultimo_404(config, store):
    client, _ = _app(config, store)
    assert client.get("/jobs/ultimo").status_code == 404


def test_episodio_com_range(config, store):
    nome = "falaai-2026-11-08-1.mp3"
    (config.episodios_dir / nome).write_bytes(bytes(range(100)))
    client, _ = _app(config, store)
    r = client.get(f"/episodes/{nome}", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206
    assert len(r.content) == 10
    assert r.headers["content-type"] == "audio/mpeg"


def test_path_traversal_404(config, store):
    (config.data_dir / "feed.xml").write_text("x")
    client, _ = _app(config, store)
    assert client.get("/episodes/..%2Ffalaai.db").status_code == 404
    assert client.get("/episodes/feed.xml").status_code == 404
    assert client.get("/episodes/falaai-2026-11-08-9.mp3").status_code == 404


def test_feed_404_sem_arquivo(config, store):
    client, _ = _app(config, store)
    assert client.get("/feed.xml").status_code == 404


def test_feed_ok(config, store):
    config.feed_path.write_text("<rss/>")
    client, _ = _app(config, store)
    r = client.get("/feed.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/rss+xml")


def test_metrics_expoe_series(config, store):
    client, _ = _app(config, store)
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "falaai_job_em_andamento" in r.text


def test_startup_marca_interrompidos(config, store):
    job = store.criar_job("m")
    _app(config, store)
    j = store.job(job.id)
    assert j.status == JobStatus.ERRO
    assert j.erro == "interrompido"


def test_startup_conta_interrompido_como_erro(config, store):
    store.criar_job("m")
    reg = CollectorRegistry()
    runner = JobRunner(store, lambda job: None, "m", registry=reg)
    criar_app(config, runner, reg)
    assert reg.get_sample_value("falaai_jobs_total", {"status": "erro"}) == 1


def test_post_jobs_novo(config, store):
    antigo = store.criar_job("m")
    store.atualizar_job(antigo.id, status=JobStatus.ERRO, erro="boom", terminar=True)

    def executar(job):
        store.atualizar_job(job.id, status=JobStatus.SUCESSO, terminar=True)

    client, runner = _app(config, store, executar)
    r = client.post("/jobs?novo=1")
    runner.aguardar(5)
    assert r.status_code == 202
    assert r.json()["retomado"] is False
    assert r.json()["job_id"] != antigo.id
