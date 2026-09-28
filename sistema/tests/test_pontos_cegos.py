"""Pontos cegos de negócio encontrados na revisão antes de ir para o servidor."""
import pytest

from sistema import consultas, servicos
from sistema.regras import ErroDeNegocio


def _cobranca(contrato, competencia="2026-10"):
    return consultas.listar_cobrancas(competencia=competencia, contrato_id=contrato, hoje="2026-10-05")[0]


def test_boleto_pago_em_cobranca_cancelada_vira_pendencia_e_nao_se_perde(cenario):
    cb = _cobranca(cenario["contrato"])
    servicos.registrar_boleto("hermes", cb["id"], "Caixa", "NN-1")
    servicos.isentar_cobranca("paulo", cb["id"], "acordo")  # gera a pendência de cancelar o boleto no banco
    # O locatário paga assim mesmo, porque o banco não cancelou o boleto.
    r = servicos.registrar_pagamento_boleto("hermes", "NN-1", "2026-10-09", 150000)
    assert r["registrado"] is False and r["pendencia_id"]
    pend = [p for p in consultas.listar_pendencias() if p["tipo"] == "pagamento_sem_cobranca"]
    assert len(pend) == 1 and "isenta" in pend[0]["descricao"] and "NN-1" in pend[0]["descricao"]
    assert pend[0]["entidade"] == "cobranca" and pend[0]["entidade_id"] == cb["id"]
    # O Hermes repete a baixa no dia seguinte: continua uma pendência só.
    assert servicos.registrar_pagamento_boleto("hermes", "NN-1", "2026-10-09", 150000)["pendencia_id"] == pend[0]["id"]
    assert len([p for p in consultas.listar_pendencias() if p["tipo"] == "pagamento_sem_cobranca"]) == 1


def test_pagamento_do_boleto_antigo_apos_segunda_via(cenario):
    cb = _cobranca(cenario["contrato"])
    servicos.registrar_boleto("hermes", cb["id"], "Caixa", "NN-ANTIGO")
    servicos.registrar_boleto("hermes", cb["id"], "Caixa", "NN-NOVO", substituir=True)
    # O locatário pagou o boleto antigo, que continua válido no banco.
    r = servicos.registrar_pagamento_boleto("hermes", "NN-ANTIGO", "2026-10-09", 150000)
    assert r["registrado"] is True and r["cobranca_id"] == cb["id"] and r["pendencias"] == []
    assert _cobranca(cenario["contrato"])["situacao_calculada"] == "paga"
    assert servicos.registrar_pagamento_boleto("hermes", "NN-ANTIGO", "2026-10-09", 150000)["ja_existia"] is True
    # Boleto que nunca existiu continua sendo desconhecido.
    assert servicos.registrar_pagamento_boleto("hermes", "NN-QUALQUER", "2026-10-09", 1000)["registrado"] is False


def test_imovel_com_outra_grafia_e_recusado():
    servicos.cadastrar_imovel("t", "Anel Viário", "Apto 101", "Rua A")
    for grupo, unidade in [("Anel Viario", "Apto 101"), ("ANEL VIÁRIO", "apto 101"), (" anel  viario ", "Apto  101")]:
        with pytest.raises(ErroDeNegocio, match="Já existe o imóvel 'Anel Viário - Apto 101'"):
            servicos.cadastrar_imovel("t", grupo, unidade, "Rua B")
    outro = servicos.cadastrar_imovel("t", "Anel Viário", "Apto 102", "Rua A")
    with pytest.raises(ErroDeNegocio, match="Já existe"):
        servicos.atualizar_imovel("t", outro, unidade="apto 101")
    servicos.atualizar_imovel("t", outro, unidade="Apto 102", endereco="Rua C")  # o próprio nome não conta como repetido
    servicos.atualizar_imovel("t", outro, grupo="Anel Viario")


def test_busca_de_locatario_ignora_acento_e_maiuscula():
    servicos.cadastrar_locatario("t", "João Pereira da Silva", "11122233344", "j@x.com")
    servicos.cadastrar_locatario("t", "Construtora São José Ltda", "12345678000199", "c@x.com")
    assert [l["nome"] for l in consultas.buscar_locatarios("JOAO PEREIRA")] == ["João Pereira da Silva"]
    assert [l["nome"] for l in consultas.buscar_locatarios("sao jose")] == ["Construtora São José Ltda"]
    assert [l["nome"] for l in consultas.buscar_locatarios("11122233344")] == ["João Pereira da Silva"]
    assert [l["nome"] for l in consultas.buscar_locatarios("111.222")] == ["João Pereira da Silva"]
    assert consultas.buscar_locatarios("ninguém") == []
    assert len(consultas.buscar_locatarios("")) == 2


def test_texto_digitado_com_html_nao_roda_no_site(cliente):
    cliente.post("/locatarios/novo", data={"nome": "<script>alert(1)</script>", "cpf_cnpj": "12345678900",
                                           "email": "a@x.com"})
    r = cliente.get("/locatarios")
    assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
