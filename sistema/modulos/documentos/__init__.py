"""Módulo opcional: documentos (contratos assinados, vistorias, RG, fotos...).

Liga arquivos da pasta de documentos a um imóvel, locatário ou contrato, com upload e
lista nas fichas. Para remover: apagar esta pasta (a tabela `documentos` fica no banco
sem uso e não atrapalha nada).
"""
from pathlib import Path

from sistema import arquivos, db, regras, servicos
from sistema.regras import ErroDeNegocio

TIPOS = [
    ("contrato-assinado", "Contrato assinado"), ("vistoria-entrada", "Vistoria de entrada"),
    ("vistoria-saida", "Vistoria de saída"), ("aditivo", "Aditivo"), ("documento-pessoal", "Documento pessoal"),
    ("foto", "Foto"), ("outro", "Outro"),
]
# Nome de arquivo fixo dentro da pasta (ver docs/estrutura-de-pastas.md).
NOMES_FIXOS = ("contrato-assinado", "vistoria-entrada", "vistoria-saida")


def _coluna(entidade):
    if entidade not in arquivos.ENTIDADES:
        raise ErroDeNegocio(f"Entidade inválida: '{entidade}'. Use: {', '.join(arquivos.ENTIDADES)}.")
    return f"{entidade}_id"


def registrar(quem, entidade, entidade_id, tipo, caminho, descricao=None):
    """Liga um arquivo que já está na pasta de documentos. Registrar de novo o mesmo arquivo
    devolve o mesmo documento."""
    coluna = _coluna(entidade)
    arquivos.pasta(entidade, entidade_id)  # confere se o cadastro existe
    relativo = arquivos.caminho_relativo(caminho)
    tipo = str(tipo or "").strip()
    if not tipo:
        raise ErroDeNegocio("Informe o tipo do documento.")
    with db.transacao() as con:
        existente = con.execute("SELECT id FROM documentos WHERE caminho = ?", (relativo,)).fetchone()
        if existente:
            return existente["id"]
        cur = con.execute(
            f"INSERT INTO documentos ({coluna}, tipo, caminho, descricao, registrado_por, registrado_em) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (entidade_id, tipo, relativo, (descricao or "").strip() or None, quem, regras.agora()),
        )
        servicos.auditar(con, quem, "registrar_documento", entidade, entidade_id, documento_id=cur.lastrowid,
                         tipo=tipo, caminho=relativo)
        return cur.lastrowid


def salvar(quem, entidade, entidade_id, tipo, nome_arquivo, conteudo, descricao=None):
    """Upload pela web: grava o arquivo na pasta certa, com nome padronizado, e registra."""
    original = Path(str(nome_arquivo or ""))
    if not original.name:
        raise ErroDeNegocio("Escolha um arquivo.")
    if tipo in NOMES_FIXOS:
        base = tipo
    elif tipo == "aditivo":
        base = f"aditivo-{regras.competencia_de(regras.hoje())}"
    else:
        base = regras.nome_pasta(original.stem).replace(" ", "-").lower() or str(tipo)
    caminho = arquivos.salvar(arquivos.pasta(entidade, entidade_id), base, original.suffix, conteudo)
    return registrar(quem, entidade, entidade_id, tipo, caminho, descricao)


def listar(entidade, entidade_id):
    with db.leitura() as con:
        return [dict(d) for d in con.execute(
            f"SELECT * FROM documentos WHERE {_coluna(entidade)} = ? ORDER BY registrado_em, id", (entidade_id,))]
