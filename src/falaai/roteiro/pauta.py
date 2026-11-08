"""Estágio de pauta: Itens -> Tópicos dentro do orçamento de palavras."""

from collections.abc import Sequence

from falaai.domain import Item, Pauta, Topico
from falaai.ports import Llm
from falaai.roteiro import prompts

SCHEMA = {
    "type": "object",
    "properties": {
        "topicos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string"},
                    "indices": {"type": "array", "items": {"type": "integer"}},
                    "palavras_alvo": {"type": "integer"},
                },
                "required": ["titulo", "indices", "palavras_alvo"],
            },
        }
    },
    "required": ["topicos"],
}


def montar_pauta(llm: Llm, itens: Sequence[Item], palavras_max: int) -> Pauta:
    orcamento = palavras_max * 0.85
    listagem = "\n".join(
        f"[{i}] {it.titulo} ({it.fonte}): {it.descricao}" for i, it in enumerate(itens)
    )
    sistema = prompts.PAUTA.format(palavras_max=int(orcamento))
    resposta = llm.json(sistema, listagem, SCHEMA)

    usados: set[int] = set()
    topicos: list[Topico] = []
    for bruto in resposta.get("topicos", []):
        validos = []
        for i in bruto.get("indices", []):
            if isinstance(i, int) and 0 <= i < len(itens) and i not in usados:
                usados.add(i)
                validos.append(i)
        if not validos:
            continue
        topicos.append(
            Topico(
                titulo=(bruto.get("titulo") or "").strip() or itens[validos[0]].titulo,
                itens=tuple(itens[i] for i in validos),
                palavras_alvo=int(bruto.get("palavras_alvo") or 0),
            )
        )

    while topicos and sum(t.palavras_alvo for t in topicos) > orcamento:
        topicos.pop()

    mantidos = {id(it) for t in topicos for it in t.itens}
    fora = tuple(it for it in itens if id(it) not in mantidos)
    return Pauta(topicos=tuple(topicos), fora_do_audio=fora)
