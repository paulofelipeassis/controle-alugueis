import sqlite3
import tarfile

from sistema import arquivos, config
from scripts import backup


def test_backup_contem_banco_e_documentos(tmp_path, monkeypatch, cenario):
    monkeypatch.setattr(config, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(config, "RCLONE_DESTINO", "")
    monkeypatch.setattr(config, "BACKUP_MANTER", 2)
    arquivos.salvar(arquivos.pasta("contrato", cenario["contrato"]), "contrato-assinado", ".pdf", b"%PDF")
    arquivo = backup.fazer_backup()
    with tarfile.open(arquivo) as tar:
        nomes = tar.getnames()
        tar.extract("alugueis.db", tmp_path / "restaurado")
    assert any(n.endswith("contrato-assinado.pdf") for n in nomes)
    con = sqlite3.connect(tmp_path / "restaurado" / "alugueis.db")
    assert con.execute("SELECT nome FROM locatarios").fetchone()[0] == "Maria Souza"
    con.close()
    # Guarda só as últimas BACKUP_MANTER cópias.
    for i in range(3):
        (tmp_path / "backups" / f"backup-alugueis-2020-01-0{i + 1}-0300.tar.gz").write_bytes(b"x")
    backup._limpar_local(tmp_path / "backups")
    assert len(list((tmp_path / "backups").glob("*.tar.gz"))) == 2
