"""Montagem do mp3 do Episódio com ffmpeg."""

import os
import subprocess
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

_FORMATO = "aresample=24000,aformat=sample_fmts=s16:channel_layouts=mono"


def montar_audio(wavs: Sequence[bytes], pausa_ms: int, destino: Path) -> float:
    if not wavs:
        raise ValueError("nenhum áudio para montar")
    tmp_mp3 = destino.with_suffix(".tmp.mp3")
    try:
        _codificar(wavs, pausa_ms, tmp_mp3)
        os.replace(tmp_mp3, destino)
    except BaseException:
        tmp_mp3.unlink(missing_ok=True)
        raise
    return _duracao(destino)


def _rodar(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode(errors="replace").strip()
        raise RuntimeError(f"{cmd[0]} falhou (código {e.returncode}): {stderr}") from e


def _codificar(wavs: Sequence[bytes], pausa_ms: int, tmp_mp3: Path) -> None:
    with TemporaryDirectory() as pasta:
        entradas: list[str] = []
        for i, wav in enumerate(wavs):
            caminho = Path(pasta) / f"{i:04d}.wav"
            caminho.write_bytes(wav)
            entradas += ["-i", str(caminho)]
        partes: list[str] = []
        rotulos: list[str] = []
        for i in range(len(wavs)):
            partes.append(f"[{i}:a]{_FORMATO}[a{i}]")
            rotulos.append(f"[a{i}]")
            if i < len(wavs) - 1:
                partes.append(
                    f"anullsrc=r=24000:cl=mono,atrim=duration={pausa_ms / 1000},{_FORMATO}[p{i}]"
                )
                rotulos.append(f"[p{i}]")
        partes.append(f"{''.join(rotulos)}concat=n={len(rotulos)}:v=0:a=1[out]")
        _rodar(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                *entradas,
                "-filter_complex",
                ";".join(partes),
                "-map",
                "[out]",
                "-ac",
                "1",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "64k",
                "-f",
                "mp3",
                str(tmp_mp3),
            ]
        )


def _duracao(destino: Path) -> float:
    saida = _rodar(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(destino),
        ]
    )
    return float(saida.stdout.decode().strip())
