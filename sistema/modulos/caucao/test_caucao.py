"""Testes do módulo opcional caução."""
import pytest

from sistema import consultas, db, servicos
from sistema.modulos import caucao
from sistema.regras import ErroDeNegocio


@pytest.fixture
def com_caucao(cenario):
    """O contrato do cenário (aluguel R$ 1.500,00), agora com caução de R$ 3.000,00 (2 aluguéis)."""
    servicos.atualizar_contrato("t", cenario["contrato"], garantia_tipo="caucao", garantia_valor_centavos=300000)
    return cenario["contrato"]


def _encerrar(contrato):
    servicos.encerrar_contrato("paulo", contrato, "2026-11-15", "saiu", cobrar_ate_a_saida=False)


def test_contrato_sem_caucao_nao_participa(cenario):
    assert caucao.situacao(cenario["contrato"]) is None
    _encerrar(cenario["contrato"])
    assert caucao.a_devolver() == [] and caucao.situacao(999) is None
    with pytest.raises(ErroDeNegocio, match="não tem caução"):
        caucao.registrar_devolucao("paulo", cenario["contrato"], "2026-12-01", 0)


def test_caucao_retida_enquanto_o_contrato_esta_ativo(com_caucao):
    s = caucao.situacao(com_caucao)
    assert (s["estado"], s["valor"], s["limite"], s["excede_limite"]) == ("retida", "R$ 3.000,00", "R$ 4.500,00", False)
    assert caucao.a_devolver() == []
    with pytest.raises(ErroDeNegocio, match="só é devolvida depois de encerrar"):
        caucao.registrar_devolucao("paulo", com_caucao, "2026-12-01", 300000)


def test_caucao_acima_de_tres_alugueis_avisa(cenario):
    servicos.atualizar_contrato("t", cenario["contrato"], garantia_tipo="caucao", garantia_valor_centavos=500000)
    assert caucao.situacao(cenario["contrato"])["excede_limite"] is True  # 5.000 > 3 × 1.500


def test_encerrado_sem_devolucao_gera_alerta(com_caucao):
    _encerrar(com_caucao)
    assert caucao.situacao(com_caucao, hoje="2026-11-27")["estado"] == "a_devolver"
    [aviso] = [a for a in consultas.alertas(hoje="2026-11-27") if a["tipo"] == "caucao_a_devolver"]
    assert aviso["contrato_id"] == com_caucao
    assert "caução de R$ 3.000,00" in aviso["mensagem"] and "15/11/2026" in aviso["mensagem"]
    assert "há 12 dias" in aviso["mensagem"] and "Maria Souza" in aviso["mensagem"]


def test_registrar_devolucao_com_rendimento_e_descontos(com_caucao):
    _encerrar(com_caucao)
    caucao.registrar_devolucao("paulo", com_caucao, "2026-12-01", 250000, 50000, "pintura da sala", "PIX")
    s = caucao.situacao(com_caucao)
    assert s["estado"] == "devolvida" and s["devolucao"]["valor_devolvido"] == "R$ 2.500,00"
    assert s["devolucao"]["descontos"] == "R$ 500,00" and s["devolucao"]["motivo_descontos"] == "pintura da sala"
    assert caucao.a_devolver() == [] and not [a for a in consultas.alertas() if a["tipo"] == "caucao_a_devolver"]
    acoes = [a["acao"] for a in consultas.auditoria("contrato", com_caucao)]
    assert "devolver_caucao" in acoes
    with pytest.raises(ErroDeNegocio, match="já foi registrada"):
        caucao.registrar_devolucao("paulo", com_caucao, "2026-12-02", 300000)


def test_devolucao_com_rendimento_da_poupanca_pode_passar_da_caucao(com_caucao):
    _encerrar(com_caucao)
    caucao.registrar_devolucao("paulo", com_caucao, "2026-12-01", 301250)  # R$ 12,50 de rendimento
    assert caucao.situacao(com_caucao)["devolucao"]["valor_devolvido"] == "R$ 3.012,50"


@pytest.mark.parametrize("devolvido, descontos, motivo, erro", [
    (250000, 50000, None, "motivo dos descontos"),   # descontou sem dizer por quê
    (250000, 0, None, "menor que a caução"),          # faltou dinheiro sem explicação
    (30000, 0, None, "menor que a caução"),           # erro de digitação: 300,00 em vez de 3.000,00
    (-1, 0, None, "negativos"),
])
def test_devolucao_que_nao_fecha_e_recusada(com_caucao, devolvido, descontos, motivo, erro):
    _encerrar(com_caucao)
    with pytest.raises(ErroDeNegocio, match=erro):
        caucao.registrar_devolucao("paulo", com_caucao, "2026-12-01", devolvido, descontos, motivo)
    assert caucao.situacao(com_caucao)["estado"] == "a_devolver"  # nada foi gravado


def test_devolver_tudo_como_desconto(com_caucao):
    _encerrar(com_caucao)
    caucao.registrar_devolucao("paulo", com_caucao, "2026-12-01", 0, 300000, "aluguéis em aberto e reformas")
    assert caucao.situacao(com_caucao)["devolucao"]["valor_devolvido"] == "R$ 0,00"


def test_apagar_contrato_apaga_o_registro_da_caucao(com_caucao):
    _encerrar(com_caucao)
    caucao.registrar_devolucao("paulo", com_caucao, "2026-12-01", 300000)
    servicos.apagar_contrato("paulo", com_caucao)  # o núcleo não sabe que o módulo existe
    with db.leitura() as con:
        assert con.execute("SELECT COUNT(*) FROM caucoes").fetchone()[0] == 0


def test_pagina_do_contrato_e_devolucao_pela_web(cliente, com_caucao):
    pagina = cliente.get(f"/contratos/{com_caucao}").text
    assert "em posse do locador" in pagina and "art. 38" in pagina
    _encerrar(com_caucao)
    pagina = cliente.get(f"/contratos/{com_caucao}").text
    assert "aguardando devolução" in pagina and "Registrar devolução da caução" in pagina
    r = cliente.post(f"/contratos/{com_caucao}/caucao", data={
        "data_devolucao": "2026-12-01", "valor_devolvido": "2.700,00", "descontos": "300,00",
        "motivo_descontos": "pintura", "observacao": ""})
    assert "Devolução da caução registrada" in r.text and "devolvida em 01/12/2026" in r.text
    assert "com descontos de R$ 300,00 (pintura)" in r.text
    r = cliente.post(f"/contratos/{com_caucao}/caucao", data={"data_devolucao": "2026-12-02", "valor_devolvido": "3.000,00"})
    assert "já foi registrada" in r.text
    assert "aguardando devolução" not in cliente.get("/").text  # o aviso saiu do painel
