"""Ferramenta do Hermes do módulo reajuste."""
from sistema.modulos import reajuste


def sugerir_reajuste(contrato_id: int) -> dict:
    """Calcula agora o reajuste anual sugerido: acumulado das últimas 12 variações publicadas do
    IPCA ou IGP-M do contrato (Banco Central). Índice negativo = valor mantido. Não grava nada:
    mostre o 'resumo' ao Paulo e, só depois do "sim" dele, chame registrar_reajuste com
    novo_valor = valor_sugerido (ou o valor que ele disser), vigente_desde e motivo."""
    return reajuste.sugerir(contrato_id)


def registrar(mcp):
    mcp.tool()(sugerir_reajuste)
