from datetime import date
from decimal import Decimal

import pytest

from sistema import consultas, db, regras, servicos
from sistema.regras import ErroDeNegocio


def _indice_fixo(pct_mes, publicado_ate="2099-12"):
    """Simula o Banco Central: mesma variação todo mês, publicada até `publicado_ate`."""
    chamadas = []

    def buscar(indice, de, ate):
        chamadas.append((indice, de, ate))
        return {m: str(pct_mes) for m in regras.competencias_entre(de, min(ate, publicado_ate))}

    buscar.chamadas = chamadas
    return buscar


_contador = iter(range(10_000_000_000, 99_999_999_999))


def _contrato(inicio="2025-10-05", indice="IGP-M", valor=150000, vigente=None):
    n = next(_contador)
    imovel = servicos.cadastrar_imovel("t", "G", f"U{n}", "E")
    loc = servicos.cadastrar_locatario("t", "N", str(n), "n@x.com")
    return servicos.criar_contrato("t", imovel, loc, inicio, "2027-10-04", 5, valor, indice_reajuste=indice,
                                   valor_vigente_desde=vigente or inicio)


def test_regras_do_reajuste():
    assert regras.normalizar_indice("igpm") == regras.normalizar_indice("IGP-M") == "IGP-M"
    assert regras.normalizar_indice(" ipca ") == "IPCA"
    assert regras.normalizar_indice("INPC") is None
    assert regras.proximo_aniversario(date(2025, 10, 5)) == date(2026, 10, 5)
    # Aniversário em outubro: 12 meses de outubro do ano anterior a setembro.
    assert regras.periodo_reajuste(date(2026, 10, 5)) == ("2025-10", "2026-09")
    assert regras.acumulado_pct(["1"] * 12) == Decimal("12.68")
    assert regras.valor_reajustado(150000, Decimal("4.12")) == 156180
    assert regras.valor_reajustado(150000, Decimal("-2.5")) == 150000  # negativo mantém


def test_contrato_antigo_exige_data_do_valor_atual():
    imovel = servicos.cadastrar_imovel("t", "Antigo", "1", "E")
    loc = servicos.cadastrar_locatario("t", "Antigo", "11122233344", "a@x.com")
    with pytest.raises(ErroDeNegocio, match="último reajuste"):
        servicos.criar_contrato("t", imovel, loc, "2024-03-01", "2027-02-28", 5, 100000, indice_reajuste="IPCA")
    with pytest.raises(ErroDeNegocio, match="entre o início do contrato e hoje"):
        _contrato(inicio="2024-03-01", vigente="2023-01-01")
    contrato = _contrato(inicio="2024-03-01", vigente="2026-03-01")
    # Nenhuma cobrança antes do início das cobranças no sistema (2026-10): sem débitos estranhos.
    servicos.gerar_cobrancas("t", "2026-10-01")
    assert [c["competencia"] for c in consultas.listar_cobrancas(contrato_id=contrato, hoje="2026-10-01")] == \
        ["2026-10"]
    # Próximo reajuste 12 meses depois do último, não do início do contrato.
    tipos = [a for a in consultas.alertas(hoje="2026-10-01") if a["tipo"] == "reajuste"]
    assert tipos == []
    assert any(a["tipo"] == "reajuste" for a in consultas.alertas(hoje="2027-02-15"))


