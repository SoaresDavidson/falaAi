"""Troca links de rastreamento das newsletters pelo endereço final."""

import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

log = logging.getLogger(__name__)

# Parâmetros de rastreamento de plataformas de newsletter (beehiiv, Mailchimp) e anúncios.
RASTREIO = {"_bhlid", "mc_cid", "mc_eid", "fbclid", "gclid"}


def novo_cliente() -> httpx.Client:
    return httpx.Client(
        follow_redirects=True,
        max_redirects=5,
        timeout=5,
        headers={"User-Agent": "Mozilla/5.0 (compatible; falaai)"},
    )


def _sem_rastreio(url: str) -> str:
    partes = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(partes.query, keep_blank_values=True)]
    limpa = [
        (k, v) for k, v in query if not k.lower().startswith("utm_") and k.lower() not in RASTREIO
    ]
    if len(limpa) == len(query):
        return url
    return urlunsplit(partes._replace(query=urlencode(limpa)))


def resolver_link(url: str, cliente: httpx.Client) -> str:
    """Segue os redirecionamentos e devolve o destino sem parâmetros de rastreamento.

    Só abre links https e só aceita destino https. Em qualquer falha, devolve o
    link original. Só lê os cabeçalhos: o corpo da página nunca é baixado.
    """
    if not url.startswith("https://"):
        return url
    try:
        with cliente.stream("GET", url) as resposta:
            final = str(resposta.url)
    except httpx.HTTPError:
        log.info("link não resolvido: %s", url, exc_info=True)
        return url
    if not final.startswith("https://"):
        return url
    return _sem_rastreio(final)
