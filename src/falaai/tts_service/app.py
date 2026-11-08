"""Serviço HTTP do Kokoro (roda no laptop com GPU)."""

import gc
import io
import logging
import threading
import time
import wave
from collections.abc import Callable
from typing import Any

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

VOZES_VALIDAS = {"pf_dora", "pm_alex"}
TAXA = 24000
VERIFICA_A_CADA_S = 10

log = logging.getLogger(__name__)

Pipeline = Callable[[str, str], Any]


def _fabrica_padrao() -> Pipeline:
    import numpy as np
    import torch
    from kokoro import KPipeline

    pipe = KPipeline(lang_code="p", device="cuda" if torch.cuda.is_available() else "cpu")

    def sintetizar(texto: str, voz: str):
        partes = []
        for _, _, audio in pipe(texto, voice=voz):
            if audio is None:
                continue
            partes.append(np.asarray(audio.cpu() if hasattr(audio, "cpu") else audio))
        if not partes:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(partes).astype(np.float32)

    return sintetizar


def _para_wav(audio) -> bytes:
    import numpy as np

    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class Servico:
    def __init__(
        self, fabrica: Callable[[], Pipeline], ocioso_s: float, relogio: Callable[[], float]
    ):
        self._fabrica = fabrica
        self._ocioso_s = ocioso_s
        self._relogio = relogio
        self._lock = threading.Lock()  # serializa síntese e descarga
        self._pipeline: Pipeline | None = None
        self._ultimo_uso = relogio()

    @property
    def carregado(self) -> bool:
        return self._pipeline is not None

    def sintetizar(self, texto: str, voz: str) -> bytes:
        with self._lock:
            if self._pipeline is None:
                self._pipeline = self._fabrica()
            try:
                audio = self._pipeline(texto, voz)
            finally:
                self._ultimo_uso = self._relogio()
            return _para_wav(audio)

    def _talvez_descarregar(self) -> None:
        with self._lock:
            if self._pipeline is None:
                return
            if self._relogio() - self._ultimo_uso <= self._ocioso_s:
                return
            del self._pipeline
            self._pipeline = None
            gc.collect()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

    def _ciclo_vigia(self) -> None:
        try:
            self._talvez_descarregar()
        except Exception:
            log.exception("falha ao descarregar o pipeline ocioso")

    def iniciar_vigia(self) -> None:
        def laco() -> None:
            while True:
                time.sleep(VERIFICA_A_CADA_S)
                self._ciclo_vigia()

        threading.Thread(target=laco, daemon=True, name="tts-ocioso").start()


def criar_app(
    fabrica_pipeline: Callable[[], Pipeline] | None = None,
    ocioso_s: float = 120,
    relogio: Callable[[], float] = time.monotonic,
) -> Starlette:
    servico = Servico(fabrica_pipeline or _fabrica_padrao, ocioso_s, relogio)

    async def health(_: Request) -> Response:
        return JSONResponse({"carregado": servico.carregado})

    async def fala(request: Request) -> Response:
        try:
            corpo = await request.json()
        except ValueError:
            return JSONResponse({"erro": "JSON inválido"}, status_code=422)
        texto = corpo.get("input") if isinstance(corpo, dict) else None
        voz = corpo.get("voice") if isinstance(corpo, dict) else None
        if not isinstance(texto, str) or not texto.strip():
            return JSONResponse({"erro": "input vazio"}, status_code=422)
        if voz not in VOZES_VALIDAS:
            return JSONResponse({"erro": "voz desconhecida"}, status_code=422)
        wav = await run_in_threadpool(servico.sintetizar, texto, voz)
        return Response(wav, media_type="audio/wav")

    app = Starlette(
        routes=[
            Route("/health", health),
            Route("/v1/audio/speech", fala, methods=["POST"]),
        ]
    )
    app.state.servico = servico
    servico.iniciar_vigia()
    return app
