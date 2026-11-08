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
