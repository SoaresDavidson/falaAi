"""Orquestração do Job: transforma as Newsletters pendentes em um Episódio publicado.

Cada estágio grava seu resultado no Store antes do próximo começar, então um Job
interrompido (laptop dormindo, rede caindo) retoma do ponto onde parou. Ver ADR-0002.
"""

import functools
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx

from falaai.audio import montar_audio
from falaai.config import Config
from falaai.domain import Episodio, Estagio, Item, Job, JobStatus, Pauta, Roteiro
from falaai.feed import escrever_atomico, nome_arquivo, render_feed, titulo_episodio
from falaai.links import novo_cliente, resolver_link
from falaai.ports import FonteNewsletters, Llm, Tts
from falaai.roteiro.dialogo import (
    aplicar_teto,
    escrever_abertura,
    escrever_bloco,
    escrever_fechamento,
)
from falaai.roteiro.extracao import extrair_itens
from falaai.roteiro.pauta import montar_pauta
from falaai.store import Store

log = logging.getLogger(__name__)


def _agora() -> datetime:
    return datetime.now(UTC)


@dataclass
class Dependencias:
    store: Store
    fonte: FonteNewsletters
    llm: Llm
    tts: Tts
    config: Config
    hoje: Callable[[], date] = date.today
    agora: Callable[[], datetime] = field(default=_agora)
    resolver_link: Callable[[str], str] = field(default=lambda url: url)


def montar_dependencias(config: Config) -> Dependencias:
    from falaai.gmail import GmailFonte
    from falaai.llm import OllamaLlm
    from falaai.tts import KokoroTts

    config.episodios_dir.mkdir(parents=True, exist_ok=True)
    fuso = ZoneInfo(config.fuso)
    return Dependencias(
        store=Store(config.db_path),
        fonte=GmailFonte(
            config.gmail_token,
            config.gmail_rotulo,
            config.texto_max_chars,
            janela_dias=config.gmail_janela_dias,
            fuso=fuso,
            rotulo_processada=config.gmail_rotulo_processada,
        ),
        llm=OllamaLlm(config.ollama_url, config.ollama_modelo),
        tts=KokoroTts(config.tts_url),
        config=config,
        hoje=lambda: datetime.now(fuso).date(),
        resolver_link=functools.partial(resolver_link, cliente=novo_cliente()),
    )


def executar_job(job: Job, deps: Dependencias) -> None:
    """Roda (ou retoma) o Job. Exceções propagam; quem marca ERRO é o JobRunner."""
    store = deps.store

    def estagio(e: Estagio) -> None:
        store.atualizar_job(job.id, estagio=e)

    def terminar(status: JobStatus) -> None:
        store.atualizar_job(job.id, status=status, terminar=True)

    episodio = store.episodio_do_job(job.id)
    if episodio is None:
        estagio(Estagio.COLETA)
        if not _coletar(job, deps):
            terminar(JobStatus.SEM_EPISODIO)
            return

        estagio(Estagio.EXTRACAO)
        itens = _extrair(job, deps)
        if not itens:
            terminar(JobStatus.SEM_EPISODIO)
            return

        estagio(Estagio.PAUTA)
        pauta = store.pauta(job.id)
        if pauta is None:
            pauta = montar_pauta(deps.llm, itens, deps.config.palavras_max)
            store.salvar_pauta(job.id, pauta)

        estagio(Estagio.DIALOGO)
        roteiro, pauta = _dialogar(job, pauta, deps)
        # Libera a VRAM do laptop antes do TTS (ADR-0001).
        deps.llm.descarregar()

        estagio(Estagio.AUDIO)
        hoje = _data_episodio(job, deps)
        arquivo = nome_arquivo(hoje, job.id)
        destino = deps.config.episodios_dir / arquivo
        wavs = [deps.tts.sintetizar(fala) for fala in roteiro.falas()]
        duracao = montar_audio(wavs, deps.config.pausa_ms, destino)

        estagio(Estagio.PUBLICACAO)
        episodio = store.salvar_episodio(
            Episodio(
                job_id=job.id,
                titulo=titulo_episodio(hoje),
                data=hoje,
                arquivo=arquivo,
                duracao_s=duracao,
                tamanho_bytes=destino.stat().st_size,
                shownotes=_shownotes(pauta),
                publicado_em=deps.agora(),
            )
        )

    # Reescrito também ao retomar: só arquiva depois de o Episódio estar no feed (ADR-0002).
    escrever_atomico(
        deps.config.feed_path,
        render_feed(store.episodios(), deps.config.feed_base_url),
    )

    estagio(Estagio.ARQUIVAMENTO)
    deps.fonte.arquivar([n.gmail_id for n in store.newsletters_do_job(job.id)])
    terminar(JobStatus.SUCESSO)


