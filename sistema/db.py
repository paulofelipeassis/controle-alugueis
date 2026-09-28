"""Conexão com o SQLite.

Cada operação abre a própria conexão (barato no SQLite) e fecha no fim. O
schema (núcleo + módulos opcionais) é aplicado automaticamente na primeira conexão
de cada arquivo, e as migrações pendentes (MIGRACOES) rodam em bancos que já existiam.
"""
import contextlib
import sqlite3
from pathlib import Path

from sistema import config, modulos

_SCHEMA = Path(__file__).with_name("schema.sql")
_inicializados = set()

# Mudanças no schema DEPOIS de haver dados reais no banco. Cada item é uma lista de comandos SQL (um
# comando por texto), aplicada uma única vez, na ordem, em bancos que já existem. Regras:
#   1. Nunca editar um item já publicado: acrescente um novo no fim.
#   2. Faça a mesma mudança no schema.sql, porque banco novo nasce a partir dele.
#   3. Só acrescente coisas (tabela, coluna com valor padrão); apagar ou renomear dado exige cuidado.
# Antes de aplicar, o sistema guarda uma cópia do banco ao lado dele (…antes-da-migracao-N).
# Exemplo: [["ALTER TABLE imoveis ADD COLUMN area_m2 REAL"]]
MIGRACOES = []


def _migrar(con, caminho):
    versao = con.execute("PRAGMA user_version").fetchone()[0]
    if versao >= len(MIGRACOES):
        return
    copia = sqlite3.connect(f"{caminho}.antes-da-migracao-{versao}")
    try:
        con.backup(copia)
    finally:
        copia.close()
    con.execute("BEGIN IMMEDIATE")  # dois processos subindo juntos: o segundo espera e encontra tudo pronto
    try:
        for i in range(con.execute("PRAGMA user_version").fetchone()[0], len(MIGRACOES)):
            for comando in MIGRACOES[i]:
                con.execute(comando)
            con.execute(f"PRAGMA user_version = {i + 1}")
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise


def conectar():
    caminho = config.DB_PATH
    Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None: nós controlamos as transações com BEGIN/COMMIT.
    con = sqlite3.connect(caminho, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute("PRAGMA foreign_keys = ON")
    # WAL: a web e o MCP (dois processos) usam o mesmo arquivo ao mesmo tempo.
    con.execute("PRAGMA journal_mode = WAL")
    if caminho not in _inicializados:
        novo = con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'imoveis'").fetchone() is None
        con.executescript(_SCHEMA.read_text(encoding="utf-8"))
        for schema in modulos.schemas():  # tabelas dos módulos opcionais
            con.executescript(schema.read_text(encoding="utf-8"))
        if novo:  # banco novo já nasce na versão mais recente
            con.execute(f"PRAGMA user_version = {len(MIGRACOES)}")
        else:
            _migrar(con, caminho)
        _inicializados.add(caminho)
    return con


@contextlib.contextmanager
def transacao():
    """Tudo dentro do bloco é gravado junto, ou nada é gravado."""
    con = conectar()
    try:
        con.execute("BEGIN IMMEDIATE")
        yield con
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


@contextlib.contextmanager
def leitura():
    con = conectar()
    try:
        yield con
    finally:
        con.close()
