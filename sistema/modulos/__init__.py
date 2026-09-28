"""Módulos opcionais: funções extras que podem ser removidas apagando a pasta.

Cada subpasta é um módulo e pode ter:
  __init__.py   a lógica (usa o núcleo: servicos, consultas, arquivos...)
  schema.sql    tabelas próprias (aplicadas junto com as do núcleo)
  web.py        `router` (APIRouter) com as páginas do módulo
  mcp.py        `registrar(mcp)` com as ferramentas do Hermes
  alertas.py    `alertas(hoje)` -> lista de avisos para o painel e para o Hermes
  templates/    páginas HTML (em templates/<nome_do_modulo>/...)
  test_*.py     testes do módulo

Regra: o núcleo nunca importa um módulo pelo nome; só os encontra por aqui. Nas
páginas do núcleo, um pedaço de um módulo aparece com
`{% if modulo_ativo("nome") %}...{% endif %}`, então apagar a pasta não quebra nada.
"""
import importlib
import logging
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


def alertas(hoje):
    """Avisos de todos os módulos, no mesmo formato dos avisos do núcleo: {'tipo', 'contrato_id', 'mensagem'}.
    Um módulo com defeito não derruba o painel: vira um aviso dizendo qual módulo falhou."""
    lista = []
    for nome in nomes():
        modulo = carregar(nome, "alertas")
        if modulo is None:
            continue
        try:
            lista += modulo.alertas(hoje)
        except Exception:  # noqa: BLE001 — módulo opcional nunca pode quebrar o núcleo
            logging.getLogger("controle_alugueis").exception("Falha nos avisos do módulo '%s'", nome)
            lista.append({"tipo": "erro_de_modulo", "contrato_id": None,
                          "mensagem": f"O módulo '{nome}' falhou ao montar os avisos dele (o resto do sistema segue "
                                      "normal). Avise quem cuida do sistema."})
    return lista


def schemas():
    return [PASTA / n / "schema.sql" for n in nomes() if (PASTA / n / "schema.sql").is_file()]


def pastas_templates():
    return [PASTA / n / "templates" for n in nomes() if (PASTA / n / "templates").is_dir()]
