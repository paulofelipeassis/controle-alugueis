"""Testes do módulo opcional reajuste (sugestão pelo IPCA/IGP-M)."""
from sistema import servicos
from sistema.modulos import reajuste


def _meses(pct):
    """Simula o Banco Central: 12 meses com a mesma variação."""
    return lambda indice: [(f"2025-{m:02d}" if m >= 9 else f"2026-{m:02d}", str(pct))
                           for m in [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]]


_contador = iter(range(10_000_000_000, 99_999_999_999))


def _contrato(inicio="2025-10-05", indice="IGP-M", valor=150000):
    n = next(_contador)
    imovel = servicos.cadastrar_imovel("t", "G", f"U{n}", "E")
    loc = servicos.cadastrar_locatario("t", "N", str(n), "n@x.com")
    return servicos.criar_contrato("t", imovel, loc, inicio, "2027-10-04", 5, valor, indice_reajuste=indice,
                                   valor_vigente_desde=inicio)


def test_sugestao():
    contrato = _contrato()
    s = reajuste.sugerir(contrato, buscar=_meses("0.5"))
    assert s["percentual"] == "6.17" and s["valor_sugerido"] == "R$ 1.592,55"
    assert s["vigente_desde"] == "2026-10-05"
    assert s["resumo"] == "IGP-M de 09/2025 a 08/2026 = 6,17%: R$ 1.500,00 → R$ 1.592,55 a partir de 05/10/2026"
    assert s["motivo"] == "IGP-M 6,17% (09/2025 a 08/2026)"


def test_sugestao_com_indice_negativo_mantem_valor():
    s = reajuste.sugerir(_contrato(), buscar=_meses("-0.3"))
    assert s["valor_sugerido_centavos"] == 150000 and "valor mantido" in s["resumo"]


def test_sugestao_sem_indice_ou_fora_do_ar():
    assert "à mão" in reajuste.sugerir(_contrato(indice="INPC"), buscar=_meses("1"))["erro"]

    def fora_do_ar(indice):
        raise OSError("sem conexão")

    assert "Banco Central" in reajuste.sugerir(_contrato(), buscar=fora_do_ar)["erro"]


def test_reajuste_pela_web(cliente, monkeypatch):
    imovel = servicos.cadastrar_imovel("t", "G", "U", "E")
    loc = servicos.cadastrar_locatario("t", "N", "12345678900", "n@x.com")
    dados = {"imovel_id": imovel, "locatario_id": loc, "data_inicio": "2024-10-05",
             "data_fim_prevista": "2027-10-04", "valor_aluguel": "1.500,00", "dia_vencimento": "5",
             "multa_pct": "2", "juros_mes_pct": "1", "garantia_tipo": "nenhuma", "indice_reajuste": "IGP-M"}
    r = cliente.post("/contratos/novo", data=dados)
    assert "último reajuste" in r.text  # contrato antigo sem a data do valor atual
    r = cliente.post("/contratos/novo", data={**dados, "valor_vigente_desde": "2025-10-05"})
    assert "Contrato criado" in r.text and "Calcular pelo IGP-M" in r.text
    contrato = int(str(r.url).rsplit("/", 1)[1])
    monkeypatch.setattr(reajuste, "ultimos_12_meses",
                        lambda indice: [(f"2025-{m:02d}", "0.5") for m in range(1, 13)])
    r = cliente.get(f"/contratos/{contrato}/reajuste")
    assert "6,17%" in r.text and 'value="1.592,55"' in r.text and 'value="2026-10-05"' in r.text
    r = cliente.post(f"/contratos/{contrato}/reajuste",
                     data={"novo_valor": "1.580,00", "vigente_desde": "2026-10-05", "motivo": "IGP-M combinado"})
    assert "Reajuste registrado" in r.text and "R$ 1.580,00 desde 05/10/2026" in r.text
