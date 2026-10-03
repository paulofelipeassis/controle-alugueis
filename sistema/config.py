"""Configuração lida de variáveis de ambiente.

Os módulos leem `config.X` na hora do uso (nunca `from config import X`), para
os testes poderem trocar os valores com monkeypatch.
"""
import os

DB_PATH = os.environ.get("DB_PATH", "dados/alugueis.db")
DOCS_DIR = os.environ.get("DOCS_DIR", "dados/documentos")
INICIO_COBRANCAS = os.environ.get("INICIO_COBRANCAS", "2026-11")  # outubro/2026 fecha no sistema antigo
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")
MCP_TOKEN = os.environ.get("MCP_TOKEN", "")
TZ = os.environ.get("TZ", "America/Sao_Paulo")
MCP_PORT = int(os.environ.get("MCP_PORT", "8001"))
BACKUP_DIR = os.environ.get("BACKUP_DIR", "dados/backups")
# Destino do rclone, ex.: "drive:Backup Alugueis". Vazio = só backup local.
RCLONE_DESTINO = os.environ.get("RCLONE_DESTINO", "")
BACKUP_MANTER = int(os.environ.get("BACKUP_MANTER", "14"))
BACKUP_HORA = int(os.environ.get("BACKUP_HORA", "3"))
# Feriados que o sistema não conhece (municipais, ou dias sem expediente bancário): lista separada por
# vírgula, cada item 'MM-DD' (todo ano) ou 'AAAA-MM-DD'. Ex. (Formosa-GO): "08-01,11-30,12-08".
FERIADOS_EXTRAS = os.environ.get("FERIADOS_EXTRAS", "")
# 1 quando o site é acessado por HTTPS (servidor): o cookie de login só viaja por conexão segura.
COOKIE_SEGURO = os.environ.get("COOKIE_SEGURO", "0") == "1"
# SÓ PARA DEMONSTRAÇÃO (branch descartável): "AAAA-MM-DD" congela a data de hoje do sistema.
HOJE_FICTICIO = os.environ.get("HOJE_FICTICIO", "")
# SÓ PARA DEMONSTRAÇÃO: "1" entra direto como "visitante", sem login.
DEMO_SEM_LOGIN = os.environ.get("DEMO_SEM_LOGIN", "0") == "1"
