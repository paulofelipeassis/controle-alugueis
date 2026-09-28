"""Base das páginas web, usada pelo núcleo (web.py) e pelas páginas dos módulos.

Padrão dos formulários: POST → serviço → redireciona com mensagem (não grava duas vezes
se a página for atualizada). Erro de regra: mostra a mensagem.
"""
from pathlib import Path

from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from sistema import consultas, modulos, regras
from sistema.regras import ErroDeNegocio

PASTA = Path(__file__).parent
templates = Jinja2Templates(directory=[PASTA / "templates", *modulos.pastas_templates()])

FORMAS = [("pix", "PIX"), ("boleto", "Boleto"), ("transferencia", "Transferência"), ("dinheiro", "Dinheiro"),
          ("outro", "Outro")]
GARANTIAS = [("nenhuma", "Nenhuma"), ("caucao", "Caução"), ("fiador", "Fiador"), ("seguro_fianca", "Seguro-fiança")]
SITUACOES_COBRANCA = [("atrasada", "Atrasada"), ("em_aberto", "Em aberto"), ("parcial", "Parcial"),
                      ("paga", "Paga"), ("isenta", "Isenta"), ("cancelada", "Cancelada")]


def _data(valor):
    if not valor:
        return ""
    texto = str(valor)
    data = f"{texto[8:10]}/{texto[5:7]}/{texto[0:4]}"
    return f"{data} {texto[11:16]}" if len(texto) > 10 else data


templates.env.filters["reais"] = regras.formatar_reais
templates.env.filters["reais_campo"] = lambda c: regras.formatar_reais(c).removeprefix("R$ ") if c else ""
templates.env.filters["data"] = _data
templates.env.filters["pct"] = lambda v: f"{float(v):g}".replace(".", ",") if v not in (None, "") else ""
templates.env.filters["comp"] = lambda c: f"{c[5:7]}/{c[0:4]}" if c else ""
_ATIVOS = set(modulos.nomes())
templates.env.globals.update(FORMAS=FORMAS, GARANTIAS=GARANTIAS, SITUACOES_COBRANCA=SITUACOES_COBRANCA,
                             ROTULOS=consultas.ROTULOS_SITUACAO, modulo_ativo=lambda nome: nome in _ATIVOS)


def quem(request):
    return request.session["usuario"]["login"]


def avisar(request, texto, tipo="ok"):
    request.session.setdefault("mensagens", []).append({"texto": texto, "tipo": tipo})


def pagina(request, nome, **contexto):
    mensagens = request.session.pop("mensagens", [])
    return templates.TemplateResponse(request, nome, {
        "usuario": request.session.get("usuario"), "mensagens": mensagens, **contexto})


def ir(url):
    return RedirectResponse(url, status_code=303)


def local(url, padrao="/"):
    """Só aceita endereço interno do próprio sistema (evita redirecionar para outro site)."""
    url = str(url or "")
    return url if url.startswith("/") and not url.startswith("//") else padrao


async def ler_form(request):
    return {chave: (valor.strip() if isinstance(valor, str) else valor) for chave, valor in (await request.form()).items()}


def centavos(texto, campo="valor"):
    return regras.reais_para_centavos(texto, campo) if texto not in (None, "") else None


def pct(texto, campo):
    try:
        return float(str(texto).replace(",", "."))
    except ValueError:
        raise ErroDeNegocio(f"Percentual inválido em {campo}: '{texto}'.") from None


def int_ou_none(texto):
    return int(texto) if texto not in (None, "") else None


def acao(request, voltar, funcao, sucesso):
    """Executa uma ação de botão e volta para a página com mensagem de sucesso ou de erro."""
    try:
        resultado = funcao()
        avisar(request, sucesso(resultado) if callable(sucesso) else sucesso)
        if isinstance(resultado, dict):
            for pendencia in resultado.get("pendencias", []):
                avisar(request, f"Pendência criada: {pendencia['descricao']}", "aviso")
    except ErroDeNegocio as erro:
        avisar(request, str(erro), "erro")
    return ir(voltar)


def salvar_form(request, template, contexto, funcao, destino, sucesso):
    """Formulário de cadastro/edição: em erro, mostra o formulário de novo com os dados digitados."""
    try:
        resultado = funcao()
    except ErroDeNegocio as erro:
        return pagina(request, template, erro=str(erro), **contexto)
    avisar(request, sucesso)
    return ir(destino(resultado))
