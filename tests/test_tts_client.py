import json

import httpx
import pytest
import respx

from falaai.domain import Fala
from falaai.tts import KokoroTts

URL = "http://tts.test"


@respx.mock
def test_mapeia_apresentador_para_voz():
    rota = respx.post(f"{URL}/v1/audio/speech").respond(200, content=b"RIFFxx")
    audio = KokoroTts(URL).sintetizar(Fala("alex", "oi"))
    assert audio == b"RIFFxx"
    corpo = json.loads(rota.calls.last.request.content)
    assert corpo["voice"] == "pm_alex"
    assert corpo["input"] == "oi"


@respx.mock
def test_erro_http_levanta():
    respx.post(f"{URL}/v1/audio/speech").respond(500)
    with pytest.raises(httpx.HTTPStatusError):
        KokoroTts(URL).sintetizar(Fala("dora", "oi"))


def test_apresentador_desconhecido():
    with pytest.raises(ValueError, match="apresentador"):
        KokoroTts(URL).sintetizar(Fala("zed", "oi"))  # type: ignore[arg-type]
