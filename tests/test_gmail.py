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


def _eml_bruto(cabecalhos: str, corpo: str = "corpo") -> bytes:
    return f"From: a@b.c\nSubject: s\n{cabecalhos}\n\n{corpo}\n".encode()


def test_sem_date_usa_agora():
    n = newsletter_de_mime("1", _eml_bruto("Content-Type: text/plain"), 100)
    assert n.recebida_em.tzinfo is not None


def test_date_malformado_usa_agora():
    raw = _eml_bruto("Date: lixo\nContent-Type: text/plain")
    assert newsletter_de_mime("1", raw, 100).recebida_em.tzinfo is not None


def test_date_naive_vira_utc():
    raw = _eml_bruto("Date: Sat, 08 Nov 2026 07:00:00 -0000\nContent-Type: text/plain")
    assert newsletter_de_mime("1", raw, 100).recebida_em.tzinfo is not None


def test_charset_desconhecido():
    raw = _eml_bruto(
        "Date: Sat, 08 Nov 2026 07:00:00 -0300\nContent-Type: text/plain; charset=x-desconhecido",
        "olá",
    )
    assert "ol" in newsletter_de_mime("1", raw, 100).texto


class FakeCreds:
    valid = False
    refresh_token = "r"

    def refresh(self, request):
        self.refrescou = True

    def to_json(self):
        return '{"novo": true}'


def test_refresh_regrava_token_0600(tmp_path, monkeypatch):
    from google.oauth2.credentials import Credentials

    creds = FakeCreds()
    monkeypatch.setattr(Credentials, "from_authorized_user_file", lambda *a, **k: creds)
    token = tmp_path / "t.json"
    token.write_text("velho")
    token.chmod(0o644)
    GmailFonte(token, "newsletter", 10)._credenciais()
    assert creds.refrescou
    assert token.read_text() == '{"novo": true}'
    assert token.stat().st_mode & 0o777 == 0o600


def test_sem_refresh_token_erro_claro(tmp_path, monkeypatch):
    import pytest
    from google.oauth2.credentials import Credentials

    creds = FakeCreds()
    creds.refresh_token = None
    monkeypatch.setattr(Credentials, "from_authorized_user_file", lambda *a, **k: creds)
    with pytest.raises(RuntimeError, match="falaai auth"):
        GmailFonte(tmp_path / "t.json", "newsletter", 10)._credenciais()


def test_autorizar_grava_0600(tmp_path, monkeypatch):
    from google_auth_oauthlib.flow import InstalledAppFlow

    from falaai.gmail import autorizar

    class Flow:
        def run_local_server(self, port):
            return FakeCreds()

    monkeypatch.setattr(InstalledAppFlow, "from_client_secrets_file", lambda *a, **k: Flow())
    saida = tmp_path / "tok.json"
    autorizar(tmp_path / "cs.json", saida)
    assert saida.read_text() == '{"novo": true}'
    assert saida.stat().st_mode & 0o777 == 0o600


def test_pendentes_isola_mensagem_ruim(tmp_path):
    svc = FakeServico(
        {None: {"messages": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}},
        {
            "a": _eml("Sat, 08 Nov 2026 09:00:00 -0300"),
            "b": b"lixo",
            "c": _eml("Sat, 08 Nov 2026 08:00:00 -0300"),
        },
    )
    orig = svc.get

    def get(**kw):
        if kw["id"] == "b":
            raise ValueError("quebrou")
        return orig(**kw)

    svc.get = get
    res = GmailFonte(tmp_path / "t.json", "newsletter", 100, servico=svc).pendentes()
    assert [n.gmail_id for n in res] == ["c", "a"]
