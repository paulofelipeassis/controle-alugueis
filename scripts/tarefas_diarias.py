"""Tarefas diárias do servidor: propostas de reajuste e backup.

Uso:
  python -m scripts.tarefas_diarias          # roda uma vez agora
  python -m scripts.tarefas_diarias --loop   # fica rodando: uma vez ao iniciar e todo dia às BACKUP_HORA
"""
import sys
import time

from scripts import backup
from sistema import servicos


def rodar(com_backup=True):
    try:
        criadas = servicos.gerar_propostas_reajuste()
        backup._log(f"Propostas de reajuste novas: {len(criadas)}")
    except Exception as erro:  # noqa: BLE001 — um erro não pode impedir o backup
        backup._log(f"ERRO nas propostas de reajuste: {erro}")
    if com_backup:
        try:
            backup.fazer_backup()
        except Exception as erro:  # noqa: BLE001
            backup._log(f"ERRO no backup: {erro}")


def main():
    if "--loop" not in sys.argv:
        rodar()
        return
    backup._log("Tarefas diárias ativas.")
    rodar(com_backup=False)  # ao iniciar, só as propostas (o backup fica para a hora marcada)
    while True:
        time.sleep(backup._segundos_ate_proximo())
        rodar()


if __name__ == "__main__":
    main()
