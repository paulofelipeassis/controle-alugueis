"""Configuração lida de variáveis de ambiente.

Os módulos leem `config.X` na hora do uso (nunca `from config import X`), para
os testes poderem trocar os valores com monkeypatch.
"""
import os

DB_PATH = os.environ.get("DB_PATH", "dados/alugueis.db")
DOCS_DIR = os.environ.get("DOCS_DIR", "dados/documentos")
INICIO_COBRANCAS = os.environ.get("INICIO_COBRANCAS", "2026-10")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")
TZ = os.environ.get("TZ", "America/Sao_Paulo")
MCP_PORT = int(os.environ.get("MCP_PORT", "8001"))
BACKUP_DIR = os.environ.get("BACKUP_DIR", "dados/backups")
# Destino do rclone, ex.: "drive:Backup Alugueis". Vazio = só backup local.
RCLONE_DESTINO = os.environ.get("RCLONE_DESTINO", "")
BACKUP_MANTER = int(os.environ.get("BACKUP_MANTER", "14"))
BACKUP_HORA = int(os.environ.get("BACKUP_HORA", "3"))
