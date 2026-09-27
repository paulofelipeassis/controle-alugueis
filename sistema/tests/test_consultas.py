from pathlib import Path

import pytest

from sistema import config, consultas, servicos
from sistema.regras import ErroDeNegocio


def test_atraso_antigo_aparece_em_inadimplentes(cenario):
    """Erro da versão antiga: só olhava atrasos do mês atual."""
    servicos.gerar_cobrancas("t", "2027-01-15")
    devedores = consultas.inadimplentes(hoje="2027-01-15")
    assert len(devedores) == 1
    assert [c["competencia"] for c in devedores[0]["cobrancas"]] == ["2026-10", "2026-11", "2026-12", "2027-01"]
    assert devedores[0]["saldo_centavos"] == 600000
    assert devedores[0]["valor_atualizado_centavos"] > 600000


def test_painel(cenario):
    servicos.cadastrar_imovel("t", "Centro", "Sala 1", "Rua C")
    painel = consultas.painel(hoje="2026-10-05")
    assert (painel["imoveis_total"], painel["imoveis_alugados"], painel["imoveis_vagos"]) == (2, 1, 1)
    assert painel["ocupacao_pct"] == 50
    assert painel["resumo_do_mes"]["devido"] == "R$ 1.500,00"
    assert "sem_boleto" in [a["tipo"] for a in painel["alertas"]]


def test_alertas(cenario):
    tipos = {a["tipo"] for a in consultas.alertas(hoje="2027-09-20")}
    assert {"contrato_a_vencer", "reajuste"} <= tipos
    tipos = {a["tipo"] for a in consultas.alertas(hoje="2027-10-20")}
    assert "prazo_vencido" in tipos


def test_contrato_com_prazo_vencido_continua_cobrando(cenario):
    servicos.gerar_cobrancas("t", "2027-12-01")
    extrato = consultas.extrato_contrato(cenario["contrato"], hoje="2027-12-01")
    assert extrato["prazo_vencido"] and extrato["status"] == "ativo"
    assert extrato["cobrancas"][-1]["competencia"] == "2027-12"


def test_fichas_e_extrato(cenario):
    servicos.gerar_cobrancas("t", "2026-11-15")
    cobranca = consultas.listar_cobrancas(competencia="2026-10", hoje="2026-11-15")[0]
    servicos.registrar_pagamento("t", cobranca["id"], "2026-10-10", 150000, "pix")
    extrato = consultas.extrato_contrato(cenario["contrato"], hoje="2026-11-15")
    assert extrato["cobrancas"][0]["situacao_calculada"] == "paga"
    assert extrato["cobrancas"][0]["pagamentos"][0]["valor"] == "R$ 1.500,00"
    assert extrato["cobrancas"][1]["situacao_calculada"] == "atrasada"
    ficha = consultas.ficha_locatario(cenario["locatario"], hoje="2026-11-15")
    assert ficha["total_atrasado_centavos"] == 150000
    assert ficha["contratos"][0]["imovel_nome"] == "Anel Viário - Apto 101"
    imovel = consultas.ficha_imovel(cenario["imovel"])
    assert imovel["contrato_atual"]["locatario_nome"] == "Maria Souza"


def test_busca_e_historico(cenario):
    assert consultas.buscar_locatarios("maria")[0]["id"] == cenario["locatario"]
    assert consultas.buscar_locatarios("456.789")[0]["id"] == cenario["locatario"]
    assert consultas.buscar_locatarios("ninguém") == []
    servicos.gerar_cobrancas("t", "2026-10-01")
    cobranca = consultas.listar_cobrancas(competencia="2026-10", hoje="2026-10-01")[0]
    servicos.registrar_pagamento("t", cobranca["id"], "2026-10-10", 150000, "pix")
    historico = consultas.historico_pagamentos(data_de="2026-10-01", data_ate="2026-10-31", grupo="Anel Viário")
    assert historico["total"] == "R$ 1.500,00"
    assert consultas.historico_pagamentos(data_de="2026-11-01")["quantidade"] == 0


def test_pasta_documento(cenario):
    assert servicos.pasta_documento("imovel", cenario["imovel"]) == "imoveis/Anel Viario - Apto 101/imovel"
    assert servicos.pasta_documento("locatario", cenario["locatario"]) == "locatarios/12345678900 - Maria Souza"
    assert servicos.pasta_documento("contrato", cenario["contrato"]) == \
        "imoveis/Anel Viario - Apto 101/contratos/2026-10 - Maria Souza"


def test_documentos(cenario):
    doc = servicos.salvar_documento("t", "contrato", cenario["contrato"], "contrato-assinado", "scan.PDF", b"%PDF")
    doc2 = servicos.salvar_documento("t", "contrato", cenario["contrato"], "contrato-assinado", "scan.pdf", b"%PDF")
    caminhos = [d["caminho"] for d in consultas.extrato_contrato(cenario["contrato"])["documentos"]]
    assert caminhos == ["imoveis/Anel Viario - Apto 101/contratos/2026-10 - Maria Souza/contrato-assinado.pdf",
                        "imoveis/Anel Viario - Apto 101/contratos/2026-10 - Maria Souza/contrato-assinado-2.pdf"]
    # Registrar de novo o mesmo arquivo devolve o mesmo documento.
    assert servicos.registrar_documento("hermes", "contrato", cenario["contrato"], "contrato-assinado",
                                        caminhos[0]) == doc
    assert doc != doc2
    with pytest.raises(ErroDeNegocio, match="inválido"):
        servicos.registrar_documento("hermes", "contrato", cenario["contrato"], "x", "../../etc/passwd")
    with pytest.raises(ErroDeNegocio, match="dentro da pasta"):
        servicos.registrar_documento("hermes", "contrato", cenario["contrato"], "x", "/etc/passwd")
    # Caminho absoluto dentro da pasta de documentos é aceito.
    absoluto = str(Path(config.DOCS_DIR).resolve() / caminhos[0])
    assert servicos.registrar_documento("hermes", "contrato", cenario["contrato"], "x", absoluto) == doc


def test_erro_de_entidade_inexistente():
    with pytest.raises(ErroDeNegocio, match="não encontrado"):
        consultas.extrato_contrato(999)
