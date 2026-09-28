"""Backup do banco e da pasta de documentos, com envio ao Google Drive (rclone).

Uso:
  python -m scripts.backup          # faz um backup agora
  python -m scripts.backup --loop   # fica rodando e faz um por dia (BACKUP_HORA, padrão 3h)

Guarda as últimas BACKUP_MANTER cópias (padrão 14) na pasta local e no Drive.
Roda no servidor, independente do Hermes.
"""
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sistema import config, db

try:
    from sistema.modulos import backup as aviso
except ImportError:  # módulo opcional removido: o backup funciona igual, só sem o aviso no painel
    aviso = None

PREFIXO = "backup-alugueis-"


def _log(texto):
    print(f"{datetime.now(ZoneInfo(config.TZ)):%Y-%m-%d %H:%M:%S} {texto}", flush=True)


def _registrar(**dados):
    """Guarda o resultado para o painel mostrar (módulo opcional; sem ele, só segue)."""
    if aviso is None:
        return
    try:
        aviso.gravar(**dados)
    except Exception as erro:  # noqa: BLE001 — o aviso nunca pode derrubar o backup
        _log(f"Não consegui gravar o status do backup: {erro}")


def fazer_backup():
    arquivo = None
    try:
        arquivo = _fazer_copia_local()
        if config.RCLONE_DESTINO:
            _enviar(arquivo)
    except Exception as erro:
        _registrar(ok=False, arquivo=arquivo.name if arquivo else None,
                   drive=False if arquivo and config.RCLONE_DESTINO else None, erro=str(erro)[:200])
        raise
    _registrar(ok=True, arquivo=arquivo.name, drive=True if config.RCLONE_DESTINO else None)
    return arquivo


def _fazer_copia_local():
    pasta = Path(config.BACKUP_DIR)
    pasta.mkdir(parents=True, exist_ok=True)
    nome = f"{PREFIXO}{datetime.now(ZoneInfo(config.TZ)):%Y-%m-%d-%H%M}.tar.gz"
    arquivo = pasta / nome
    with tempfile.TemporaryDirectory() as tmp:
        copia = Path(tmp) / "alugueis.db"
        # Cópia consistente mesmo com o sistema rodando (API de backup do SQLite).
        origem = db.conectar()
        destino = sqlite3.connect(copia)
        try:
            origem.backup(destino)
        finally:
            destino.close()
            origem.close()
        with tarfile.open(arquivo, "w:gz") as tar:
            tar.add(copia, arcname="alugueis.db")
            if Path(config.DOCS_DIR).is_dir():
                tar.add(config.DOCS_DIR, arcname="documentos")
    _log(f"Backup local criado: {arquivo} ({arquivo.stat().st_size // 1024} KB)")
    _limpar_local(pasta)
    return arquivo


def _limpar_local(pasta):
    antigos = sorted(pasta.glob(f"{PREFIXO}*.tar.gz"))[:-config.BACKUP_MANTER]
    for arquivo in antigos:
        arquivo.unlink()


def _enviar(arquivo):
    try:
        _enviar_ao_drive(arquivo)
    except (OSError, subprocess.CalledProcessError) as erro:
        raise RuntimeError("não consegui copiar para o Google Drive (rclone). Se foi a autorização que "
                           f"venceu, refaça o passo do rclone em docs/instalacao-servidor.md. Detalhe: {erro}") from erro


def _enviar_ao_drive(arquivo):
    destino = config.RCLONE_DESTINO
    subprocess.run(["rclone", "copy", str(arquivo), destino], check=True)
    _log(f"Enviado para {destino}")
    lista = subprocess.run(["rclone", "lsf", destino, "--include", f"{PREFIXO}*"], check=True,
                           capture_output=True, text=True).stdout.split()
    for nome in sorted(lista)[:-config.BACKUP_MANTER]:
        subprocess.run(["rclone", "deletefile", f"{destino.rstrip('/')}/{nome}"], check=True)
        _log(f"Apagado do Drive (antigo): {nome}")


def _segundos_ate_proximo():
    agora = datetime.now(ZoneInfo(config.TZ))
    proximo = agora.replace(hour=config.BACKUP_HORA, minute=0, second=0, microsecond=0)
    if proximo <= agora:
        proximo += timedelta(days=1)
    return (proximo - agora).total_seconds()


def main():
    if "--loop" not in sys.argv:
        fazer_backup()
        return
    _log(f"Backup diário ativo às {config.BACKUP_HORA}h.")
    if aviso is not None and aviso.precisa_agora():  # servidor novo ou que ficou desligado
        try:
            fazer_backup()
        except Exception as erro:  # noqa: BLE001
            _log(f"ERRO no backup: {erro}")
    while True:
        time.sleep(_segundos_ate_proximo())
        try:
            fazer_backup()
        except Exception as erro:  # noqa: BLE001 — um dia com erro não pode parar os próximos
            _log(f"ERRO no backup: {erro}")


if __name__ == "__main__":
    main()
