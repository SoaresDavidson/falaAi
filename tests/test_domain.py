from falaai.domain import Fala, Roteiro


def test_roteiro_achata_falas_na_ordem():
    a, b, c, d = (
        Fala("dora", "oi"),
        Fala("alex", "um dois"),
        Fala("dora", "três"),
        Fala("alex", "tchau"),
    )
    r = Roteiro(abertura=(a,), blocos=((b,), (c,)), fechamento=(d,))
    assert r.falas() == [a, b, c, d]
    assert r.palavras() == 5