def _coletar(job: Job, deps: Dependencias) -> bool:
    if not deps.store.newsletters_do_job(job.id):
        deps.store.vincular_newsletters(job.id, deps.fonte.pendentes(job.dia))
    return bool(deps.store.newsletters_do_job(job.id))


def _extrair(job: Job, deps: Dependencias) -> list[Item]:
    """Uma Newsletter que falha na extração sai do Job e continua pendente no Gmail.

    Se todas as tentadas falham, o problema é o LLM e não as Newsletters: o Job falha.
    """
    itens: list[Item] = []
    falhas: list[str] = []
    tentativas = 0
    ultimo_erro: Exception | None = None
    for newsletter in deps.store.newsletters_do_job(job.id):
        extraidos = deps.store.itens_extraidos(newsletter.gmail_id)
        if extraidos is None:
            tentativas += 1
            try:
                extraidos = extrair_itens(deps.llm, newsletter)
            except (httpx.NetworkError, httpx.ConnectTimeout):
                # Laptop fora do ar não é culpa da Newsletter: o Job falha e é retomado.
                raise
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500 or e.response.status_code == 404:
                    raise  # servidor ou modelo quebrado, não a Newsletter
                ultimo_erro = e
                falhas.append(newsletter.gmail_id)
                log.warning("extração falhou; newsletter %s", newsletter.gmail_id, exc_info=True)
                continue
            except Exception as e:
                ultimo_erro = e
                falhas.append(newsletter.gmail_id)
                log.warning("extração falhou; newsletter %s", newsletter.gmail_id, exc_info=True)
                continue
            extraidos = _resolver_links(extraidos, deps.resolver_link)
            deps.store.salvar_itens(newsletter.gmail_id, extraidos)
        itens.extend(extraidos)
    if tentativas and len(falhas) == tentativas and not itens:
        raise RuntimeError(
            f"extração falhou em todas as {tentativas} newsletters: "
            f"{type(ultimo_erro).__name__}: {ultimo_erro}"
        ) from ultimo_erro
    for gmail_id in falhas:
        deps.store.desvincular_newsletter(job.id, gmail_id)
    return itens


def _dialogar(job: Job, pauta: Pauta, deps: Dependencias) -> tuple[Roteiro, Pauta]:
    store, llm = deps.store, deps.llm

    def cacheado(chave: str, gerar):
        falas = store.falas(job.id, chave)
        if falas is None:
            falas = gerar()
            store.salvar_falas(job.id, chave, falas)
        return falas

    abertura = cacheado(
        "abertura", lambda: escrever_abertura(llm, pauta, _data_episodio(job, deps))
    )
    blocos = tuple(
        cacheado(f"topico:{i}", lambda t=topico: escrever_bloco(llm, t))
        for i, topico in enumerate(pauta.topicos)
    )
    fechamento = cacheado("fechamento", lambda: escrever_fechamento(llm, pauta))

    roteiro, pauta_final = aplicar_teto(
        Roteiro(abertura=abertura, blocos=blocos, fechamento=fechamento),
        pauta,
        deps.config.palavras_max,
    )
    if pauta_final != pauta:
        store.salvar_pauta(job.id, pauta_final)
    return roteiro, pauta_final


def _data_episodio(job: Job, deps: Dependencias) -> date:
    """Um Job de `?dia=` fala daquele dia, não de quando rodou."""
    return job.dia or deps.hoje()


def _resolver_links(itens: list[Item], resolver: Callable[[str], str]) -> list[Item]:
    with ThreadPoolExecutor(max_workers=8) as pool:
        links = list(pool.map(lambda i: resolver(i.link) if i.link else None, itens))
    return [replace(i, link=link) for i, link in zip(itens, links, strict=True)]


def _shownotes(pauta: Pauta) -> tuple[Item, ...]:
    return (*(i for t in pauta.topicos for i in t.itens), *pauta.fora_do_audio)
