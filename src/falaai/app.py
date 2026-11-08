"""App HTTP: dispara Jobs, serve feed, episódios e métricas."""

import dataclasses
import functools
import re
from datetime import date

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

from falaai.config import Config
from falaai.runner import JobEmAndamento, JobRunner
from falaai.store import Store

NOME_EPISODIO = re.compile(r"^falaai-\d{4}-\d{2}-\d{2}-\d+\.mp3$")


def criar_app(
    config: Config | None = None,
    runner: JobRunner | None = None,
    registry: CollectorRegistry | None = None,
) -> Starlette:
    config = config or Config.do_ambiente()
    if runner is None:
        from falaai.job import executar_job, montar_dependencias

        config.data_dir.mkdir(parents=True, exist_ok=True)
        config.episodios_dir.mkdir(parents=True, exist_ok=True)
        registry = registry if registry is not None else CollectorRegistry()
        runner = JobRunner(
            Store(config.db_path),
            functools.partial(executar_job, deps=montar_dependencias(config)),
            config.ollama_modelo,
            registry=registry,
        )
    registry = registry if registry is not None else runner.registry
    store = runner.store
    runner.registrar_interrompidos(store.marcar_interrompidos())

    async def post_jobs(request: Request) -> Response:
        bruto = request.query_params.get("dia")
        try:
            dia = date.fromisoformat(bruto) if bruto else None
        except ValueError:
            return JSONResponse({"erro": "dia inválido; use AAAA-MM-DD"}, status_code=400)
        try:
            job, retomado = runner.iniciar(novo=request.query_params.get("novo") == "1", dia=dia)
        except JobEmAndamento:
            return JSONResponse({"erro": "job em andamento"}, status_code=409)
        return JSONResponse({"job_id": job.id, "retomado": retomado}, status_code=202)

    async def get_ultimo(request: Request) -> Response:
        job = store.ultimo_job()
        if job is None:
            return JSONResponse({"erro": "nenhum job"}, status_code=404)
        return JSONResponse(
            {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in dataclasses.asdict(job).items()
            }
        )

    async def get_feed(request: Request) -> Response:
        if not config.feed_path.is_file():
            return JSONResponse({"erro": "feed inexistente"}, status_code=404)
        return FileResponse(config.feed_path, media_type="application/rss+xml")

    async def get_episodio(request: Request) -> Response:
        nome = request.path_params["nome"]
        if not NOME_EPISODIO.fullmatch(nome):
            return JSONResponse({"erro": "não encontrado"}, status_code=404)
        caminho = config.episodios_dir / nome
        if not caminho.is_file():
            return JSONResponse({"erro": "não encontrado"}, status_code=404)
        return FileResponse(caminho, media_type="audio/mpeg")

    async def get_metrics(request: Request) -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return Starlette(
        routes=[
            Route("/jobs", post_jobs, methods=["POST"]),
            Route("/jobs/ultimo", get_ultimo, methods=["GET"]),
            Route("/feed.xml", get_feed, methods=["GET"]),
            Route("/episodes/{nome}", get_episodio, methods=["GET"]),
            Route("/metrics", get_metrics, methods=["GET"]),
        ]
    )
