from datetime import date
from decimal import Decimal

import pytest

from sistema import consultas, regras, servicos
from sistema.regras import ErroDeNegocio


_contador = iter(range(10_000_000_000, 99_999_999_999))


def _contrato(inicio="2025-10-05", indice="IGP-M", valor=150000):
    n = next(_contador)
    imovel = servicos.cadastrar_imovel("t", "G", f"U{n}", "E")
    loc = servicos.cadastrar_locatario("t", "N", str(n), "n@x.com")
    return servicos.criar_contrato("t", imovel, loc, inicio, "2027-10-04", 5, valor, indice_reajuste=indice,
                                   valor_vigente_desde=inicio)


def test_regras_do_reajuste():
    assert regras.normalizar_indice("igpm") == regras.normalizar_indice("IGP-M") == "IGP-M"
    assert regras.normalizar_indice(" ipca ") == "IPCA"
    assert regras.normalizar_indice("INPC") is None
    assert regras.proximo_aniversario(date(2025, 10, 5)) == date(2026, 10, 5)
    assert regras.acumulado_pct(["1"] * 12) == Decimal("12.68")
    assert regras.valor_reajustado(150000, Decimal("4.12")) == 156180
    assert regras.valor_reajustado(150000, Decimal("-2.5")) == 150000  # negativo mantém


def test_contrato_antigo_exige_data_do_valor_atual():
    imovel = servicos.cadastrar_imovel("t", "Antigo", "1", "E")
    loc = servicos.cadastrar_locatario("t", "Antigo", "11122233344", "a@x.com")
    with pytest.raises(ErroDeNegocio, match="último reajuste"):
        servicos.criar_contrato("t", imovel, loc, "2024-03-01", "2027-02-28", 5, 100000, indice_reajuste="IPCA")
    with pytest.raises(ErroDeNegocio, match="entre o início do contrato e hoje"):
        servicos.criar_contrato("t", imovel, loc, "2024-03-01", "2027-02-28", 5, 100000, indice_reajuste="IPCA",
                                valor_vigente_desde="2023-01-01")
    contrato = servicos.criar_contrato("t", imovel, loc, "2024-03-01", "2027-02-28", 5, 100000,
                                       indice_reajuste="IPCA", valor_vigente_desde="2026-03-01")
    # Nenhuma cobrança antes do início das cobranças no sistema (2026-10): sem débitos estranhos.
    servicos.gerar_cobrancas("t", "2026-10-01")
    assert [c["competencia"] for c in consultas.listar_cobrancas(contrato_id=contrato, hoje="2026-10-01")] == \
        ["2026-10"]
    # Próximo reajuste 12 meses depois do último, não do início do contrato.
    assert not [a for a in consultas.alertas(hoje="2026-10-01") if a["tipo"] == "reajuste"]
    assert [a for a in consultas.alertas(hoje="2027-02-15") if a["tipo"] == "reajuste"]


def test_boleto_13_so_sai_reajustado():
    """A cobrança que vence no aniversário fica marcada até o reajuste do ano ser registrado."""
    contrato = _contrato()
    servicos.gerar_cobrancas("t", "2026-10-01")
    sem_boleto = {c["competencia"]: c for c in consultas.cobrancas_sem_boleto(dias=10, hoje="2026-09-28")}
    assert sem_boleto["2026-10"]["reajuste_pendente"] is True
    alerta = [a for a in consultas.alertas(hoje="2026-09-28") if a["tipo"] == "reajuste"][0]
    assert "Registre antes de emitir o boleto" in alerta["mensagem"]

    servicos.registrar_reajuste("paulo", contrato, 159255, "2026-10-05", "IGP-M 6,17%")
    outubro = consultas.listar_cobrancas(competencia="2026-10", contrato_id=contrato, hoje="2026-09-28")[0]
    assert outubro["valor_centavos"] == 159255 and outubro["reajuste_pendente"] is False
    assert not [a for a in consultas.alertas(hoje="2026-09-28") if a["tipo"] == "reajuste"]


def test_nao_reajustar_no_ano_registrando_o_mesmo_valor():
    contrato = _contrato()
    servicos.registrar_reajuste("paulo", contrato, 150000, "2026-10-05", "sem reajuste (acordo)")
    servicos.gerar_cobrancas("t", "2026-10-01")
    outubro = consultas.listar_cobrancas(competencia="2026-10", contrato_id=contrato, hoje="2026-09-28")[0]
    assert outubro["reajuste_pendente"] is False and outubro["valor_centavos"] == 150000


def test_contrato_sem_indice_nao_cobra_reajuste():
    contrato = _contrato(indice=None)
    servicos.gerar_cobrancas("t", "2026-10-01")
    outubro = consultas.listar_cobrancas(competencia="2026-10", contrato_id=contrato, hoje="2026-09-28")[0]
    assert outubro["reajuste_pendente"] is False
