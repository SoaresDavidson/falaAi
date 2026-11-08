from datetime import UTC, date, datetime

import httpx
import pytest

from falaai.config import Config
from falaai.domain import JobStatus
from falaai.job import Dependencias, executar_job
from falaai.store import Store
from tests.fakes import FakeFonte, FakeLlm, FakeTts, newsletter

HOJE = date(2026, 11, 8)


def extracao(gmail_id: str) -> dict:
    return {"itens": [{"titulo": f"item de {gmail_id}", "descricao": "d", "link": None}]}


def pauta(n_topicos: int, palavras: int = 100) -> dict:
    return {
        "topicos": [
            {"titulo": f"T{k}", "indices": [k], "palavras_alvo": palavras} for k in range(n_topicos)
        ]
    }


def falas(texto: str = "oi tudo bem") -> dict:
    return {"falas": [{"apresentador": "dora", "texto": texto}]}


def respostas_felizes(ids: list[str], n_topicos: int) -> list[dict]:
    return [
        *(extracao(i) for i in ids),
        pauta(n_topicos),
        falas("abertura"),
        *(falas(f"bloco {k}") for k in range(n_topicos)),
        falas("fechamento"),
    ]


@pytest.fixture
def ambiente(tmp_path):
    config = Config(data_dir=tmp_path, feed_base_url="http://falaai:8000")
    config.episodios_dir.mkdir()
    store = Store(config.db_path)
    fonte = FakeFonte([newsletter("n1"), newsletter("n2")])

    def deps(llm, tts=None):
        return Dependencias(
            store=store,
            fonte=fonte,
            llm=llm,
            tts=tts or FakeTts(),
            config=config,
            hoje=lambda: HOJE,
            agora=lambda: datetime(2026, 11, 8, 7, 0, tzinfo=UTC),
        )

    return config, store, fonte, deps


def falhar_como_runner(store, job, exc_tipo, executar):
    with pytest.raises(exc_tipo):
        executar()
    store.atualizar_job(job.id, status=JobStatus.ERRO, erro="x", terminar=True)


def test_caminho_feliz(ambiente):
    config, store, fonte, deps = ambiente
    llm = FakeLlm(respostas_felizes(["n1", "n2"], 2))
    job = store.criar_job(llm.modelo)
    executar_job(job, deps(llm))

    assert store.job(job.id).status == JobStatus.SUCESSO
    ep = store.episodio_do_job(job.id)
    assert (config.episodios_dir / ep.arquivo).exists()
    assert ep.arquivo == f"falaai-2026-11-08-{job.id}.mp3"
    assert ep.arquivo in config.feed_path.read_text()
    assert {i.newsletter_id for i in ep.shownotes} == {"n1", "n2"}
    assert fonte.arquivados == ["n1", "n2"]
    assert llm.descarregado == 1


def test_descarrega_llm_antes_do_tts(ambiente):
    _, store, _, deps = ambiente
    llm = FakeLlm(respostas_felizes(["n1", "n2"], 2))

    class TtsQueConfere(FakeTts):
        def sintetizar(self, fala):
            assert llm.descarregado == 1
            return super().sintetizar(fala)

    job = store.criar_job(llm.modelo)
    executar_job(job, deps(llm, TtsQueConfere()))
    assert store.job(job.id).status == JobStatus.SUCESSO


def test_sem_newsletters(ambiente):
    config, store, fonte, deps = ambiente
    fonte.newsletters = []
    job = store.criar_job("fake")
    executar_job(job, deps(FakeLlm([])))

    assert store.job(job.id).status == JobStatus.SEM_EPISODIO
    assert store.job(job.id).terminado_em is not None
    assert list(config.episodios_dir.iterdir()) == []
    assert fonte.arquivados == []


def test_extracao_falha_pula_newsletter(ambiente):
    _, store, fonte, deps = ambiente
    llm = FakeLlm(
        [
            ValueError("json inválido"),
            extracao("n2"),
            pauta(1),
            falas("abertura"),
            falas("bloco"),
            falas("fechamento"),
        ]
    )
    job = store.criar_job(llm.modelo)
    executar_job(job, deps(llm))

    assert store.job(job.id).status == JobStatus.SUCESSO
    assert fonte.arquivados == ["n2"]
    assert [n.gmail_id for n in store.newsletters_do_job(job.id)] == ["n2"]
    assert "n1" not in {i.newsletter_id for i in store.episodio_do_job(job.id).shownotes}


