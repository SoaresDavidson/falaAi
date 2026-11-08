"""Orquestração do Job: transforma as Newsletters pendentes em um Episódio publicado.

Cada estágio grava seu resultado no Store antes do próximo começar, então um Job
interrompido (laptop dormindo, rede caindo) retoma do ponto onde parou. Ver ADR-0002.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from falaai.audio import montar_audio
from falaai.config import Config
from falaai.domain import Episodio, Estagio, Item, Job, JobStatus, Pauta, Roteiro
from falaai.feed import escrever_atomico, nome_arquivo, render_feed, titulo_episodio
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


def montar_dependencias(config: Config) -> Dependencias:
    from falaai.gmail import GmailFonte
    from falaai.llm import OllamaLlm
    from falaai.tts import KokoroTts

    config.episodios_dir.mkdir(parents=True, exist_ok=True)
    return Dependencias(
        store=Store(config.db_path),
        fonte=GmailFonte(config.gmail_token, config.gmail_rotulo, config.texto_max_chars),
        llm=OllamaLlm(config.ollama_url, config.ollama_modelo),
        tts=KokoroTts(config.tts_url),
        config=config,
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
        arquivo = nome_arquivo(deps.hoje(), job.id)
        destino = deps.config.episodios_dir / arquivo
        wavs = [deps.tts.sintetizar(fala) for fala in roteiro.falas()]
        duracao = montar_audio(wavs, deps.config.pausa_ms, destino)

        estagio(Estagio.PUBLICACAO)
        episodio = store.salvar_episodio(
            Episodio(
                job_id=job.id,
                titulo=titulo_episodio(deps.hoje()),
                data=deps.hoje(),
                arquivo=arquivo,
                duracao_s=duracao,
                tamanho_bytes=destino.stat().st_size,
                shownotes=_shownotes(pauta),
                publicado_em=deps.agora(),
            )
        )
        escrever_atomico(
            deps.config.feed_path,
            render_feed(store.episodios(), deps.config.feed_base_url),
        )

    estagio(Estagio.ARQUIVAMENTO)
    deps.fonte.arquivar([n.gmail_id for n in store.newsletters_do_job(job.id)])
    terminar(JobStatus.SUCESSO)


def _coletar(job: Job, deps: Dependencias) -> bool:
    if not deps.store.newsletters_do_job(job.id):
        deps.store.vincular_newsletters(job.id, deps.fonte.pendentes())
    return bool(deps.store.newsletters_do_job(job.id))


def _extrair(job: Job, deps: Dependencias) -> list[Item]:
    """Uma Newsletter que falha na extração sai do Job e continua pendente no Gmail."""
    itens: list[Item] = []
    for newsletter in deps.store.newsletters_do_job(job.id):
        extraidos = deps.store.itens_extraidos(newsletter.gmail_id)
        if extraidos is None:
            try:
                extraidos = extrair_itens(deps.llm, newsletter)
            except Exception:
                log.warning(
                    "extração falhou; newsletter %s fica pendente",
                    newsletter.gmail_id,
                    exc_info=True,
                )
                deps.store.desvincular_newsletter(job.id, newsletter.gmail_id)
                continue
            deps.store.salvar_itens(newsletter.gmail_id, extraidos)
        itens.extend(extraidos)
    return itens


def _dialogar(job: Job, pauta: Pauta, deps: Dependencias) -> tuple[Roteiro, Pauta]:
    store, llm = deps.store, deps.llm

    def cacheado(chave: str, gerar):
        falas = store.falas(job.id, chave)
        if falas is None:
            falas = gerar()
            store.salvar_falas(job.id, chave, falas)
        return falas

    abertura = cacheado("abertura", lambda: escrever_abertura(llm, pauta, deps.hoje()))
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


def _shownotes(pauta: Pauta) -> tuple[Item, ...]:
    return (*(i for t in pauta.topicos for i in t.itens), *pauta.fora_do_audio)
