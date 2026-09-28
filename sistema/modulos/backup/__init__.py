"""Módulo opcional: aviso no painel sobre o backup diário.

O script scripts/backup.py grava o resultado de cada tentativa em `status.json`, na pasta de
backups; este módulo lê o arquivo e mostra no painel se está tudo bem, ou avisa quando o backup
parou de funcionar (ninguém olha o log do servidor). Para remover: apagar esta pasta; o backup
continua funcionando, só sem o aviso.
"""
import json
from datetime import datetime
from pathlib import Path

from sistema import config, regras

LIMITE_EM_HORAS = 36   # sem backup completo há mais que isso = alerta vermelho
RENOVAR_EM_HORAS = 20  # ao subir o servidor, faz backup na hora se o último é mais velho que isso


def _arquivo():
    return Path(config.BACKUP_DIR) / "status.json"


def ler():
    try:
        return json.loads(_arquivo().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def gravar(ok, arquivo=None, drive=None, erro=None):
    """ok: backup completo (local e, se configurado, no Drive). drive: True/False, ou None se não configurado."""
    anterior = ler() or {}
    agora = regras.agora()
    dados = {"ultima_tentativa": agora, "ok": ok, "arquivo": arquivo, "drive": drive, "erro": erro,
             "ultimo_sucesso": agora if ok else anterior.get("ultimo_sucesso")}
    _arquivo().parent.mkdir(parents=True, exist_ok=True)
    _arquivo().write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def _horas_desde(texto):
    return (datetime.strptime(regras.agora(), "%Y-%m-%d %H:%M:%S")
            - datetime.strptime(texto, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600


def _br(texto):
    return f"{texto[8:10]}/{texto[5:7]} às {texto[11:16]}"


def precisa_agora():
    """Vale fazer um backup já (ao subir o servidor)? Sim, se não houve um completo nas últimas horas."""
    dados = ler()
    return not dados or not dados.get("ultimo_sucesso") or _horas_desde(dados["ultimo_sucesso"]) > RENOVAR_EM_HORAS


def situacao():
    """{'nivel': 'ok'|'aviso'|'erro', 'mensagem': texto} para mostrar no painel."""
    dados = ler()
    if not dados:
        return {"nivel": "aviso", "mensagem": "O backup automático ainda não rodou. Ele roda todo dia às "
                f"{config.BACKUP_HORA}h; confira se o serviço 'backup' está ligado no servidor."}
    ultimo = dados.get("ultimo_sucesso")
    if not dados.get("ok"):
        quando = f" O último backup completo foi em {_br(ultimo)}." if ultimo else ""
        return {"nivel": "erro", "mensagem": f"O backup falhou: {dados.get('erro') or 'motivo desconhecido'}.{quando}"}
    if not ultimo or _horas_desde(ultimo) > LIMITE_EM_HORAS:
        return {"nivel": "erro", "mensagem": "O backup está parado: o último completo foi em "
                f"{_br(ultimo) if ultimo else 'data desconhecida'}. Veja o servidor."}
    if dados.get("drive") is None:
        return {"nivel": "aviso", "mensagem": "O backup só fica neste servidor (Google Drive não configurado). "
                "Se o servidor quebrar, os dados se perdem."}
    return {"nivel": "ok", "mensagem": f"Último backup: {_br(ultimo)}, copiado no Google Drive."}
