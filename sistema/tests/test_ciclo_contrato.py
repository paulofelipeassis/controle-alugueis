"""Ciclo de vida do contrato: pontos cegos encontrados na revisão antes de ir para o servidor."""
import pytest

from sistema import consultas, db, servicos
from sistema.regras import ErroDeNegocio


def _cobrancas(contrato_id):
    return {c["competencia"]: c for c in consultas.listar_cobrancas(contrato_id=contrato_id, hoje="2026-11-15")}


def test_reajuste_depois_do_boleto_pede_conferencia(cenario):
    servicos.gerar_cobrancas("t", "2026-12-01")
    nov = _cobrancas(cenario["contrato"])["2026-11"]
    servicos.registrar_boleto("hermes", nov["id"], "Caixa", "NN-ANTIGO")
    r = servicos.registrar_reajuste("paulo", cenario["contrato"], 160000, "2026-10-20", "IGP-M")
    assert [p["tipo"] for p in r["pendencias"]] == ["boleto_valor_antigo"]
    assert "NN-ANTIGO" in r["pendencias"][0]["descricao"] and "R$ 1.600,00" in r["pendencias"][0]["descricao"]
    # A cobrança sem boleto (dezembro) foi atualizada sozinha; a com boleto ficou como estava.
    cobrancas = _cobrancas(cenario["contrato"])
    assert cobrancas["2026-11"]["valor_centavos"] == 150000 and cobrancas["2026-12"]["valor_centavos"] == 160000


def test_reajuste_sem_boleto_nao_gera_pendencia(cenario):
    assert servicos.registrar_reajuste("paulo", cenario["contrato"], 160000, "2026-12-01")["pendencias"] == []


def test_pagamento_antes_do_encerramento_nao_e_ruido(cenario):
    servicos.gerar_cobrancas("t", "2026-12-01")
    nov = _cobrancas(cenario["contrato"])["2026-11"]
    # O locatário avisou que sai em 30/11 e o encerramento foi registrado com antecedência.
    servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-30", "aviso prévio")
    r = servicos.registrar_pagamento("hermes", nov["id"], "2026-11-09", 150000, "pix")
    assert r["pendencias"] == []


def test_pagamento_depois_do_encerramento_avisa(cenario):
    servicos.gerar_cobrancas("t", "2026-11-01")
    out = _cobrancas(cenario["contrato"])["2026-10"]
    servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-10-31", "saída")
    r = servicos.registrar_pagamento("hermes", out["id"], "2026-11-20", 150000, "pix")
    assert "contrato_encerrado" in [p["tipo"] for p in r["pendencias"]]


def test_reabrir_contrato_encerrado_por_engano(cenario):
    servicos.gerar_cobrancas("t", "2027-01-15")
    dez = _cobrancas(cenario["contrato"])["2026-12"]
    servicos.registrar_boleto("hermes", dez["id"], "Caixa", "NN-DEZ")
    r = servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-30", "engano")
    assert r["cobrancas_canceladas"] == 3 and consultas.listar_imoveis()[0]["situacao"] == "vago"

    r = servicos.reabrir_contrato("paulo", cenario["contrato"], "encerrado com o contrato errado")
    assert r["cobrancas_restauradas"] == 3
    assert [p["tipo"] for p in r["pendencias"]] == ["reemitir_boleto"]
    assert consultas.listar_imoveis(hoje="2026-10-10")[0]["situacao"] == "alugado"
    cobrancas = _cobrancas(cenario["contrato"])
    assert cobrancas["2026-12"]["situacao"] == "normal" and cobrancas["2027-01"]["situacao"] == "normal"
    with db.leitura() as con:
        assert con.execute("SELECT COUNT(*) FROM auditoria WHERE acao = 'reabrir_contrato'").fetchone()[0] == 1
    with pytest.raises(ErroDeNegocio, match="não está encerrado"):
        servicos.reabrir_contrato("paulo", cenario["contrato"], "de novo")


def test_nao_reabre_se_o_imovel_ja_tem_outro_contrato(cenario):
    servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-10-31", "saída")
    outro = servicos.cadastrar_locatario("t", "João", "98765432100", "j@x.com")
    servicos.criar_contrato("t", cenario["imovel"], outro, "2026-11-01", "2027-11-01", 5, 100000)
    with pytest.raises(ErroDeNegocio, match="outro contrato ativo"):
        servicos.reabrir_contrato("paulo", cenario["contrato"], "engano")


def test_corrigir_data_de_fim(cenario):
    servicos.atualizar_contrato("paulo", cenario["contrato"], data_fim_prevista="2027-06-30")  # encurtar é permitido
    assert consultas.extrato_contrato(cenario["contrato"])["data_fim_prevista"] == "2027-06-30"
    with pytest.raises(ErroDeNegocio, match="depois da data de início"):
        servicos.atualizar_contrato("paulo", cenario["contrato"], data_fim_prevista="2026-10-05")
    with pytest.raises(ErroDeNegocio, match="não pode ser alterado"):
        servicos.atualizar_contrato("paulo", cenario["contrato"], dia_vencimento=20)
    servicos.atualizar_contrato("paulo", cenario["contrato"], data_fim_prevista=None, observacoes="ok")  # sem data: ignora
