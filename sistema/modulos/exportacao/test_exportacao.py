"""Testes do módulo opcional exportação (planilhas CSV)."""
import csv
import io

import pytest
from fastapi.testclient import TestClient

from sistema import consultas, servicos
from sistema.modulos import exportacao
from sistema.regras import ErroDeNegocio
from sistema.web import app


def _linhas(texto):
    assert texto.startswith("﻿")  # o Excel precisa disto para abrir os acentos
    return list(csv.reader(io.StringIO(texto[1:]), delimiter=";"))


@pytest.fixture
def dados(cenario):
    """Maria (R$ 1.500,00) paga out e nov de 2026; um pagamento dela é cancelado; outro locatário, com nome
    malicioso e CPF começando em zero, paga em 2026 e 2027."""
    servicos.gerar_cobrancas("t", "2027-02-01")
    maria = {c["competencia"]: c["id"] for c in consultas.listar_cobrancas(contrato_id=cenario["contrato"], hoje="2027-02-01")}
    servicos.registrar_pagamento("paulo", maria["2026-10"], "2026-10-09", 150000, "pix", identificador_externo="E2E-1")
    servicos.registrar_pagamento("hermes", maria["2026-11"], "2026-11-10", 150000, "boleto", identificador_externo="NN1")
    errado = servicos.registrar_pagamento("paulo", maria["2026-12"], "2026-12-05", 150000, "pix")
    servicos.cancelar_pagamento("paulo", errado["pagamento_id"], "lançado no contrato errado; era de outro")

    imovel2 = servicos.cadastrar_imovel("t", "Centro", "Sala 1", "Rua B")
    loc2 = servicos.cadastrar_locatario("t", "=HYPERLINK(\"http://x\")", "01234567890", "x@x.com")
    contrato2 = servicos.criar_contrato("t", imovel2, loc2, "2026-10-01", "2029-10-01", 5, 220000)
    outro = {c["competencia"]: c["id"] for c in consultas.listar_cobrancas(contrato_id=contrato2, hoje="2027-02-01")}
    servicos.registrar_pagamento("paulo", outro["2026-10"], "2026-10-04", 220000, "pix")
    servicos.registrar_pagamento("paulo", outro["2027-01"], "2027-01-05", 220000, "pix")
    return {"maria": cenario["locatario"], "contrato2": contrato2}


def test_formatos():
    assert exportacao.reais(150000) == "1500,00" and exportacao.reais(5) == "0,05" and exportacao.reais(0) == "0,00"
    assert exportacao.reais(-1234) == "-12,34" and exportacao.reais(None) == ""
    assert exportacao.cpf_cnpj("01234567890") == "012.345.678-90"
    assert exportacao.cpf_cnpj("12345678000199") == "12.345.678/0001-99"
    assert [exportacao.seguro(t) for t in ("=1+1", "+1", "-1", "@a", "Ana", "", None)] == ["'=1+1", "'+1", "'-1", "'@a", "Ana", "", ""]


def test_pagamentos_csv(dados):
    linhas = _linhas(exportacao.pagamentos_csv())
    assert linhas[0][:6] == ["Data do pagamento", "Mês da cobrança", "Imóvel", "Locatário", "CPF/CNPJ", "Valor pago"]
    assert len(linhas) == 5  # cabeçalho + 4 pagamentos válidos (o cancelado fica de fora)
    assert linhas[1][:6] == ["05/01/2027", "01/2027", "Centro - Sala 1", "'=HYPERLINK(\"http://x\")", "012.345.678-90", "2200,00"]
    assert [l[0] for l in linhas[1:]] == ["05/01/2027", "10/11/2026", "09/10/2026", "04/10/2026"]  # mais recente primeiro
    nov = [l for l in linhas if l[0] == "10/11/2026"][0]
    assert nov[5:10] == ["1500,00", "boleto", "NN1", "hermes", "Válido"]


def test_pagamentos_csv_com_filtros_e_cancelados(dados):
    so_2027 = _linhas(exportacao.pagamentos_csv(data_de="2027-01-01"))
    assert [l[0] for l in so_2027[1:]] == ["05/01/2027"]
    da_maria = _linhas(exportacao.pagamentos_csv(locatario_id=dados["maria"]))
    assert {l[3] for l in da_maria[1:]} == {"Maria Souza"}
    todos = _linhas(exportacao.pagamentos_csv(incluir_cancelados=True))
    cancelado = [l for l in todos if l[9] == "Cancelado"][0]
    assert cancelado[0] == "05/12/2026" and cancelado[10] == "lançado no contrato errado; era de outro"
    assert len(_linhas(exportacao.pagamentos_csv(grupo="Centro"))) == 3


def test_recebimentos_do_ano(dados):
    linhas = _linhas(exportacao.recebimentos_do_ano_csv(2026))
    assert linhas[0] == ["Locatário", "CPF/CNPJ", "Imóvel", "Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set",
                         "Out", "Nov", "Dez", "Total 2026"]
    por_nome = {l[0]: l for l in linhas[1:]}
    maria = por_nome["Maria Souza"]
    assert maria[1:3] == ["123.456.789-00", "Anel Viário - Apto 101"]
    assert maria[3:15] == ["", "", "", "", "", "", "", "", "", "1500,00", "1500,00", ""]  # dezembro cancelado não conta
    assert maria[15] == "3000,00"
    outro = por_nome["'=HYPERLINK(\"http://x\")"]
    assert outro[12] == "2200,00" and outro[15] == "2200,00"  # só outubro em 2026; janeiro de 2027 fica de fora
    total = por_nome["TOTAL"]
    assert total[12] == "3700,00" and total[13] == "1500,00" and total[15] == "5200,00"
    assert _linhas(exportacao.recebimentos_do_ano_csv("2027"))[-1][3] == "2200,00"  # janeiro/2027


def test_ano_invalido():
    for ruim in ("abc", "", "1999", "2101", None):
        with pytest.raises(ErroDeNegocio, match="Ano inválido"):
            exportacao.recebimentos_do_ano_csv(ruim)


def test_ano_sem_pagamentos_tem_so_o_total_zerado():
    linhas = _linhas(exportacao.recebimentos_do_ano_csv(2030))
    assert len(linhas) == 2 and linhas[1][0] == "TOTAL" and linhas[1][15] == "0,00"


def test_downloads_pela_web(cliente, dados):
    r = cliente.get("/exportar/pagamentos.csv?data_de=2026-11-01&data_ate=&grupo=&locatario_id=&cancelados=")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="pagamentos.csv"'
    assert len(_linhas(r.content.decode("utf-8"))) == 3  # cabeçalho + nov/2026 + jan/2027
    r = cliente.get("/exportar/recebimentos.csv?ano=2026")
    assert r.headers["content-disposition"] == 'attachment; filename="recebimentos-2026.csv"'
    assert "Total 2026" in r.content.decode("utf-8")
    assert "Ano inválido" in cliente.get("/exportar/recebimentos.csv?ano=abc").text


def test_downloads_exigem_login(dados):
    c = TestClient(app)
    for url in ("/exportar/pagamentos.csv", "/exportar/recebimentos.csv?ano=2026"):
        r = c.get(url, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login"


def test_botoes_no_historico_financeiro(cliente, dados):
    pagina = cliente.get("/pagamentos?data_de=2026-11-01&grupo=Centro").text
    assert "Baixar estes pagamentos" in pagina and "data_de=2026-11-01" in pagina and "grupo=Centro" in pagina
    assert 'name="ano"' in pagina and 'value="2026"' in pagina and "Baixar planilha do ano" in pagina
