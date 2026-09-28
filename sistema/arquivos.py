"""Pasta de documentos compartilhada (sistema, Hermes e File Browser).

Núcleo: usado pelos comprovantes de pagamento e pelo módulo opcional de documentos.
Aqui fica a convenção de pastas (docs/estrutura-de-pastas.md) e a proteção para
nenhum caminho sair da pasta de documentos.
"""
from pathlib import Path, PurePosixPath

from sistema import config, db, regras
from sistema.regras import ErroDeNegocio

ENTIDADES = ("imovel", "locatario", "contrato")


def raiz():
    return Path(config.DOCS_DIR).resolve()


def caminho_relativo(caminho, exigir_arquivo=True):
    """Normaliza um caminho relativo à pasta de documentos e recusa o que sai dela."""
    texto = str(caminho or "").strip().replace("\\", "/")
    if not texto:
        raise ErroDeNegocio("Informe o caminho do arquivo.")
    # Aceita caminho absoluto se estiver dentro da pasta de documentos.
    if texto.startswith("/"):
        try:
            texto = Path(texto).resolve().relative_to(raiz()).as_posix()
        except ValueError:
            raise ErroDeNegocio(f"O arquivo precisa estar dentro da pasta de documentos: '{caminho}'.") from None
    relativo = PurePosixPath(texto)
    if ".." in relativo.parts:
        raise ErroDeNegocio(f"Caminho inválido: '{caminho}'.")
    relativo = relativo.as_posix().removeprefix("./")
    if exigir_arquivo and not (raiz() / relativo).is_file():
        raise ErroDeNegocio(f"Arquivo não encontrado na pasta de documentos: '{relativo}'.")
    return relativo


def caminho_absoluto(relativo):
    absoluto = raiz() / caminho_relativo(relativo, exigir_arquivo=False)
    if not absoluto.resolve().is_relative_to(raiz()):  # link simbólico apontando para fora da pasta
        raise ErroDeNegocio(f"Caminho inválido: '{relativo}'.")
    return absoluto


def pasta(entidade, entidade_id):
    """Pasta (relativa) onde guardar os arquivos de um imóvel, locatário ou contrato."""
    if entidade not in ENTIDADES:
        raise ErroDeNegocio(f"Entidade inválida: '{entidade}'. Use: {', '.join(ENTIDADES)}.")

    def obter(con, tabela, id_, nome):
        linha = con.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id_,)).fetchone()
        if linha is None:
            raise ErroDeNegocio(f"{nome} {id_} não encontrado.")
        return linha

    with db.leitura() as con:
        if entidade == "locatario":
            loc = obter(con, "locatarios", entidade_id, "Locatário")
            return f"locatarios/{regras.nome_pasta(loc['cpf_cnpj'] + ' - ' + loc['nome'])}"
        if entidade == "imovel":
            imovel = obter(con, "imoveis", entidade_id, "Imóvel")
            return f"imoveis/{regras.nome_pasta(imovel['grupo'] + ' - ' + imovel['unidade'])}/imovel"
        contrato = obter(con, "contratos", entidade_id, "Contrato")
        imovel = obter(con, "imoveis", contrato["imovel_id"], "Imóvel")
        loc = obter(con, "locatarios", contrato["locatario_id"], "Locatário")
        return (f"imoveis/{regras.nome_pasta(imovel['grupo'] + ' - ' + imovel['unidade'])}/contratos/"
                f"{regras.nome_pasta(contrato['data_inicio'][:7] + ' - ' + loc['nome'])}")


def salvar(pasta_relativa, nome_base, extensao, conteudo):
    """Grava o arquivo na pasta; se o nome já existir, usa -2, -3... Devolve o caminho relativo."""
    destino = raiz() / caminho_relativo(pasta_relativa, exigir_arquivo=False)
    destino.mkdir(parents=True, exist_ok=True)
    base = regras.nome_pasta(nome_base) or "arquivo"
    extensao = (extensao or "").lower()
    nome, n = f"{base}{extensao}", 2
    while (destino / nome).exists():
        nome, n = f"{base}-{n}{extensao}", n + 1
    (destino / nome).write_bytes(conteudo)
    return f"{pasta_relativa}/{nome}"
