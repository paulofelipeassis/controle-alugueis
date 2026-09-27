"""Ferramentas do Hermes do módulo documentos."""
from sistema.modulos import documentos

HERMES = "hermes"


def registrar_documento(entidade: str, entidade_id: int, tipo: str, caminho: str,
                        descricao: str | None = None) -> dict:
    """Liga ao sistema um arquivo que você já salvou na pasta de documentos (use pasta_documento
    para saber onde salvar). entidade: 'imovel', 'locatario' ou 'contrato'. tipo: ex.
    'contrato-assinado', 'vistoria-entrada', 'vistoria-saida', 'aditivo', 'documento-pessoal'.
    caminho: relativo à pasta de documentos."""
    return {"documento_id": documentos.registrar(HERMES, entidade, entidade_id, tipo, caminho, descricao)}


def listar_documentos(entidade: str, entidade_id: int) -> list:
    """Documentos ligados a um 'imovel', 'locatario' ou 'contrato' (tipo e caminho)."""
    return documentos.listar(entidade, entidade_id)


def registrar(mcp):
    for ferramenta in (registrar_documento, listar_documentos):
        mcp.tool()(ferramenta)