def test_retoma_sem_refazer(ambiente):
    _, store, fonte, deps = ambiente
    primeiro = FakeLlm(
        [
            extracao("n1"),
            extracao("n2"),
            pauta(2),
            falas("abertura"),
            falas("bloco 0"),
            httpx.ConnectError("laptop dormiu"),
        ]
    )
    job = store.criar_job(primeiro.modelo)
    falhar_como_runner(store, job, httpx.ConnectError, lambda: executar_job(job, deps(primeiro)))

    segundo = FakeLlm([falas("bloco 1"), falas("fechamento")])
    retomado = store.job_retomavel()
    assert retomado.id == job.id
    store.atualizar_job(job.id, status=JobStatus.RODANDO)
    executar_job(retomado, deps(segundo))

    assert store.job(job.id).status == JobStatus.SUCESSO
    assert len(segundo.chamadas) == 2
    assert fonte.arquivados == ["n1", "n2"]


def test_newsletter_nova_nao_entra(ambiente):
    _, store, fonte, deps = ambiente
    primeiro = FakeLlm([extracao("n1"), extracao("n2"), httpx.ConnectError("caiu")])
    job = store.criar_job(primeiro.modelo)
    falhar_como_runner(store, job, httpx.ConnectError, lambda: executar_job(job, deps(primeiro)))

    fonte.newsletters.append(newsletter("n3"))
    segundo = FakeLlm([pauta(2), falas("abertura"), falas("b0"), falas("b1"), falas("fim")])
    store.atualizar_job(job.id, status=JobStatus.RODANDO)
    executar_job(store.job(job.id), deps(segundo))

    assert fonte.arquivados == ["n1", "n2"]
    ep = store.episodio_do_job(job.id)
    assert "n3" not in {i.newsletter_id for i in ep.shownotes}


def test_retoma_apos_publicacao(ambiente):
    _, store, fonte, deps = ambiente

    class FonteQueFalhaUmaVez(FakeFonte):
        falhou = False

        def arquivar(self, gmail_ids):
            if not self.falhou:
                self.falhou = True
                raise RuntimeError("Gmail fora")
            super().arquivar(gmail_ids)

    fonte_ruim = FonteQueFalhaUmaVez(fonte.newsletters)
    llm = FakeLlm(respostas_felizes(["n1", "n2"], 2))
    job = store.criar_job(llm.modelo)
    d = deps(llm)
    d.fonte = fonte_ruim
    falhar_como_runner(store, job, RuntimeError, lambda: executar_job(job, d))
    assert store.episodio_do_job(job.id) is not None

    tts = FakeTts()
    d2 = deps(FakeLlm([]), tts)
    d2.fonte = fonte_ruim
    store.atualizar_job(job.id, status=JobStatus.RODANDO)
    executar_job(store.job(job.id), d2)

    assert store.job(job.id).status == JobStatus.SUCESSO
    assert fonte_ruim.arquivados == ["n1", "n2"]
    assert tts.falas == []
    assert len(store.episodios()) == 1


def test_teto_corta_topico_e_vai_para_shownotes(ambiente):
    config, store, _, deps = ambiente
    longo = " ".join(["palavra"] * 80)
    llm = FakeLlm(
        [
            extracao("n1"),
            extracao("n2"),
            pauta(2, palavras=50),
            falas("abertura"),
            falas(longo),
            falas(longo),
            falas("fim"),
        ]
    )
    d = deps(llm)
    d.config = Config(
        data_dir=config.data_dir, max_minutos=1, palavras_por_minuto=150
    )  # teto de 150 palavras: 2 blocos de 80 não cabem, sobra 1
    job = store.criar_job(llm.modelo)
    executar_job(job, d)

    ep = store.episodio_do_job(job.id)
    assert len(store.pauta(job.id).topicos) == 1
    assert {i.newsletter_id for i in ep.shownotes} == {"n1", "n2"}


def test_laptop_fora_na_extracao_falha_o_job_e_retoma(ambiente):
    _, store, fonte, deps = ambiente
    primeiro = FakeLlm([httpx.ConnectError("laptop desligado")])
    job = store.criar_job(primeiro.modelo)
    falhar_como_runner(store, job, httpx.ConnectError, lambda: executar_job(job, deps(primeiro)))
    assert [n.gmail_id for n in store.newsletters_do_job(job.id)] == ["n1", "n2"]

    store.atualizar_job(job.id, status=JobStatus.RODANDO)
    executar_job(store.job(job.id), deps(FakeLlm(respostas_felizes(["n1", "n2"], 2))))
    assert store.job(job.id).status == JobStatus.SUCESSO
    assert fonte.arquivados == ["n1", "n2"]