def test_proposta_e_aprovacao():
    contrato = _contrato()
    buscar = _indice_fixo("0.5")
    assert servicos.gerar_propostas_reajuste("t", "2026-08-01", buscar) == []  # mais de 30 dias antes
    [proposta] = servicos.gerar_propostas_reajuste("t", "2026-09-10", buscar)
    assert buscar.chamadas == [("IGP-M", "2025-10", "2026-09")]
    # Rodar de novo não duplica nem busca de novo (índices guardados).
    assert servicos.gerar_propostas_reajuste("t", "2026-09-11", buscar) == []
    assert len(buscar.chamadas) == 1
    p = consultas.listar_propostas_reajuste()[0]
    assert p["percentual"] == "6.17" and p["valor_proposto"] == "R$ 1.592,55"
    assert "IGP-M de 10/2025 a 09/2026 = 6,17%" in p["resumo"]
    assert any(a["tipo"] == "proposta_reajuste" for a in consultas.alertas(hoje="2026-09-10"))
    assert consultas.painel(hoje="2026-09-10")["reajustes_para_aprovar"] == 1

    # Nada muda até alguém aprovar.
    servicos.gerar_cobrancas("t", "2026-10-01")
    outubro = consultas.listar_cobrancas(competencia="2026-10", contrato_id=contrato, hoje="2026-10-01")[0]
    assert outubro["valor_centavos"] == 150000
    r = servicos.aprovar_reajuste("paulo", proposta)
    assert r["valor_centavos"] == 159255 and r["pendencias"] == []
    outubro = consultas.listar_cobrancas(competencia="2026-10", contrato_id=contrato, hoje="2026-10-01")[0]
    assert outubro["valor_centavos"] == 159255
    extrato = consultas.extrato_contrato(contrato, hoje="2026-10-01")
    assert extrato["valores"][-1]["motivo"] == "IGP-M 6,17% (2025-10 a 2026-09)"
    assert consultas.listar_propostas_reajuste() == []
    with pytest.raises(ErroDeNegocio, match="já foi aprovada"):
        servicos.aprovar_reajuste("paulo", proposta)
    # O próximo aniversário é daqui a 12 meses.
    assert servicos.gerar_propostas_reajuste("t", "2026-10-20", buscar) == []


def test_indice_negativo_mantem_valor():
    contrato = _contrato()
    [proposta] = servicos.gerar_propostas_reajuste("t", "2026-09-10", _indice_fixo("-0.3"))
    p = consultas.listar_propostas_reajuste()[0]
    assert p["valor_proposto_centavos"] == 150000 and "valor mantido" in p["resumo"]
    servicos.aprovar_reajuste("paulo", proposta)
    extrato = consultas.extrato_contrato(contrato, hoje="2026-10-01")
    assert extrato["valores"][-1]["valor_centavos"] == 150000
    assert "índice negativo" in extrato["valores"][-1]["motivo"]


def test_aprovar_com_valor_combinado_e_boleto_ja_emitido():
    contrato = _contrato()
    [proposta] = servicos.gerar_propostas_reajuste("t", "2026-09-10", _indice_fixo("0.5"))
    servicos.gerar_cobrancas("t", "2026-10-01")
    outubro = consultas.listar_cobrancas(competencia="2026-10", contrato_id=contrato, hoje="2026-10-01")[0]
    servicos.registrar_boleto("hermes", outubro["id"], "Caixa", "NN-OUT")
    r = servicos.aprovar_reajuste("paulo", proposta, valor_centavos=155000)
    assert r["valor_centavos"] == 155000
    assert r["pendencias"][0]["tipo"] == "boleto_valor_antigo"
    assert "valor combinado" in consultas.extrato_contrato(contrato)["valores"][-1]["motivo"]


def test_indice_ainda_nao_publicado_ou_fora_do_ar():
    _contrato(indice="IPCA")
    # IPCA de setembro sai só em outubro: ainda sem proposta, alerta avisa que está aguardando.
    assert servicos.gerar_propostas_reajuste("t", "2026-09-28", _indice_fixo("0.4", publicado_ate="2026-08")) == []
    alerta = [a for a in consultas.alertas(hoje="2026-09-28") if a["tipo"] == "reajuste"][0]
    assert "assim que o índice" in alerta["mensagem"]

    def fora_do_ar(*_):
        raise OSError("sem conexão")

    assert servicos.gerar_propostas_reajuste("t", "2026-10-11", fora_do_ar) == []
    assert len(servicos.gerar_propostas_reajuste("t", "2026-10-11", _indice_fixo("0.4"))) == 1


def test_indice_nao_suportado_fica_so_no_alerta():
    _contrato(indice="INPC")
    assert servicos.gerar_propostas_reajuste("t", "2026-09-28", _indice_fixo("1")) == []
    alerta = [a for a in consultas.alertas(hoje="2026-09-28") if a["tipo"] == "reajuste"][0]
    assert "registre o reajuste à mão" in alerta["mensagem"]


def test_contrato_encerrado_nao_recebe_proposta():
    contrato = _contrato()
    servicos.encerrar_contrato("t", contrato, "2026-09-30", "saída")
    assert servicos.gerar_propostas_reajuste("t", "2026-09-10", _indice_fixo("0.5")) == []
    with db.leitura() as con:
        assert con.execute("SELECT COUNT(*) FROM propostas_reajuste").fetchone()[0] == 0
