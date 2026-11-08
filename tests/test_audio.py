import json
import shutil
import subprocess

import pytest

from falaai.audio import montar_audio
from tests.fakes import wav_silencio

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="sem ffmpeg")


def test_concatena_com_pausas(tmp_path):
    destino = tmp_path / "ep.mp3"
    duracao = montar_audio([wav_silencio(1.0)] * 3, 300, destino)
    assert abs(duracao - 3.6) < 0.15
    inicio = destino.read_bytes()[:3]
    assert inicio == b"ID3" or inicio[0] == 0xFF
    saida = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=channels",
            "-of",
            "json",
            str(destino),
        ],
        check=True,
        capture_output=True,
    )
    assert json.loads(saida.stdout)["streams"][0]["channels"] == 1
    assert not list(tmp_path.glob("*.tmp.mp3"))


def test_vazio_levanta(tmp_path):
    with pytest.raises(ValueError):
        montar_audio([], 300, tmp_path / "ep.mp3")
