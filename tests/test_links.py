import httpx
import respx

from falaai.links import novo_cliente, resolver_link

RASTREIO = "https://elink.mail.exemplo.com/ss/c/abc"


@respx.mock
def test_segue_redirecionamento_e_tira_utm():
    respx.get(RASTREIO).respond(
        302, headers={"Location": "https://site.com/artigo?id=7&utm_source=news&_bhlid=abc"}
    )
    respx.get(url__startswith="https://site.com/artigo").respond(200, text="x")
    assert resolver_link(RASTREIO, novo_cliente()) == "https://site.com/artigo?id=7"


@respx.mock
def test_sem_utm_mantem_url_intacta():
    respx.get(RASTREIO).respond(302, headers={"Location": "https://site.com/a?b=1&c="})
    respx.get(url__startswith="https://site.com/a").respond(200)
    assert resolver_link(RASTREIO, novo_cliente()) == "https://site.com/a?b=1&c="


@respx.mock
def test_falha_devolve_original():
    respx.get(RASTREIO).mock(side_effect=httpx.ConnectError("bloqueado"))
    assert resolver_link(RASTREIO, novo_cliente()) == RASTREIO


@respx.mock
def test_destino_http_devolve_original():
    respx.get(RASTREIO).respond(302, headers={"Location": "http://site.com/a"})
    respx.get("http://site.com/a").respond(200)
    assert resolver_link(RASTREIO, novo_cliente()) == RASTREIO


@respx.mock
def test_link_http_nem_e_aberto():
    rota = respx.get("http://site.com/a").respond(200)
    assert resolver_link("http://site.com/a", novo_cliente()) == "http://site.com/a"
    assert not rota.called