def test_feed_reescrito_ao_retomar_antes_de_arquivar(ambiente, monkeypatch):
    config, store, fonte, deps = ambiente
    import falaai.job as modulo

    original = modulo.escrever_atomico
    chamadas = []

    def falha_uma_vez(path, conteudo):
        chamadas.append(path)
        if len(chamadas) == 1:
            raise OSError("disco cheio")
        original(path, conteudo)

    monkeypatch.setattr(modulo, "escrever_atomico", falha_uma_vez)
    llm = FakeLlm(respostas_felizes(["n1", "n2"], 2))
    job = store.criar_job(llm.modelo)
    falhar_como_runner(store, job, OSError, lambda: executar_job(job, deps(llm)))
    assert fonte.arquivados == []

    class FonteQueConfereFeed(FakeFonte):
        def arquivar(self, gmail_ids):
            ep = store.episodio_do_job(job.id)
            assert ep.arquivo in config.feed_path.read_text()
            super().arquivar(gmail_ids)

    d = deps(FakeLlm([]))
    d.fonte = FonteQueConfereFeed(fonte.newsletters)
    store.atualizar_job(job.id, status=JobStatus.RODANDO)
    executar_job(store.job(job.id), d)
    assert d.fonte.arquivados == ["n1", "n2"]


def test_todas_extracoes_falham_levanta_e_mantem_vinculo(ambiente):
    _, store, fonte, deps = ambiente
    llm = FakeLlm([ValueError("a"), ValueError("b")])
    job = store.criar_job(llm.modelo)
    with pytest.raises(RuntimeError, match="b") as e:
        executar_job(job, deps(llm))
    assert isinstance(e.value.__cause__, ValueError)
    assert [n.gmail_id for n in store.newsletters_do_job(job.id)] == ["n1", "n2"]
    assert fonte.arquivados == []


@pytest.mark.parametrize("codigo", [500, 404])
def test_http_status_servidor_quebrado_propaga(ambiente, codigo):
    _, store, _, deps = ambiente
    req = httpx.Request("POST", "http://x")
    erro = httpx.HTTPStatusError("x", request=req, response=httpx.Response(codigo, request=req))
    llm = FakeLlm([erro])
    job = store.criar_job(llm.modelo)
    with pytest.raises(httpx.HTTPStatusError):
        executar_job(job, deps(llm))
    assert [n.gmail_id for n in store.newsletters_do_job(job.id)] == ["n1", "n2"]


def test_coleta_passa_dia_para_fonte(ambiente):
    _, store, fonte, deps = ambiente
    job = store.criar_job("m", date(2026, 11, 6))
    executar_job(job, deps(FakeLlm(respostas_felizes(["n1", "n2"], 1))))
    assert fonte.dias == [date(2026, 11, 6)]


def test_data_do_episodio_e_o_dia_do_job(ambiente):
    _, store, _, deps = ambiente
    job = store.criar_job("m", date(2026, 11, 6))
    llm = FakeLlm(respostas_felizes(["n1", "n2"], 1))
    executar_job(job, deps(llm))
    (ep,) = store.episodios()
    assert ep.data == date(2026, 11, 6)
    assert ep.titulo == "Fala Aí — 6 de novembro de 2026"
    abertura_sistema = llm.chamadas[3][0]
    assert "sexta-feira, 6 de novembro de 2026" in abertura_sistema


def test_extracao_resolve_links(ambiente):
    _, store, _, deps = ambiente
    respostas = respostas_felizes(["n1", "n2"], 1)
    respostas[0] = {
        "itens": [
            {"titulo": "com link", "descricao": "d", "link": "https://rastreio.com/x"},
            {"titulo": "sem link", "descricao": "d", "link": None},
        ]
    }
    d = deps(FakeLlm(respostas))
    d.resolver_link = lambda url: url.replace("rastreio.com/x", "destino.com/artigo")
    executar_job(store.criar_job("m"), d)
    links = [i.link for i in store.itens_extraidos("n1")]
    assert links == ["https://destino.com/artigo", None]
