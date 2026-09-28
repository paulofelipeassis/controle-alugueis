"""Testes do módulo opcional proporcional (primeiro período de contrato que começa no meio do mês)."""
import pytest

from sistema import config, consultas, db, servicos
from sistema.modulos import proporcional
from sistema.modulos.proporcional import mcp as ferramentas
from sistema.regras import ErroDeNegocio

_n = iter(range(20_000_000_000, 90_000_000_000))


def _contrato(inicio, dia=10, valor=150000):
    n = next(_n)
    imovel = servicos.cadastrar_imovel("t", "G", f"U{n}", "E")
    loc = servicos.cadastrar_locatario("t", f"N{n}", str(n), "n@x.com")
    return servicos.criar_contrato("t", imovel, loc, inicio, "2030-12-31", dia, valor)


def _primeira(contrato, hoje="2026-11-15"):
    return consultas.listar_cobrancas(contrato_id=contrato, hoje=hoje)[0]


def test_comeca_antes_do_vencimento_a_primeira_cobranca_e_do_proprio_mes(cenario):
    # Cenário: começa em 05/10/2026, vence dia 10 -> primeira cobrança 10/10, com 27 dos 31 dias de outubro.
    s = proporcional.sugerir(cenario["contrato"])
    assert (s["competencia"], s["vencimento"], s["dias"], s["dias_do_mes"]) == ("2026-10", "2026-10-10", 27, 31)
    assert (s["valor_cheio"], s["valor_sugerido"], s["mes_do_inicio"]) == ("R$ 1.500,00", "R$ 1.306,45", "2026-10")


def test_comeca_depois_do_vencimento_a_primeira_cobranca_e_do_mes_seguinte():
    contrato = _contrato("2026-10-15")  # vence dia 10: a primeira cobrança é a de 10/11
    assert proporcional.sugerir(contrato) is None  # em 27/09 ela ainda não existe (o sistema gera 30 dias à frente)
    s = proporcional.sugerir(contrato, hoje="2026-10-20")
    assert (s["competencia"], s["vencimento"], s["dias"], s["mes_do_inicio"]) == ("2026-11", "2026-11-10", 17, "2026-10")
    assert s["valor_sugerido_centavos"] == 82258  # 1.500,00 × 17/31


@pytest.mark.parametrize("inicio", ["2026-11-01", "2026-09-15"])  # dia 1 (mês inteiro) / mês do sistema antigo
def test_nao_se_aplica(inicio):
    assert proporcional.sugerir(_contrato(inicio)) is None


def test_contrato_encerrado_ou_inexistente_nao_se_aplica(cenario):
    assert proporcional.sugerir(999) is None
    servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-10-30", "saiu")
    assert proporcional.sugerir(cenario["contrato"]) is None


def test_some_quando_a_cobranca_deixa_de_estar_intocada(cenario):
    primeira = _primeira(cenario["contrato"])
    servicos.registrar_boleto("hermes", primeira["id"], "Caixa", "NN-1")
    assert proporcional.sugerir(cenario["contrato"]) is None  # boleto já emitido

    outro = _contrato("2026-10-15")
    servicos.editar_valor_cobranca("paulo", _primeira(outro)["id"], 90000, "acordo")
    assert proporcional.sugerir(outro) is None  # alguém já ajustou o valor

    terceiro = _contrato("2026-10-20")
    servicos.registrar_pagamento("paulo", _primeira(terceiro)["id"], "2026-11-09", 150000, "pix")
    assert proporcional.sugerir(terceiro) is None  # já foi pago


