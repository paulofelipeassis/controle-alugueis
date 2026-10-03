"""Vencimento em fim de semana ou feriado vale até o dia útil seguinte, sem multa nem juros."""
from datetime import date

import pytest

from sistema import config, consultas, regras, servicos
from sistema.regras import ErroDeNegocio


def test_pascoa_e_feriados_moveis():
    assert [regras.pascoa(a) for a in (2024, 2025, 2026, 2027, 2028)] == [
        date(2024, 3, 31), date(2025, 4, 20), date(2026, 4, 5), date(2027, 3, 28), date(2028, 4, 16)]
    f = regras.feriados(2026)
    assert {date(2026, 2, 16), date(2026, 2, 17), date(2026, 4, 3), date(2026, 6, 4)} <= f  # carnaval, sexta santa, corpus christi
    assert {date(2026, 1, 1), date(2026, 10, 12), date(2026, 11, 20), date(2026, 12, 25)} <= f
    assert date(2023, 11, 20) not in regras.feriados(2023)  # só vale a partir de 2024


def test_vencimento_efetivo():
    assert regras.vencimento_efetivo(date(2026, 10, 9)) == date(2026, 10, 9)    # sexta
    assert regras.vencimento_efetivo(date(2026, 10, 10)) == date(2026, 10, 13)  # sábado, domingo e feriado 12/10
    assert regras.vencimento_efetivo(date(2026, 4, 3)) == date(2026, 4, 6)      # sexta-feira santa
    assert regras.vencimento_efetivo(date(2026, 12, 25)) == date(2026, 12, 28)  # sexta, feriado, fim de semana
    # 31/12 sem expediente bancário; 01/01 feriado; 02 e 03/01/2027 fim de semana.
    assert regras.vencimento_efetivo(date(2026, 12, 31)) == date(2027, 1, 4)
    assert date(2023, 12, 31) in regras.feriados(2023)


def test_feriados_extras(monkeypatch):
    monkeypatch.setattr(config, "FERIADOS_EXTRAS", "08-01, 11-30,12-08, 2026-12-30")  # Formosa + um dia avulso
    assert date(2026, 8, 1) in regras.feriados(2026) and date(2028, 12, 8) in regras.feriados(2028)
    assert regras.vencimento_efetivo(date(2026, 11, 30)) == date(2026, 12, 1)  # segunda, Dia do Evangélico
    assert regras.vencimento_efetivo(date(2027, 11, 29)) == date(2027, 11, 29)  # segunda comum
    assert date(2026, 12, 30) in regras.feriados(2026) and date(2027, 12, 30) not in regras.feriados(2027)
    monkeypatch.setattr(config, "FERIADOS_EXTRAS", "24/10")
    with pytest.raises(ErroDeNegocio, match="FERIADOS_EXTRAS"):
        regras.feriados(2026)


def test_boleto_pago_no_primeiro_dia_util_nao_e_atraso(cenario):
    # A cobrança de outubro vence sábado 10/10/2026; segunda 12/10 é feriado.
    cb = consultas.listar_cobrancas(competencia="2026-10", hoje="2026-10-10")[0]
    assert cb["vencimento"] == "2026-10-10" and cb["vencimento_efetivo"] == "2026-10-13"
    assert consultas.listar_cobrancas(competencia="2026-10", hoje="2026-10-13")[0]["situacao_calculada"] == "em_aberto"
    atrasada = consultas.listar_cobrancas(competencia="2026-10", hoje="2026-10-14")[0]
    assert atrasada["situacao_calculada"] == "atrasada" and atrasada["dias_atraso"] == 1
    assert consultas.inadimplentes(hoje="2026-10-13") == []

    r = servicos.registrar_pagamento("hermes", cb["id"], "2026-10-13", 150000, "boleto", identificador_externo="NN1")
    assert r["pendencias"] == []
    assert consultas.listar_cobrancas(competencia="2026-10", hoje="2026-10-13")[0]["situacao_calculada"] == "paga"


def test_um_dia_depois_do_dia_util_ja_cobra_encargos(cenario):
    cb = consultas.listar_cobrancas(competencia="2026-10", hoje="2026-10-10")[0]
    # 14/10: 1 dia de atraso (a partir de 13/10): multa 2% = 30,00 + juros 1% × 1/30 = 0,50
    r = servicos.registrar_pagamento("hermes", cb["id"], "2026-10-14", 150000, "pix")
    assert "R$ 1.530,50" in r["pendencias"][0]["descricao"]
