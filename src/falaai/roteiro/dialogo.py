"""Estágio de diálogo: Pauta -> Falas, e aplicação do teto de palavras."""

from dataclasses import replace
from datetime import date

from falaai.domain import Fala, Pauta, Roteiro, Topico
from falaai.ports import Llm
from falaai.roteiro import prompts

SCHEMA = {
    "type": "object",
    "properties": {
        "falas": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "apresentador": {"type": "string", "enum": ["dora", "alex"]},
                    "texto": {"type": "string"},
                },
                "required": ["apresentador", "texto"],
            },
        }
    },
    "required": ["falas"],
}

# O modelo às vezes devolve "falas": [] mesmo com minItems no schema.
TENTATIVAS = 3

PALAVRAS_ABERTURA = 60
PALAVRAS_FECHAMENTO = 50

_MESES = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]
_DIAS = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
]


def _falas(resposta: dict) -> tuple[Fala, ...]:
    falas = []
    for bruta in resposta.get("falas") or []:
        apresentador = bruta.get("apresentador")
        texto = (bruta.get("texto") or "").strip()
        if apresentador in ("dora", "alex") and texto:
            falas.append(Fala(apresentador, texto))
    if not falas:
        raise ValueError("o LLM não devolveu nenhuma fala válida")
    return tuple(falas)


def _pedir_falas(llm: Llm, sistema: str, usuario: str) -> tuple[Fala, ...]:
    for tentativa in range(TENTATIVAS):
        try:
            return _falas(llm.json(sistema, usuario, SCHEMA))
        except ValueError:
            if tentativa == TENTATIVAS - 1:
                raise
    raise AssertionError("inalcançável")


def _titulos(pauta: Pauta) -> str:
    return "\n".join(f"- {t.titulo}" for t in pauta.topicos)


def escrever_abertura(llm: Llm, pauta: Pauta, data: date) -> tuple[Fala, ...]:
    data_ptbr = f"{_DIAS[data.weekday()]}, {data.day} de {_MESES[data.month - 1]} de {data.year}"
    sistema = prompts.ABERTURA.format(data=data_ptbr, palavras_alvo=PALAVRAS_ABERTURA)
    return _pedir_falas(llm, sistema, f"Assuntos do dia:\n{_titulos(pauta)}")


def escrever_bloco(llm: Llm, topico: Topico) -> tuple[Fala, ...]:
    sistema = prompts.BLOCO.format(titulo=topico.titulo, palavras_alvo=topico.palavras_alvo)
    usuario = "\n\n".join(f"Fonte: {i.fonte}\n{i.titulo}\n{i.descricao}" for i in topico.itens)
    return _pedir_falas(llm, sistema, usuario)


def escrever_fechamento(llm: Llm, pauta: Pauta) -> tuple[Fala, ...]:
    sistema = prompts.FECHAMENTO.format(palavras_alvo=PALAVRAS_FECHAMENTO)
    return _pedir_falas(llm, sistema, f"Assuntos falados hoje:\n{_titulos(pauta)}")


def aplicar_teto(roteiro: Roteiro, pauta: Pauta, palavras_max: int) -> tuple[Roteiro, Pauta]:
    assert len(roteiro.blocos) == len(pauta.topicos)
    blocos = list(roteiro.blocos)
    topicos = list(pauta.topicos)
    fora = list(pauta.fora_do_audio)
    while blocos and replace(roteiro, blocos=tuple(blocos)).palavras() > palavras_max:
        blocos.pop()
        if topicos:
            fora.extend(topicos.pop().itens)
    return (
        replace(roteiro, blocos=tuple(blocos)),
        Pauta(topicos=tuple(topicos), fora_do_audio=tuple(fora)),
    )
