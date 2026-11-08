import base64
from pathlib import Path

from falaai.gmail import GmailFonte, newsletter_de_mime

FIX = Path(__file__).parent / "fixtures"
PIXEL = "track.exemplo.com"


def _raw(nome: str) -> bytes:
    return (FIX / nome).read_bytes()


def test_html_vira_markdown():
    n = newsletter_de_mime("1", _raw("newsletter_html.eml"), 30000)
    assert n.assunto == "Notícias do dia"
    assert n.remetente.startswith("Boletim Tech")
    assert "](https://" in n.texto
    assert "<img" not in n.texto
    assert PIXEL not in n.texto
    assert "x()" not in n.texto
    assert "Versao em texto puro" not in n.texto
    assert n.recebida_em.tzinfo is not None


def test_texto_iso_8859_1():
    n = newsletter_de_mime("2", _raw("newsletter_texto.eml"), 30000)
    assert "Coração e ação em São Paulo" in n.texto
    assert n.assunto == "Edição"


def test_trunca():
    n = newsletter_de_mime("1", _raw("newsletter_html.eml"), 50)
    assert len(n.texto) <= 50


class _Exec:
    def __init__(self, v):
        self.v = v

    def execute(self):
        return self.v


class FakeServico:
    def __init__(self, paginas, brutos):
        self.paginas = paginas
        self.brutos = brutos
        self.chamadas = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, **kw):
        self.chamadas.append(("list", kw))
        return _Exec(self.paginas[kw.get("pageToken")])

    def get(self, **kw):
        self.chamadas.append(("get", kw))
        raw = base64.urlsafe_b64encode(self.brutos[kw["id"]]).decode()
        return _Exec({"id": kw["id"], "raw": raw})

    def batchModify(self, **kw):
        self.chamadas.append(("batchModify", kw))
        return _Exec({})


def _eml(data: str) -> bytes:
    return f"From: a@b.c\nSubject: s\nDate: {data}\nContent-Type: text/plain\n\ncorpo\n".encode()


def test_pendentes_pagina_e_ordena(tmp_path):
    svc = FakeServico(
        {
            None: {"messages": [{"id": "a"}, {"id": "b"}], "nextPageToken": "T"},
            "T": {"messages": [{"id": "c"}]},
        },
        {
            "a": _eml("Sat, 08 Nov 2026 09:00:00 -0300"),
            "b": _eml("Sat, 08 Nov 2026 07:00:00 -0300"),
            "c": _eml("Sat, 08 Nov 2026 08:00:00 -0300"),
        },
    )
    fonte = GmailFonte(tmp_path / "t.json", "newsletter", 1000, servico=svc)
    res = fonte.pendentes()
    assert [n.gmail_id for n in res] == ["b", "c", "a"]
    lists = [kw for nome, kw in svc.chamadas if nome == "list"]
    assert all(kw["q"] == "label:newsletter in:inbox" for kw in lists)
    assert all(kw["format"] == "raw" for nome, kw in svc.chamadas if nome == "get")


def test_arquivar_remove_inbox(tmp_path):
    svc = FakeServico({}, {})
    fonte = GmailFonte(tmp_path / "t.json", "newsletter", 1000, servico=svc)
    fonte.arquivar([])
    assert svc.chamadas == []
    fonte.arquivar(["a", "b"])
    ((nome, kw),) = svc.chamadas
    assert nome == "batchModify"
    assert kw["body"] == {"ids": ["a", "b"], "removeLabelIds": ["INBOX"]}
