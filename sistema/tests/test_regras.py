from datetime import date

import pytest

from sistema import regras
from sistema.regras import ErroDeNegocio


@pytest.mark.parametrize("texto, centavos", [
    ("1.234,56", 123456), ("1234,56", 123456), ("1234.56", 123456), ("1234", 123400),
    ("R$ 1.234,56", 123456), ("1.234", 123400), (1500, 150000), (1500.5, 150050), ("0,1", 10),
])
def test_reais_para_centavos(texto, centavos):
    assert regras.reais_para_centavos(texto) == centavos


@pytest.mark.parametrize("texto", ["abc", "", "-5"])
def test_reais_para_centavos_invalido(texto):
    with pytest.raises(ErroDeNegocio):
        regras.reais_para_centavos(texto)


def test_formatar_reais():
    assert regras.formatar_reais(123456) == "R$ 1.234,56"
    assert regras.formatar_reais(5) == "R$ 0,05"
    assert regras.formatar_reais(123456789) == "R$ 1.234.567,89"


def test_vencimento_dia_que_nao_existe_no_mes():
    assert regras.vencimento("2027-02", 31) == date(2027, 2, 28)
    assert regras.vencimento("2026-04", 31) == date(2026, 4, 30)
    assert regras.vencimento("2028-02", 29) == date(2028, 2, 29)  # bissexto
    assert regras.vencimento("2027-02", 29) == date(2027, 2, 28)
    assert regras.vencimento("2026-10", 10) == date(2026, 10, 10)


def test_primeira_competencia():
    # Início antes do dia de vencimento: primeira cobrança no mesmo mês.
    assert regras.primeira_competencia(date(2026, 10, 5), 10, "2026-10") == "2026-10"
    # Início depois do dia de vencimento: primeira cobrança no mês seguinte.
    assert regras.primeira_competencia(date(2026, 10, 15), 10, "2026-10") == "2026-11"
    # Contrato antigo: nada antes do início das cobranças no sistema.
    assert regras.primeira_competencia(date(2025, 3, 1), 10, "2026-10") == "2026-10"
    # Dia 31 começando em 30/04: vence 30/04 (último dia), no mesmo mês.
    assert regras.primeira_competencia(date(2027, 4, 30), 31, "2026-10") == "2027-04"


def test_encargos():
    venc = date(2026, 10, 10)
    assert regras.encargos(150000, 2, 1, venc, date(2026, 10, 10)) == (0, 0)
    # 10 dias: multa 2% = 30,00; juros 1% × 10/30 = 5,00
    assert regras.encargos(150000, 2, 1, venc, date(2026, 10, 20)) == (3000, 500)


@pytest.mark.parametrize("situacao, valor, pago, venc, esperado", [
    ("cancelada", 100, 0, date(2026, 1, 1), "cancelada"),
    ("isenta", 100, 0, date(2026, 1, 1), "isenta"),
    ("normal", 100, 100, date(2026, 1, 1), "paga"),
    ("normal", 100, 150, date(2026, 1, 1), "paga"),
    ("normal", 100, 50, date(2026, 12, 1), "parcial"),
    ("normal", 100, 50, date(2026, 1, 1), "atrasada"),
    ("normal", 100, 0, date(2026, 1, 1), "atrasada"),
    ("normal", 100, 0, date(2026, 11, 1), "em_aberto"),
    ("normal", 100, 0, date(2026, 11, 1), "em_aberto"),
])
def test_situacao_cobranca(situacao, valor, pago, venc, esperado):
    assert regras.situacao_cobranca(situacao, valor, pago, venc, date(2026, 11, 1)) == esperado


def test_validar_cpf_cnpj():
    assert regras.validar_cpf_cnpj("123.456.789-00") == "12345678900"
    assert regras.validar_cpf_cnpj("12.345.678/0001-99") == "12345678000199"
    with pytest.raises(ErroDeNegocio):
        regras.validar_cpf_cnpj("123")


def test_competencia_e_datas():
    assert regras.validar_competencia("10/2026") == "2026-10"
    assert regras.proxima_competencia("2026-12") == "2027-01"
    assert regras.para_data("05/10/2026") == date(2026, 10, 5)
    assert regras.somar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
    with pytest.raises(ErroDeNegocio):
        regras.validar_competencia("2026-13")
    with pytest.raises(ErroDeNegocio):
        regras.para_data("amanhã")


def test_nome_pasta():
    assert regras.nome_pasta("Anel Viário - Apto 101") == "Anel Viario - Apto 101"
    assert regras.nome_pasta('  Sala 2/3: "A"  ') == "Sala 23 A"
