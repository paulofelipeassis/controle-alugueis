import pytest

from sistema import consultas, db, servicos
from sistema.regras import ErroDeNegocio


def _cobrancas(contrato_id):
    with db.leitura() as con:
        return [dict(c) for c in con.execute(
            "SELECT * FROM cobrancas WHERE contrato_id = ? ORDER BY competencia", (contrato_id,))]


def test_primeira_cobranca(cenario):
    servicos.gerar_cobrancas("t", "2026-10-01")
    primeira = _cobrancas(cenario["contrato"])[0]
    assert (primeira["competencia"], primeira["vencimento"], primeira["valor_centavos"]) == \
        ("2026-10", "2026-10-10", 150000)


def test_gera_ate_30_dias_e_nao_duplica(cenario):
    servicos.gerar_cobrancas("t", "2027-01-15")
    servicos.gerar_cobrancas("t", "2027-01-15")
    assert [c["competencia"] for c in _cobrancas(cenario["contrato"])] == \
        ["2026-10", "2026-11", "2026-12", "2027-01", "2027-02"]


def test_vencimento_dia_31():
    imovel = servicos.cadastrar_imovel("t", "G", "U", "E")
    loc = servicos.cadastrar_locatario("t", "N", "12345678900", "n@x.com")
    contrato = servicos.criar_contrato("t", imovel, loc, "2026-10-01", "2027-10-01", 31, 100000)
    servicos.gerar_cobrancas("t", "2026-11-15")
    assert [c["vencimento"] for c in _cobrancas(contrato)] == ["2026-10-31", "2026-11-30"]


def test_nada_antes_do_inicio_das_cobrancas():
    imovel = servicos.cadastrar_imovel("t", "G", "U", "E")
    loc = servicos.cadastrar_locatario("t", "N", "12345678900", "n@x.com")
    contrato = servicos.criar_contrato("t", imovel, loc, "2025-03-01", "2027-03-01", 5, 100000)
    servicos.gerar_cobrancas("t", "2026-10-01")
    assert [c["competencia"] for c in _cobrancas(contrato)] == ["2026-10"]


def test_reajuste_atualiza_so_cobrancas_intocadas(cenario):
    servicos.gerar_cobrancas("t", "2026-12-01")  # out, nov, dez
    out, nov, dez = _cobrancas(cenario["contrato"])
    servicos.registrar_boleto("t", nov["id"], "Caixa", "NN-NOV")
    servicos.registrar_reajuste("t", cenario["contrato"], 160000, "2026-11-01")
    valores = {c["competencia"]: c["valor_centavos"] for c in _cobrancas(cenario["contrato"])}
    assert valores == {"2026-10": 150000, "2026-11": 150000, "2026-12": 160000}


def test_encerramento(cenario):
    servicos.gerar_cobrancas("t", "2026-12-01")
    out, nov, dez = _cobrancas(cenario["contrato"])
    servicos.registrar_boleto("t", dez["id"], "Caixa", "NN-DEZ")
    resultado = servicos.encerrar_contrato("t", cenario["contrato"], "2026-11-15", "saída")
    situacoes = {c["competencia"]: c["situacao"] for c in _cobrancas(cenario["contrato"])}
    assert situacoes == {"2026-10": "normal", "2026-11": "normal", "2026-12": "cancelada"}
    assert resultado["pendencias"][0]["tipo"] == "cancelar_boleto"
    assert "NN-DEZ" in consultas.listar_pendencias()[0]["descricao"]
    # Dívidas anteriores continuam cobradas.
    devedores = consultas.inadimplentes(hoje="2026-12-20")
    assert [c["competencia"] for c in devedores[0]["cobrancas"]] == ["2026-10", "2026-11"]
    # Contrato encerrado não gera mais nada.
    servicos.gerar_cobrancas("t", "2027-06-01")
    assert len(_cobrancas(cenario["contrato"])) == 3


def test_editar_isentar_cancelar(cenario):
    servicos.gerar_cobrancas("t", "2026-11-01")
    out, nov = _cobrancas(cenario["contrato"])
    servicos.editar_valor_cobranca("t", out["id"], 120000, "primeiro mês proporcional")
    assert _cobrancas(cenario["contrato"])[0]["valor_centavos"] == 120000
    with pytest.raises(ErroDeNegocio, match="motivo"):
        servicos.isentar_cobranca("t", nov["id"], "")
    servicos.registrar_boleto("t", nov["id"], "Caixa", "NN-1")
    pendencia = servicos.isentar_cobranca("t", nov["id"], "acordo")
    assert pendencia["tipo"] == "cancelar_boleto"
    servicos.registrar_pagamento("t", out["id"], "2026-10-10", 120000, "pix")
    with pytest.raises(ErroDeNegocio, match="já tem pagamento"):
        servicos.cancelar_cobranca("t", out["id"], "erro")


def test_boleto(cenario):
    servicos.gerar_cobrancas("t", "2026-11-01")
    out, nov = _cobrancas(cenario["contrato"])
    assert servicos.registrar_boleto("t", out["id"], "Caixa", "NN-1", "1234 5678", "http://pdf")["ja_existia"] is False
    # Repetir o mesmo boleto não é erro (o Hermes pode repetir).
    assert servicos.registrar_boleto("t", out["id"], "Caixa", "NN-1")["ja_existia"] is True
    with pytest.raises(ErroDeNegocio, match="segunda via"):
        servicos.registrar_boleto("t", out["id"], "Caixa", "NN-2")
    servicos.registrar_boleto("t", out["id"], "Caixa", "NN-2", substituir=True)
    with pytest.raises(ErroDeNegocio, match="outra cobrança"):
        servicos.registrar_boleto("t", nov["id"], "Caixa", "NN-2")
    servicos.marcar_boleto_enviado("t", out["id"])
    assert _cobrancas(cenario["contrato"])[0]["boleto_enviado_em"]
