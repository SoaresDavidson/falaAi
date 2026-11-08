from datetime import UTC, date, datetime

import pytest

from falaai.domain import (
    Episodio,
    Estagio,
    Fala,
    JobStatus,
    Pauta,
    Topico,
)
from falaai.store import Store
from tests.fakes import item, newsletter


def test_job_ciclo(tmp_path):
    s = Store(tmp_path / "t.db")
    j = s.criar_job("m")
    assert j.status == JobStatus.RODANDO
    assert j.estagio == Estagio.COLETA
    s.atualizar_job(j.id, status=JobStatus.ERRO, erro="x", terminar=True)
    assert s.job(j.id).terminado_em is not None
    assert s.job_retomavel().id == j.id


def test_retomavel_none_apos_sucesso(tmp_path):
    s = Store(tmp_path / "t.db")
    s.criar_job("m")
    j = s.criar_job("m")
    s.atualizar_job(j.id, status=JobStatus.SUCESSO, terminar=True)
    assert s.job_retomavel() is None
    assert s.ultimo_job().id == j.id


def test_marcar_interrompidos(tmp_path):
    s = Store(tmp_path / "t.db")
    a, b = s.criar_job("m"), s.criar_job("m")
    assert s.marcar_interrompidos() == 2
    assert s.job(a.id).erro == "interrompido"
    assert s.job(b.id).status == JobStatus.ERRO


def test_itens_none_vs_vazio(tmp_path):
    s = Store(tmp_path / "t.db")
    assert s.itens_extraidos("n1") is None
    s.salvar_itens("n1", [])
    assert s.itens_extraidos("n1") == []


def test_roundtrip_pauta_falas_episodio(tmp_path):
    s = Store(tmp_path / "t.db")
    j = s.criar_job("m")
    s.salvar_itens("n1", [item("a"), item("b", link=None)])
    assert s.itens_extraidos("n1") == [item("a"), item("b", link=None)]
    pauta = Pauta(
        topicos=(Topico("T", (item("a"), item("b", link=None)), 100),),
        fora_do_audio=(item("c"),),
    )
    s.salvar_pauta(j.id, pauta)
    assert s.pauta(j.id) == pauta
    assert s.pauta(999) is None
    falas = [Fala("dora", "oi"), Fala("alex", "e aí")]
    s.salvar_falas(j.id, "topico:0", falas)
    assert s.falas(j.id, "topico:0") == tuple(falas)
    assert s.falas(j.id, "abertura") is None
    ep = Episodio(
        job_id=j.id,
        titulo="E",
        data=date(2026, 11, 8),
        arquivo="e.mp3",
        duracao_s=12.5,
        tamanho_bytes=100,
        shownotes=(item("a", link=None),),
        publicado_em=datetime(2026, 11, 8, 7, 0, tzinfo=UTC),
    )
    salvo = s.salvar_episodio(ep)
    assert salvo.id is not None
    assert s.episodio_do_job(j.id) == salvo
    assert s.episodios() == [salvo]


def test_desvincular(tmp_path):
    s = Store(tmp_path / "t.db")
    j = s.criar_job("m")
    n1, n2 = newsletter("n1"), newsletter("n2")
    s.vincular_newsletters(j.id, [n1, n2])
    s.desvincular_newsletter(j.id, "n1")
    assert s.newsletters_do_job(j.id) == [n2]


def test_persiste_entre_instancias(tmp_path):
    p = tmp_path / "t.db"
    j = Store(p).criar_job("m")
    assert Store(p).job(j.id).id == j.id


def test_retomar_limpa_erro_e_terminado_em(tmp_path):
    s = Store(tmp_path / "t.db")
    j = s.criar_job("m")
    s.atualizar_job(j.id, status=JobStatus.ERRO, erro="x", terminar=True)
    s.atualizar_job(j.id, status=JobStatus.RODANDO)
    atual = s.job(j.id)
    assert atual.erro is None
    assert atual.terminado_em is None


def test_job_inexistente(tmp_path):
    with pytest.raises(KeyError):
        Store(tmp_path / "t.db").job(999)


def test_interrompidos_define_terminado_em(tmp_path):
    s = Store(tmp_path / "t.db")
    j = s.criar_job("m")
    s.marcar_interrompidos()
    assert s.job(j.id).terminado_em is not None
