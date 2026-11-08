from falaai.roteiro.pauta import montar_pauta
from tests.fakes import FakeLlm, item


def test_indices_invalidos_ignorados():
    itens = [item("a"), item("b"), item("c")]
    llm = FakeLlm(
        [
            {
                "topicos": [
                    {"titulo": "X", "indices": [0, 0, 7], "palavras_alvo": 100},
                    {"titulo": "Y", "indices": [9], "palavras_alvo": 100},
                ]
            }
        ]
    )
    pauta = montar_pauta(llm, itens, 2250)
    assert len(pauta.topicos) == 1
    assert pauta.topicos[0].itens == (itens[0],)
    assert pauta.fora_do_audio == (itens[1], itens[2])


def test_corta_topicos_acima_do_orcamento():
    itens = [item("a"), item("b"), item("c")]
    llm = FakeLlm(
        [
            {
                "topicos": [
                    {"titulo": "X", "indices": [0], "palavras_alvo": 500},
                    {"titulo": "Y", "indices": [1], "palavras_alvo": 300},
                    {"titulo": "Z", "indices": [2], "palavras_alvo": 200},
                ]
            }
        ]
    )
    pauta = montar_pauta(llm, itens, 1000)
    assert [t.titulo for t in pauta.topicos] == ["X", "Y"]
    assert pauta.fora_do_audio == (itens[2],)
