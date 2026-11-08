"""Feed RSS do Podcast."""

import os
import tempfile
from collections.abc import Sequence
from datetime import date
from html import escape
from pathlib import Path

from feedgen.feed import FeedGenerator

from falaai.domain import Episodio, Item

_MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]  # fmt: skip


def titulo_episodio(data: date) -> str:
    return f"Fala Aí — {data.day} de {_MESES[data.month - 1]} de {data.year}"


def nome_arquivo(data: date, job_id: int) -> str:
    return f"falaai-{data.isoformat()}-{job_id}.mp3"


def _shownotes_html(itens: Sequence[Item]) -> str:
    linhas = []
    for it in itens:
        titulo = escape(it.titulo)
        if it.link is not None:
            titulo = f'<a href="{escape(it.link, quote=True)}">{titulo}</a>'
        linhas.append(f"<li>{titulo} — {escape(it.fonte)}</li>")
    return "<ul>" + "".join(linhas) + "</ul>"


def render_feed(episodios: Sequence[Episodio], base_url: str) -> bytes:
    fg = FeedGenerator()
    fg.load_extension("podcast")
    fg.title("Fala Aí")
    fg.link(href=base_url, rel="alternate")
    fg.description("Newsletters do dia em formato de podcast.")
    fg.language("pt-br")
    fg.podcast.itunes_category("Technology")
    for ep in episodios:
        fe = fg.add_entry(order="append")
        fe.id(ep.arquivo)
        fe.guid(ep.arquivo, permalink=False)
        fe.title(ep.titulo)
        fe.description(_shownotes_html(ep.shownotes))
        fe.pubDate(ep.publicado_em)
        fe.enclosure(f"{base_url}/episodes/{ep.arquivo}", str(ep.tamanho_bytes), "audio/mpeg")
        fe.podcast.itunes_duration(int(ep.duracao_s))
    return fg.rss_str(pretty=True)


def escrever_atomico(path: Path, conteudo: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(conteudo)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
