"""Disponibiliza o aviso de backup para o painel."""
from fastapi import APIRouter

from sistema.modulos import backup
from sistema.web_comum import templates

router = APIRouter()  # sem páginas próprias
templates.env.globals.update(status_backup=backup.situacao)
