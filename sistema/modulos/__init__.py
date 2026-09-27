"""Módulos opcionais: funções extras que podem ser removidas apagando a pasta.

Cada subpasta é um módulo e pode ter:
  __init__.py   a lógica (usa o núcleo: servicos, consultas, arquivos...)
  schema.sql    tabelas próprias (aplicadas junto com as do núcleo)
  web.py        `router` (APIRouter) com as páginas do módulo
  mcp.py        `registrar(mcp)` com as ferramentas do Hermes
  templates/    páginas HTML (em templates/<nome_do_modulo>/...)
  test_*.py     testes do módulo

Regra: o núcleo nunca importa um módulo pelo nome; só os encontra por aqui. Nas
páginas do núcleo, um pedaço de um módulo aparece com
`{% if modulo_ativo("nome") %}...{% endif %}`, então apagar a pasta não quebra nada.
"""
import importlib
import pkgutil
from pathlib import Path

PASTA = Path(__file__).parent


def nomes():
    return sorted(m.name for m in pkgutil.iter_modules([str(PASTA)]) if m.ispkg)


def carregar(nome, parte):
    """Importa sistema.modulos.<nome>.<parte>; None se o módulo não tiver essa parte."""
    caminho = f"sistema.modulos.{nome}.{parte}"
    try:
        return importlib.import_module(caminho)
    except ModuleNotFoundError as erro:
        if erro.name == caminho:
            return None
        raise


def schemas():
    return [PASTA / n / "schema.sql" for n in nomes() if (PASTA / n / "schema.sql").is_file()]


def pastas_templates():
    return [PASTA / n / "templates" for n in nomes() if (PASTA / n / "templates").is_dir()]
