import io
import wave

from falaai.config import Config
from falaai.domain import Fala
from tests.fakes import FakeTts


def test_config_le_ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("FALAAI_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FALAAI_MAX_MINUTOS", "10")
    c = Config.do_ambiente()
    assert c.db_path == tmp_path / "falaai.db"
    assert c.palavras_max == 1500
    assert c.ollama_modelo == "qwen3:30b-a3b-instruct-2507-q4_K_M"


def test_fake_tts_gera_wav_valido():
    with wave.open(io.BytesIO(FakeTts().sintetizar(Fala("dora", "x")))) as w:
        assert (w.getframerate(), w.getnchannels()) == (24000, 1)
