"""Conexão com o SQLite.

Cada operação abre a própria conexão (barato no SQLite) e fecha no fim. O
schema é aplicado automaticamente na primeira conexão de cada arquivo.
"""
import contextlib
import sqlite3
from pathlib import Path

from sistema import config

_SCHEMA = Path(__file__).with_name("schema.sql")
_inicializados = set()


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
        con.executescript(_SCHEMA.read_text(encoding="utf-8"))
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
