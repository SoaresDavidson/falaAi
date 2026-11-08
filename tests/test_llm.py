import json

import httpx
import pytest
import respx

from falaai.llm import OllamaLlm

URL = "http://ollama:11434"


@respx.mock
def test_json_envia_schema_e_keep_alive():
    rota = respx.post(f"{URL}/api/chat").respond(
        json={"message": {"content": json.dumps({"ok": 1})}}
    )
    schema = {"type": "object"}
    r = OllamaLlm(URL, "m").json("sis", "usr", schema)
    corpo = json.loads(rota.calls[0].request.content)
    assert r == {"ok": 1}
    assert corpo["format"] == schema
    assert corpo["stream"] is False
    assert corpo["keep_alive"] == "5m"
    assert corpo["messages"][0] == {"role": "system", "content": "sis"}


@respx.mock
def test_descarregar():
    rota = respx.post(f"{URL}/api/generate").respond(json={})
    OllamaLlm(URL, "m").descarregar()
    assert json.loads(rota.calls[0].request.content) == {"model": "m", "keep_alive": 0}


@respx.mock
def test_erro_de_rede_propaga():
    respx.post(f"{URL}/api/chat").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(httpx.ConnectError):
        OllamaLlm(URL, "m").json("s", "u", {})