def test_aplicar_o_proporcional(cenario):
    r = proporcional.decidir("paulo", cenario["contrato"], True)
    assert r["decisao"] == "proporcional" and r["valor_centavos"] == 130645
    primeira = _primeira(cenario["contrato"])
    assert primeira["valor_centavos"] == 130645
    assert "primeiro período proporcional: 27 de 31 dias de 2026-10" in consultas.auditoria("cobranca", primeira["id"])[0]["detalhes"]
    assert proporcional.sugerir(cenario["contrato"]) is None
    assert not [a for a in consultas.alertas() if a["tipo"] == "primeiro_periodo_proporcional"]
    with pytest.raises(ErroDeNegocio, match="não tem primeiro período a decidir"):
        proporcional.decidir("paulo", cenario["contrato"], False)


def test_manter_o_aluguel_cheio_silencia_o_aviso(cenario):
    r = proporcional.decidir("paulo", cenario["contrato"], False)
    assert r["decisao"] == "cheio" and _primeira(cenario["contrato"])["valor_centavos"] == 150000
    assert proporcional.sugerir(cenario["contrato"]) is None and proporcional.pendentes() == []


def test_alerta_no_painel_enquanto_ninguem_decide(cenario):
    [aviso] = [a for a in consultas.alertas() if a["tipo"] == "primeiro_periodo_proporcional"]
    assert aviso["contrato_id"] == cenario["contrato"]
    assert "começou em 05/10" in aviso["mensagem"] and "(vence 10/10)" in aviso["mensagem"]
    assert "27 de 31 dias" in aviso["mensagem"] and "R$ 1.306,45" in aviso["mensagem"]


def test_ferramentas_do_hermes(cenario):
    dados = ferramentas.sugerir_primeiro_periodo(cenario["contrato"])
    assert dados["aplicavel"] is True and dados["valor_sugerido"] == "R$ 1.306,45"
    assert ferramentas.decidir_primeiro_periodo(cenario["contrato"], True)["decisao"] == "proporcional"
    assert ferramentas.sugerir_primeiro_periodo(cenario["contrato"]) == {"aplicavel": False}


def test_apagar_contrato_apaga_a_decisao(cenario):
    proporcional.decidir("paulo", cenario["contrato"], False)
    servicos.apagar_contrato("paulo", cenario["contrato"])
    with db.leitura() as con:
        assert con.execute("SELECT COUNT(*) FROM primeiro_periodo").fetchone()[0] == 0


def test_uma_geracao_so_para_todos_os_contratos(monkeypatch):
    for dia in (12, 15, 20):
        _contrato(f"2026-10-{dia}")
    chamadas = []
    original = servicos.gerar_cobrancas
    monkeypatch.setattr(servicos, "gerar_cobrancas", lambda *a, **k: chamadas.append(1) or original(*a, **k))
    assert len(proporcional.pendentes(hoje="2026-10-20")) == 3 and len(chamadas) == 1


def test_pagina_do_contrato_e_decisao_pela_web(cliente, cenario):
    pagina = cliente.get(f"/contratos/{cenario['contrato']}").text
    assert "Primeira cobrança: aluguel cheio ou proporcional?" in pagina and "Usar R$ 1.306,45" in pagina
    r = cliente.post(f"/contratos/{cenario['contrato']}/primeiro-periodo", data={})
    assert "Escolha o valor proporcional" in r.text
    r = cliente.post(f"/contratos/{cenario['contrato']}/primeiro-periodo", data={"escolha": "proporcional"})
    assert "Valor proporcional aplicado na primeira cobrança" in r.text
    assert "Primeira cobrança: aluguel cheio ou proporcional?" not in r.text
    assert _primeira(cenario["contrato"])["valor_centavos"] == 130645
    r = cliente.post(f"/contratos/{cenario['contrato']}/primeiro-periodo", data={"escolha": "cheio"})
    assert "não tem primeiro período a decidir" in r.text


def test_inicio_das_cobrancas_muda_quem_recebe_a_pergunta(monkeypatch, cenario):
    monkeypatch.setattr(config, "INICIO_COBRANCAS", "2026-11")  # o mês do início (outubro) já era do sistema antigo
    assert proporcional.sugerir(cenario["contrato"]) is None
