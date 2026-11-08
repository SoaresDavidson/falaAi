import io
import wave

import pytest

np = pytest.importorskip("numpy")
from starlette.testclient import TestClient

from falaai.tts_service.app import criar_app


class Ctx:
    def __init__(self):
        self.chamadas = 0
        self.agora = 0.0

    def fabrica(self):
        self.chamadas += 1
        return lambda texto, voz: np.zeros(2400, dtype=np.float32)

    def relogio(self):
        return self.agora


@pytest.fixture
def ctx():
    return Ctx()


@pytest.fixture
def app(ctx):
    return criar_app(fabrica_pipeline=ctx.fabrica, relogio=ctx.relogio)


def falar(client, voz="pf_dora", texto="oi"):
    return client.post("/v1/audio/speech", json={"input": texto, "voice": voz})


def test_carrega_sob_demanda(app, ctx):
    client = TestClient(app)
    assert client.get("/health").json() == {"carregado": False}
    assert falar(client).status_code == 200
    assert client.get("/health").json() == {"carregado": True}
    falar(client)
    assert ctx.chamadas == 1


def test_wav_valido(app):
    r = falar(TestClient(app))
    assert r.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(r.content)) as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2


def test_voz_invalida_422(app):
    assert falar(TestClient(app), voz="xx").status_code == 422


def test_input_vazio_422(app):
    assert falar(TestClient(app), texto="").status_code == 422


def test_descarrega_quando_ocioso(app, ctx):
    client = TestClient(app)
    falar(client)
    ctx.agora = 121
    app.state.servico._talvez_descarregar()
    assert client.get("/health").json() == {"carregado": False}
    falar(client)
    assert ctx.chamadas == 2


def test_vigia_sobrevive_a_excecao(app):
    servico = app.state.servico

    def quebra():
        raise RuntimeError("boom")

    servico._talvez_descarregar = quebra
    servico._ciclo_vigia()  # nao propaga


def test_fabrica_que_falha_pode_ser_repetida(ctx):
    estado = {"n": 0}

    def fabrica():
        estado["n"] += 1
        if estado["n"] == 1:
            raise RuntimeError("falha")
        return ctx.fabrica()

    client = TestClient(
        criar_app(fabrica_pipeline=fabrica, relogio=ctx.relogio),
        raise_server_exceptions=False,
    )
    assert falar(client).status_code == 500
    assert falar(client).status_code == 200
    assert estado["n"] == 2
