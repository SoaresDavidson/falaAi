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
        subprocess.run(
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
            ],
            check=True,
            capture_output=True,
        )
    os.replace(tmp_mp3, destino)
    saida = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(destino),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(saida.stdout.strip())
