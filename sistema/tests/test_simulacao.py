"""15 meses de operação fictícia (scripts/simular.py): todas as conferências mensais têm que bater."""
from scripts.simular import Simulacao


def test_quinze_meses_de_operacao():
    sim = Simulacao()
    resumo = sim.rodar()
    assert len(resumo) == 15
    assert sim.boletos_emitidos > 250 and sim.baixas_repetidas > 0
    assert sim.violacoes == []
