from pathlib import Path

import pytest

from sistema import arquivos, config, consultas, db, servicos
from sistema.regras import ErroDeNegocio


def _cobranca(contrato_id, competencia):
    with db.leitura() as con:
        return con.execute("SELECT id FROM cobrancas WHERE contrato_id = ? AND competencia = ?",
                           (contrato_id, competencia)).fetchone()["id"]


def _situacao(contrato_id, competencia, hoje="2026-10-05"):
    cobrancas = consultas.listar_cobrancas(competencia=competencia, contrato_id=contrato_id, hoje=hoje)
    return cobrancas[0]["situacao_calculada"], cobrancas[0]["saldo_centavos"]


def test_parcial_e_completo(cenario):
    servicos.gerar_cobrancas("t", "2026-11-01")
    out = _cobranca(cenario["contrato"], "2026-10")
    r = servicos.registrar_pagamento("t", out, "2026-10-08", 100000, "pix")
    assert r["pendencias"][0]["tipo"] == "pagamento_divergente"
    assert _situacao(cenario["contrato"], "2026-10") == ("parcial", 50000)
    servicos.registrar_pagamento("t", out, "2026-10-09", 50000, "pix")
    assert _situacao(cenario["contrato"], "2026-10") == ("paga", 0)
    # Saldo não passa para o mês seguinte.
    assert _situacao(cenario["contrato"], "2026-11")[1] == 150000


def test_em_dia_sem_pendencia(cenario):
    servicos.gerar_cobrancas("t", "2026-10-01")
    r = servicos.registrar_pagamento("t", _cobranca(cenario["contrato"], "2026-10"), "2026-10-10", 150000, "pix")
    assert r["pendencias"] == []


def test_atraso_sem_encargos_vira_pendencia(cenario):
    servicos.gerar_cobrancas("t", "2026-10-01")
    out = _cobranca(cenario["contrato"], "2026-10")
    r = servicos.registrar_pagamento("t", out, "2026-10-20", 150000, "pix")
    assert r["pendencias"][0]["tipo"] == "pagamento_divergente"
    # Venceu sábado 10/10 e segunda 12/10 é feriado: a contagem começa no dia útil, terça 13/10.
    # 7 dias de atraso: 1500 + 2% + 1% × 7/30 = R$ 1.533,50
    assert "R$ 1.533,50" in r["pendencias"][0]["descricao"]
    assert _situacao(cenario["contrato"], "2026-10", "2026-10-25")[0] == "paga"


def test_atraso_com_encargos_sem_pendencia(cenario):
    servicos.gerar_cobrancas("t", "2026-10-01")
    r = servicos.registrar_pagamento("t", _cobranca(cenario["contrato"], "2026-10"), "2026-10-20", 153350, "boleto")
    assert r["pendencias"] == []


def test_boleto_pago_duas_vezes_registra_uma(cenario):
    servicos.gerar_cobrancas("t", "2026-10-01")
    out = _cobranca(cenario["contrato"], "2026-10")
    servicos.registrar_boleto("t", out, "Caixa", "NN-1")
    primeiro = servicos.registrar_pagamento_boleto("hermes", "NN-1", "2026-10-10", 150000)
    segundo = servicos.registrar_pagamento_boleto("hermes", "NN-1", "2026-10-10", 150000)
    assert primeiro["registrado"] and not primeiro["ja_existia"]
    assert segundo["ja_existia"] and segundo["pagamento_id"] == primeiro["pagamento_id"]
    assert consultas.historico_pagamentos()["quantidade"] == 1


def test_boleto_desconhecido(cenario):
    r = servicos.registrar_pagamento_boleto("hermes", "NN-XYZ", "2026-10-10", 150000)
    assert r["registrado"] is False
    # Repetir não cria outra pendência.
    assert servicos.registrar_pagamento_boleto("hermes", "NN-XYZ", "2026-10-10", 150000)["pendencia_id"] == \
        r["pendencia_id"]
    assert len(consultas.listar_pendencias()) == 1
    assert consultas.historico_pagamentos()["quantidade"] == 0


def test_pagamento_em_cobranca_ja_paga(cenario):
    servicos.gerar_cobrancas("t", "2026-10-01")
    out = _cobranca(cenario["contrato"], "2026-10")
    servicos.registrar_pagamento("t", out, "2026-10-10", 150000, "pix")
    r = servicos.registrar_pagamento("t", out, "2026-10-10", 150000, "pix")
    assert r["pendencias"][0]["tipo"] == "possivel_duplicidade"


def test_pagamento_em_contrato_encerrado(cenario):
    servicos.gerar_cobrancas("t", "2026-10-01")
    out = _cobranca(cenario["contrato"], "2026-10")
    servicos.encerrar_contrato("t", cenario["contrato"], "2026-10-31", "saída")
    r = servicos.registrar_pagamento("t", out, "2026-11-05", 150000, "pix")
    assert "contrato_encerrado" in [p["tipo"] for p in r["pendencias"]]


def test_cancelar_pagamento(cenario):
    servicos.gerar_cobrancas("t", "2026-10-01")
    out = _cobranca(cenario["contrato"], "2026-10")
    r = servicos.registrar_pagamento("t", out, "2026-10-10", 150000, "pix", identificador_externo="E2E-1")
    servicos.cancelar_pagamento("t", r["pagamento_id"], "lançado errado")
    assert _situacao(cenario["contrato"], "2026-10") == ("em_aberto", 150000)
    # Depois de cancelado, o mesmo identificador pode ser registrado de novo.
    assert servicos.registrar_pagamento("t", out, "2026-10-10", 150000, "pix",
                                        identificador_externo="E2E-1")["ja_existia"] is False
    with pytest.raises(ErroDeNegocio, match="motivo"):
        servicos.cancelar_pagamento("t", r["pagamento_id"], "")


def test_mesmo_locatario_com_dois_contratos(cenario):
    """Erro da versão antiga: o contrato era escolhido pelo nome do locatário."""
    outro_imovel = servicos.cadastrar_imovel("t", "Anel Viário", "Apto 102", "Rua A, 1")
    segundo = servicos.criar_contrato("t", outro_imovel, cenario["locatario"], "2026-10-01", "2027-10-01", 10,
                                      90000)
    servicos.gerar_cobrancas("t", "2026-10-01")
    servicos.registrar_pagamento("t", _cobranca(segundo, "2026-10"), "2026-10-10", 90000, "pix")
    assert _situacao(segundo, "2026-10")[0] == "paga"
    assert _situacao(cenario["contrato"], "2026-10")[0] == "em_aberto"


def test_forma_invalida_e_comprovante(cenario):
    servicos.gerar_cobrancas("t", "2026-10-01")
    out = _cobranca(cenario["contrato"], "2026-10")
    with pytest.raises(ErroDeNegocio, match="Forma"):
        servicos.registrar_pagamento("t", out, "2026-10-10", 150000, "cheque")
    with pytest.raises(ErroDeNegocio, match="não encontrado"):
        servicos.registrar_pagamento("t", out, "2026-10-10", 150000, "pix", comprovante_caminho="nao/existe.pdf")
    pasta = arquivos.pasta("contrato", cenario["contrato"])
    arquivo = Path(config.DOCS_DIR) / pasta / "comprovante-2026-10.pdf"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_bytes(b"%PDF")
    servicos.registrar_pagamento("t", out, "2026-10-10", 150000, "pix",
                                 comprovante_caminho=f"{pasta}/comprovante-2026-10.pdf")
