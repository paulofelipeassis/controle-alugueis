import sqlite3
from pathlib import Path

import pytest

from sistema import config, db, servicos


def _reabrir():
    db._inicializados.discard(config.DB_PATH)  # simula o sistema sendo reiniciado


def test_banco_novo_nasce_na_versao_mais_recente(monkeypatch):
    monkeypatch.setattr(db, "MIGRACOES", [["ALTER TABLE imoveis ADD COLUMN area_m2 REAL"]])
    with db.leitura() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 1


def test_banco_com_dados_recebe_a_migracao_uma_vez_e_guarda_copia(monkeypatch):
    imovel = servicos.cadastrar_imovel("t", "Anel Viário", "Apto 101", "Rua A")  # banco "antigo", versão 0
    monkeypatch.setattr(db, "MIGRACOES", [["ALTER TABLE imoveis ADD COLUMN area_m2 REAL",
                                          "UPDATE imoveis SET area_m2 = 50"]])
    _reabrir()
    with db.leitura() as con:
        assert con.execute("SELECT id, grupo, area_m2 FROM imoveis").fetchone()[:] == (imovel, "Anel Viário", 50)
        assert con.execute("PRAGMA user_version").fetchone()[0] == 1
    copia = Path(f"{config.DB_PATH}.antes-da-migracao-0")
    assert copia.is_file()
    assert "area_m2" not in [c[1] for c in sqlite3.connect(copia).execute("PRAGMA table_info(imoveis)")]
    _reabrir()  # reiniciar de novo não repete a migração (senão daria 'duplicate column')
    with db.leitura() as con:
        assert con.execute("PRAGMA user_version").fetchone()[0] == 1


def test_migracao_com_erro_desfaz_tudo(monkeypatch):
    servicos.cadastrar_imovel("t", "G", "U", "E")
    monkeypatch.setattr(db, "MIGRACOES", [["ALTER TABLE imoveis ADD COLUMN x REAL", "COMANDO INVALIDO"]])
    _reabrir()
    with pytest.raises(sqlite3.OperationalError):
        db.conectar()
    monkeypatch.setattr(db, "MIGRACOES", [])
    _reabrir()
    with db.leitura() as con:  # nada ficou pela metade
        assert "x" not in [c[1] for c in con.execute("PRAGMA table_info(imoveis)")]
        assert con.execute("PRAGMA user_version").fetchone()[0] == 0
