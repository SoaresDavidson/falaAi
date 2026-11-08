"""Cliente HTTP do serviço Kokoro que roda no laptop."""

import httpx

from falaai.domain import Fala

VOZES_PADRAO = {"dora": "pf_dora", "alex": "pm_alex"}


class KokoroTts:
    def __init__(
        self,
        url: str,
        vozes: dict[str, str] | None = None,
        timeout_s: float = 300,
    ) -> None:
        self._url = url.rstrip("/")
        self._vozes = dict(VOZES_PADRAO if vozes is None else vozes)
        self._timeout_s = timeout_s

    def sintetizar(self, fala: Fala) -> bytes:
        voz = self._vozes.get(fala.apresentador)
        if voz is None:
            raise ValueError(f"apresentador desconhecido: {fala.apresentador!r}")
        resposta = httpx.post(
            f"{self._url}/v1/audio/speech",
            json={"input": fala.texto, "voice": voz},
            timeout=self._timeout_s,
        )
        resposta.raise_for_status()
        return resposta.content
