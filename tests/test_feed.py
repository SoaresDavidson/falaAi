import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime

from falaai.domain import Episodio
from falaai.feed import escrever_atomico, nome_arquivo, render_feed, titulo_episodio
from tests.fakes import item


def test_titulo():
    assert titulo_episodio(date(2026, 11, 8)) == "Fala Aí — 8 de novembro de 2026"


def test_nome_arquivo():
    assert nome_arquivo(date(2026, 11, 8), 42) == "falaai-2026-11-08-42.mp3"


def _ep(job_id: int) -> Episodio:
    d = date(2026, 11, 8)
    return Episodio(
        job_id=job_id,
        titulo=titulo_episodio(d),
        data=d,
        arquivo=nome_arquivo(d, job_id),
        duracao_s=61.7,
        tamanho_bytes=1234,
        shownotes=(item("com", link="https://a.com"), item("sem", link=None)),
        publicado_em=datetime(2026, 11, 8, 7, 0, tzinfo=UTC),
    )


def test_feed_enclosure_e_shownotes():
    xml = render_feed([_ep(1), _ep(2)], "http://host:8000")
    root = ET.fromstring(xml)
    itens = root.findall("./channel/item")
    assert len(itens) == 2
    assert root.find("./channel/title").text == "Fala Aí"
    assert root.find("./channel/language").text == "pt-br"
    enc = next(i.find("enclosure") for i in itens if i.find("guid").text.endswith("-1.mp3"))
    assert enc.get("url") == "http://host:8000/episodes/falaai-2026-11-08-1.mp3"
    assert enc.get("type") == "audio/mpeg"
    assert enc.get("length") == "1234"
    desc = itens[0].find("description").text
    assert 'href="https://a.com"' in desc
    assert "sem" in desc
    assert "<ul>" in desc


def test_escrever_atomico(tmp_path):
    p = tmp_path / "feed.xml"
    escrever_atomico(p, b"abc")
    assert p.read_bytes() == b"abc"
    assert [x.name for x in tmp_path.iterdir()] == ["feed.xml"]
