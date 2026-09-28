"""Ferramentas do Hermes do módulo proporcional."""
from sistema.modulos import proporcional

HERMES = "hermes"


def sugerir_primeiro_periodo(contrato_id: int) -> dict:
    """Se o contrato começou no meio do mês, sugere o valor proporcional aos dias usados para a
    PRIMEIRA cobrança (que nasce com o aluguel cheio). Devolve {'aplicavel': false} quando não há
    o que decidir. Mostre ao Paulo e pergunte se o primeiro aluguel é proporcional, ANTES de emitir
    o primeiro boleto."""
    sugestao = proporcional.sugerir(contrato_id)
    return {"aplicavel": True, **sugestao} if sugestao else {"aplicavel": False}


def decidir_primeiro_periodo(contrato_id: int, proporcional_aos_dias: bool) -> dict:
    """Registra a decisão do Paulo sobre o primeiro período: true aplica o valor proporcional na
    primeira cobrança; false mantém o aluguel cheio. SÓ use depois que o Paulo responder."""
    return proporcional.decidir(HERMES, contrato_id, proporcional_aos_dias)


def registrar(mcp):
    for ferramenta in (sugerir_primeiro_periodo, decidir_primeiro_periodo):
        mcp.tool()(ferramenta)
