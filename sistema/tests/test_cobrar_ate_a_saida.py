"""Encerramento de contrato cujo aluguel é pago depois do uso: cobra os dias usados no próximo vencimento."""
from sistema import consultas, regras, servicos


def _cobrancas(contrato, hoje="2027-03-01"):
    return {c["competencia"]: c for c in consultas.listar_cobrancas(contrato_id=contrato, hoje=hoje)}


def test_valor_proporcional():
    assert regras.valor_proporcional(150000, 15, 30) == 75000
    assert regras.valor_proporcional(150000, 16, 31) == 77419   # 774,19
    assert regras.valor_proporcional(150000, 31, 31) == 150000
    assert regras.valor_proporcional(150000, 0, 30) == 0
    assert regras.valor_proporcional(150000, 45, 30) == 150000  # nunca passa do aluguel cheio
    assert regras.dias_do_mes("2027-02") == 28 and regras.dias_do_mes("2028-02") == 29


def test_saida_no_meio_do_mes_cobra_os_dias_usados(cenario):
    # Contrato do cenário: R$ 1.500,00, vence dia 10, começou em 05/10/2026. Sai em 15/11 (15 de 30 dias).
    r = servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-15", "mudou de cidade",
                                   cobrar_ate_a_saida=True)
    ultima = r["ultima_cobranca"]
    assert (ultima["competencia"], ultima["vencimento"], ultima["valor_centavos"], ultima["dias"]) == \
        ("2026-12", "2026-12-10", 75000, 15)
    assert ultima["dias_do_mes"] == 30 and r["cobrancas_canceladas"] == 0 and r["cobrancas_mantidas"] == 1
    cobrancas = _cobrancas(cenario["contrato"], hoje="2027-03-01")
    assert sorted(cobrancas) == ["2026-10", "2026-11", "2026-12"]  # nada depois da cobrança final
    final = cobrancas["2026-12"]
    assert final["valor_centavos"] == 75000 and final["situacao"] == "normal"
    assert final["motivo_situacao"].startswith("última cobrança (até a saída): 15 de 30 dias")
    assert consultas.listar_imoveis(hoje="2027-03-01")[0]["situacao"] == "vago"


def test_saida_no_ultimo_dia_do_mes_cobra_o_mes_inteiro(cenario):
    r = servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-30", "fim", cobrar_ate_a_saida=True)
    assert r["ultima_cobranca"]["valor_centavos"] == 150000 and r["ultima_cobranca"]["dias"] == 30


def test_saida_antes_do_vencimento_mantem_duas_cobrancas(cenario):
    # Sai em 03/11, antes do dia 10: a cobrança de 10/11 (uso de outubro) segue inteira e a de 10/12
    # cobre só os 3 dias de novembro.
    r = servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-03", "fim", cobrar_ate_a_saida=True)
    assert r["cobrancas_mantidas"] == 2 and r["cobrancas_canceladas"] == 0
    cobrancas = _cobrancas(cenario["contrato"])
    assert cobrancas["2026-11"]["valor_centavos"] == 150000 and cobrancas["2026-11"]["motivo_situacao"] is None
    assert cobrancas["2026-12"]["valor_centavos"] == 15000  # 3/30 de 1.500,00
    assert "2027-01" not in cobrancas


def test_saida_no_mesmo_mes_do_inicio_conta_so_os_dias_do_contrato(cenario):
    # Começou em 05/10 e sai em 20/10: usou 16 dias de outubro (de 05 a 20), vence em novembro.
    r = servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-10-20", "desistiu", cobrar_ate_a_saida=True)
    assert r["ultima_cobranca"]["competencia"] == "2026-11"
    assert (r["ultima_cobranca"]["dias"], r["ultima_cobranca"]["valor_centavos"]) == (16, 77419)


def test_sem_cobrar_ate_a_saida_tudo_depois_e_cancelado(cenario):
    servicos.gerar_cobrancas("t", "2026-12-15")
    r = servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-15", "saiu")  # comportamento de sempre
    assert r["ultima_cobranca"] is None and r["cobrancas_mantidas"] == 0 and r["cobrancas_canceladas"] == 2
    cobrancas = _cobrancas(cenario["contrato"])
    assert cobrancas["2026-12"]["situacao"] == "cancelada" and cobrancas["2027-01"]["situacao"] == "cancelada"


def test_boleto_ja_emitido_da_cobranca_final_pede_segunda_via(cenario):
    servicos.gerar_cobrancas("t", "2026-12-15")
    dez = _cobrancas(cenario["contrato"])["2026-12"]
    servicos.registrar_boleto("hermes", dez["id"], "Caixa", "NN-DEZ")
    r = servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-15", "saiu", cobrar_ate_a_saida=True)
    assert [p["tipo"] for p in r["pendencias"]] == ["boleto_valor_antigo"]
    assert "NN-DEZ" in r["pendencias"][0]["descricao"] and "R$ 750,00" in r["pendencias"][0]["descricao"]


def test_pagamento_da_cobranca_final_nao_gera_pendencia_mas_divida_antiga_sim(cenario):
    servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-15", "saiu", cobrar_ate_a_saida=True)
    cobrancas = _cobrancas(cenario["contrato"], hoje="2026-12-05")
    r = servicos.registrar_pagamento("hermes", cobrancas["2026-12"]["id"], "2026-12-09", 75000, "pix")
    assert r["pendencias"] == []  # a cobrança final é esperada, mesmo com o contrato encerrado
    r = servicos.registrar_pagamento("hermes", cobrancas["2026-10"]["id"], "2026-12-09", 153500, "pix")
    assert "contrato_encerrado" in [p["tipo"] for p in r["pendencias"]]  # dívida antiga paga por quem já saiu


def test_cobranca_final_nao_pede_reajuste(cenario):
    servicos.encerrar_contrato("paulo", cenario["contrato"], "2027-10-20", "fim", cobrar_ate_a_saida=True)
    # O aniversário do contrato passou (05/10/2027), mas contrato encerrado não tem mais reajuste a registrar.
    assert all(not c["reajuste_pendente"] for c in consultas.listar_cobrancas(contrato_id=cenario["contrato"],
                                                                             hoje="2027-11-15"))


def test_reabrir_devolve_a_cobranca_final_ao_valor_cheio(cenario):
    servicos.gerar_cobrancas("t", "2026-12-15")
    dez = _cobrancas(cenario["contrato"])["2026-12"]
    servicos.registrar_boleto("hermes", dez["id"], "Caixa", "NN-DEZ")
    servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-15", "engano", cobrar_ate_a_saida=True)
    r = servicos.reabrir_contrato("paulo", cenario["contrato"], "encerrei por engano")
    volta = _cobrancas(cenario["contrato"], hoje="2026-12-15")["2026-12"]
    assert volta["valor_centavos"] == 150000 and volta["motivo_situacao"] is None
    assert "boleto_valor_antigo" in [p["tipo"] for p in r["pendencias"]]  # o boleto tinha o valor proporcional


def test_reabrir_nao_mexe_em_cobranca_final_que_ja_foi_paga(cenario):
    servicos.encerrar_contrato("paulo", cenario["contrato"], "2026-11-15", "saiu", cobrar_ate_a_saida=True)
    final = _cobrancas(cenario["contrato"], hoje="2026-12-05")["2026-12"]
    servicos.registrar_pagamento("hermes", final["id"], "2026-12-09", 75000, "pix")
    servicos.reabrir_contrato("paulo", cenario["contrato"], "engano")
    assert _cobrancas(cenario["contrato"], hoje="2026-12-15")["2026-12"]["valor_centavos"] == 75000
