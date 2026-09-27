"""Páginas web (FastAPI + Jinja2, HTML gerado no servidor, sem JavaScript de build).

Só chama `servicos` e `consultas`, com quem = login do usuário. Padrão dos
formulários: POST → serviço → redireciona com mensagem (não grava duas vezes
se a página for atualizada). Erro de regra: mostra a mensagem.

Rodar: uvicorn sistema.web:app --port 8000
"""
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from sistema import config, consultas, regras, servicos
from sistema.regras import ErroDeNegocio

PASTA = Path(__file__).parent
templates = Jinja2Templates(directory=PASTA / "templates")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")

TIPOS_DOCUMENTO = [
    ("contrato-assinado", "Contrato assinado"), ("vistoria-entrada", "Vistoria de entrada"),
    ("vistoria-saida", "Vistoria de saída"), ("aditivo", "Aditivo"), ("documento-pessoal", "Documento pessoal"),
    ("comprovante", "Comprovante"), ("foto", "Foto"), ("outro", "Outro"),
]
FORMAS = [("pix", "PIX"), ("boleto", "Boleto"), ("transferencia", "Transferência"), ("dinheiro", "Dinheiro"),
          ("outro", "Outro")]
GARANTIAS = [("nenhuma", "Nenhuma"), ("caucao", "Caução"), ("fiador", "Fiador"), ("seguro_fianca", "Seguro-fiança")]
SITUACOES_COBRANCA = [("atrasada", "Atrasada"), ("em_aberto", "Em aberto"), ("parcial", "Parcial"),
                      ("paga", "Paga"), ("isenta", "Isenta"), ("cancelada", "Cancelada")]


# --- FILTROS DOS TEMPLATES ---
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
templates.env.globals.update(TIPOS_DOCUMENTO=TIPOS_DOCUMENTO, FORMAS=FORMAS, GARANTIAS=GARANTIAS,
                             SITUACOES_COBRANCA=SITUACOES_COBRANCA, ROTULOS=consultas.ROTULOS_SITUACAO)


# --- LOGIN ---
class ExigeLogin(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        livre = request.url.path in ("/login", "/saude") or request.url.path.startswith("/static/")
        if not livre and "usuario" not in request.session:
            return RedirectResponse("/login", status_code=303)
        return await call_next(request)


app.add_middleware(ExigeLogin)
# Adicionado por último = roda primeiro: a sessão precisa existir antes do ExigeLogin.
# Sem SESSION_SECRET, usa um aleatório: funciona, mas todos precisam entrar de novo a cada reinício.
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET or secrets.token_hex(32),
                   max_age=30 * 24 * 3600, same_site="lax")


# --- AUXILIARES ---
def _quem(request):
    return request.session["usuario"]["login"]


def _avisar(request, texto, tipo="ok"):
    request.session.setdefault("mensagens", []).append({"texto": texto, "tipo": tipo})


def _pagina(request, nome, **contexto):
    mensagens = request.session.pop("mensagens", [])
    return templates.TemplateResponse(request, nome, {
        "usuario": request.session.get("usuario"), "mensagens": mensagens, **contexto})


def _ir(url):
    return RedirectResponse(url, status_code=303)


def _local(url, padrao="/"):
    """Só aceita endereço interno do próprio sistema (evita redirecionar para outro site)."""
    url = str(url or "")
    return url if url.startswith("/") and not url.startswith("//") else padrao


async def _form(request):
    return {chave: (valor.strip() if isinstance(valor, str) else valor) for chave, valor in (await request.form()).items()}


def _centavos(texto, campo="valor"):
    return regras.reais_para_centavos(texto, campo) if texto not in (None, "") else None


def _pct(texto, campo):
    try:
        return float(str(texto).replace(",", "."))
    except ValueError:
        raise ErroDeNegocio(f"Percentual inválido em {campo}: '{texto}'.") from None


def _int_ou_none(texto):
    return int(texto) if texto not in (None, "") else None


def _acao(request, voltar, funcao, sucesso):
    """Executa uma ação de botão e volta para a página com mensagem de sucesso ou de erro."""
    try:
        resultado = funcao()
        _avisar(request, sucesso)
        if isinstance(resultado, dict):
            for pendencia in resultado.get("pendencias", []):
                _avisar(request, f"Pendência criada: {pendencia['descricao']}", "aviso")
    except ErroDeNegocio as erro:
        _avisar(request, str(erro), "erro")
    return _ir(voltar)


def _salvar_form(request, template, contexto, funcao, destino, sucesso):
    """Formulário de cadastro/edição: em erro, mostra o formulário de novo com os dados digitados."""
    try:
        resultado = funcao()
    except ErroDeNegocio as erro:
        return _pagina(request, template, erro=str(erro), **contexto)
    _avisar(request, sucesso)
    return _ir(destino(resultado))


@app.exception_handler(ErroDeNegocio)
async def _erro_de_negocio(request, erro):
    """Erro em página de consulta (ex.: id que não existe)."""
    return _pagina(request, "erro.html", erro=str(erro))


@app.get("/saude")
def saude():
    return {"ok": True}


@app.get("/login")
def login(request: Request):
    return _pagina(request, "login.html")


@app.post("/login")
async def login_post(request: Request):
    form = await _form(request)
    usuario = servicos.autenticar(form.get("login"), form.get("senha"))
    if not usuario:
        return _pagina(request, "login.html", erro="Login ou senha incorretos.", login=form.get("login"))
    request.session.clear()
    request.session["usuario"] = usuario
    return _ir("/")


@app.get("/sair")
def sair(request: Request):
    request.session.clear()
    return _ir("/login")


@app.get("/senha")
def senha(request: Request):
    return _pagina(request, "senha.html")


@app.post("/senha")
async def senha_post(request: Request):
    form = await _form(request)
    if not servicos.autenticar(_quem(request), form.get("atual")):
        return _pagina(request, "senha.html", erro="Senha atual incorreta.")
    if form.get("nova") != form.get("repetir"):
        return _pagina(request, "senha.html", erro="As senhas novas não conferem.")
    return _salvar_form(request, "senha.html", {}, lambda: servicos.alterar_senha(
        _quem(request), _quem(request), form.get("nova")), lambda _: "/", "Senha alterada.")


# --- PAINEL ---
@app.get("/")
def painel(request: Request):
    return _pagina(request, "painel.html", p=consultas.painel(), recebido=consultas.recebido_por_mes())


# --- IMÓVEIS ---
def _dados_imovel(form):
    return dict(grupo=form.get("grupo"), unidade=form.get("unidade"), endereco=form.get("endereco"),
                iptu_anual_centavos=_centavos(form.get("iptu_anual"), "IPTU"),
                medidor_saneago=form.get("medidor_saneago"), medidor_enel=form.get("medidor_enel"),
                observacoes=form.get("observacoes"), em_manutencao=form.get("em_manutencao") == "on")


@app.get("/imoveis")
def imoveis(request: Request, situacao: str = ""):
    return _pagina(request, "imoveis.html", imoveis=consultas.listar_imoveis(situacao or None), situacao=situacao)


@app.get("/imoveis/novo")
def imovel_novo(request: Request):
    return _pagina(request, "imovel_form.html", dados={}, grupos=consultas.grupos())


@app.post("/imoveis/novo")
async def imovel_novo_post(request: Request):
    form = await _form(request)
    return _salvar_form(request, "imovel_form.html", {"dados": form, "grupos": consultas.grupos()},
                        lambda: servicos.cadastrar_imovel(_quem(request), **_dados_imovel(form)),
                        lambda id_: f"/imoveis/{id_}", "Imóvel cadastrado.")


@app.get("/imoveis/{imovel_id}")
def imovel(request: Request, imovel_id: int):
    return _pagina(request, "imovel.html", i=consultas.ficha_imovel(imovel_id))


@app.get("/imoveis/{imovel_id}/editar")
def imovel_editar(request: Request, imovel_id: int):
    dados = consultas.obter("imovel", imovel_id)
    dados["iptu_anual"] = templates.env.filters["reais_campo"](dados["iptu_anual_centavos"])
    return _pagina(request, "imovel_form.html", dados=dados, grupos=consultas.grupos(), editar=imovel_id)


@app.post("/imoveis/{imovel_id}/editar")
async def imovel_editar_post(request: Request, imovel_id: int):
    form = await _form(request)
    return _salvar_form(request, "imovel_form.html", {"dados": form, "grupos": consultas.grupos(),
                                                       "editar": imovel_id},
                        lambda: servicos.atualizar_imovel(_quem(request), imovel_id, **_dados_imovel(form)),
                        lambda _: f"/imoveis/{imovel_id}", "Imóvel atualizado.")


@app.post("/imoveis/{imovel_id}/apagar")
def imovel_apagar(request: Request, imovel_id: int):
    try:
        servicos.apagar_imovel(_quem(request), imovel_id)
    except ErroDeNegocio as erro:
        _avisar(request, str(erro), "erro")
        return _ir(f"/imoveis/{imovel_id}")
    _avisar(request, "Imóvel apagado.")
    return _ir("/imoveis")


# --- LOCATÁRIOS ---
def _dados_locatario(form):
    return dict(nome=form.get("nome"), cpf_cnpj=form.get("cpf_cnpj"), email=form.get("email"),
                telefone=form.get("telefone"), observacoes=form.get("observacoes"))


@app.get("/locatarios")
def locatarios(request: Request, q: str = ""):
    lista = consultas.buscar_locatarios(q) if q else consultas.listar_locatarios()
    return _pagina(request, "locatarios.html", locatarios=lista, q=q)


@app.get("/locatarios/novo")
def locatario_novo(request: Request):
    return _pagina(request, "locatario_form.html", dados={})


@app.post("/locatarios/novo")
async def locatario_novo_post(request: Request):
    form = await _form(request)
    return _salvar_form(request, "locatario_form.html", {"dados": form},
                        lambda: servicos.cadastrar_locatario(_quem(request), **_dados_locatario(form)),
                        lambda id_: f"/locatarios/{id_}", "Locatário cadastrado.")


@app.get("/locatarios/{locatario_id}")
def locatario(request: Request, locatario_id: int):
    return _pagina(request, "locatario.html", l=consultas.ficha_locatario(locatario_id))


@app.get("/locatarios/{locatario_id}/editar")
def locatario_editar(request: Request, locatario_id: int):
    return _pagina(request, "locatario_form.html", dados=consultas.obter("locatario", locatario_id),
                   editar=locatario_id)


@app.post("/locatarios/{locatario_id}/editar")
async def locatario_editar_post(request: Request, locatario_id: int):
    form = await _form(request)
    return _salvar_form(request, "locatario_form.html", {"dados": form, "editar": locatario_id},
                        lambda: servicos.atualizar_locatario(_quem(request), locatario_id, **_dados_locatario(form)),
                        lambda _: f"/locatarios/{locatario_id}", "Locatário atualizado.")


@app.post("/locatarios/{locatario_id}/apagar")
def locatario_apagar(request: Request, locatario_id: int):
    try:
        servicos.apagar_locatario(_quem(request), locatario_id)
    except ErroDeNegocio as erro:
        _avisar(request, str(erro), "erro")
        return _ir(f"/locatarios/{locatario_id}")
    _avisar(request, "Locatário apagado.")
    return _ir("/locatarios")


# --- CORRETORES ---
def _dados_corretor(form):
    return dict(nome=form.get("nome"), telefone=form.get("telefone"), email=form.get("email"),
                observacoes=form.get("observacoes"))


@app.get("/corretores")
def corretores(request: Request):
    return _pagina(request, "corretores.html", corretores=consultas.listar_corretores())


@app.get("/corretores/novo")
def corretor_novo(request: Request):
    return _pagina(request, "corretor_form.html", dados={})


@app.post("/corretores/novo")
async def corretor_novo_post(request: Request):
    form = await _form(request)
    return _salvar_form(request, "corretor_form.html", {"dados": form},
                        lambda: servicos.cadastrar_corretor(_quem(request), **_dados_corretor(form)),
                        lambda _: "/corretores", "Corretor cadastrado.")


@app.get("/corretores/{corretor_id}/editar")
def corretor_editar(request: Request, corretor_id: int):
    return _pagina(request, "corretor_form.html", dados=consultas.obter("corretor", corretor_id),
                   editar=corretor_id)


@app.post("/corretores/{corretor_id}/editar")
async def corretor_editar_post(request: Request, corretor_id: int):
    form = await _form(request)
    return _salvar_form(request, "corretor_form.html", {"dados": form, "editar": corretor_id},
                        lambda: servicos.atualizar_corretor(_quem(request), corretor_id, **_dados_corretor(form)),
                        lambda _: "/corretores", "Corretor atualizado.")


@app.post("/corretores/{corretor_id}/apagar")
def corretor_apagar(request: Request, corretor_id: int):
    return _acao(request, "/corretores", lambda: servicos.apagar_corretor(_quem(request), corretor_id),
                 "Corretor apagado.")


# --- CONTRATOS ---
def _opcoes_contrato():
    return {"imoveis": [i for i in consultas.listar_imoveis() if i["situacao"] != "alugado"],
            "locatarios": consultas.listar_locatarios(), "corretores": consultas.listar_corretores()}


def _dados_contrato_editaveis(form):
    return dict(corretor_id=_int_ou_none(form.get("corretor_id")), multa_pct=_pct(form.get("multa_pct"), "multa"),
                juros_mes_pct=_pct(form.get("juros_mes_pct"), "juros"), garantia_tipo=form.get("garantia_tipo"),
                garantia_valor_centavos=_centavos(form.get("garantia_valor"), "valor da garantia"),
                fiador=form.get("fiador"), indice_reajuste=form.get("indice_reajuste"),
                observacoes=form.get("observacoes"))


@app.get("/contratos")
def contratos(request: Request, status: str = "ativos"):
    ativos = {"ativos": True, "encerrados": False}.get(status)
    return _pagina(request, "contratos.html", contratos=consultas.listar_contratos(ativos), status=status)


@app.get("/contratos/novo")
def contrato_novo(request: Request, imovel_id: str = "", locatario_id: str = ""):
    dados = {"multa_pct": "2", "juros_mes_pct": "1", "imovel_id": imovel_id, "locatario_id": locatario_id}
    return _pagina(request, "contrato_form.html", dados=dados, **_opcoes_contrato())


@app.post("/contratos/novo")
async def contrato_novo_post(request: Request):
    form = await _form(request)

    def criar():
        if not form.get("imovel_id") or not form.get("locatario_id"):
            raise ErroDeNegocio("Escolha o imóvel e o locatário.")
        return servicos.criar_contrato(
            _quem(request), int(form["imovel_id"]), int(form["locatario_id"]), form.get("data_inicio"),
            form.get("data_fim_prevista"), int(form.get("dia_vencimento") or 0),
            _centavos(form.get("valor_aluguel"), "valor do aluguel"), **_dados_contrato_editaveis(form))

    return _salvar_form(request, "contrato_form.html", {"dados": form, **_opcoes_contrato()}, criar,
                        lambda id_: f"/contratos/{id_}", "Contrato criado. As cobranças foram geradas.")


@app.get("/contratos/{contrato_id}")
def contrato(request: Request, contrato_id: int):
    return _pagina(request, "contrato.html", c=consultas.extrato_contrato(contrato_id))


@app.get("/contratos/{contrato_id}/editar")
def contrato_editar(request: Request, contrato_id: int):
    dados = consultas.extrato_contrato(contrato_id)
    dados["garantia_valor"] = templates.env.filters["reais_campo"](dados["garantia_valor_centavos"])
    for campo in ("multa_pct", "juros_mes_pct"):
        dados[campo] = templates.env.filters["pct"](dados[campo])
    return _pagina(request, "contrato_form.html", dados=dados, editar=contrato_id, **_opcoes_contrato())


@app.post("/contratos/{contrato_id}/editar")
async def contrato_editar_post(request: Request, contrato_id: int):
    form = await _form(request)
    contexto = {"dados": {**consultas.extrato_contrato(contrato_id), **form}, "editar": contrato_id,
                **_opcoes_contrato()}
    return _salvar_form(request, "contrato_form.html", contexto,
                        lambda: servicos.atualizar_contrato(_quem(request), contrato_id,
                                                            **_dados_contrato_editaveis(form)),
                        lambda _: f"/contratos/{contrato_id}", "Contrato atualizado.")


@app.post("/contratos/{contrato_id}/reajuste")
async def contrato_reajuste(request: Request, contrato_id: int):
    form = await _form(request)
    return _acao(request, f"/contratos/{contrato_id}", lambda: servicos.registrar_reajuste(
        _quem(request), contrato_id, _centavos(form.get("novo_valor"), "novo valor"), form.get("vigente_desde"),
        form.get("motivo")), "Reajuste registrado.")


@app.post("/contratos/{contrato_id}/renovar")
async def contrato_renovar(request: Request, contrato_id: int):
    form = await _form(request)
    return _acao(request, f"/contratos/{contrato_id}", lambda: servicos.renovar_contrato(
        _quem(request), contrato_id, form.get("nova_data_fim"), _centavos(form.get("novo_valor"), "novo valor"),
        form.get("vigente_desde") or None), "Contrato renovado.")


@app.post("/contratos/{contrato_id}/encerrar")
async def contrato_encerrar(request: Request, contrato_id: int):
    form = await _form(request)
    return _acao(request, f"/contratos/{contrato_id}", lambda: servicos.encerrar_contrato(
        _quem(request), contrato_id, form.get("data_encerramento"), form.get("motivo")), "Contrato encerrado.")


@app.post("/contratos/{contrato_id}/apagar")
def contrato_apagar(request: Request, contrato_id: int):
    try:
        servicos.apagar_contrato(_quem(request), contrato_id)
    except ErroDeNegocio as erro:
        _avisar(request, str(erro), "erro")
        return _ir(f"/contratos/{contrato_id}")
    _avisar(request, "Contrato apagado.")
    return _ir("/contratos")


# --- COBRANÇAS ---
@app.get("/cobrancas")
def cobrancas(request: Request, competencia: str = "", situacao: str = ""):
    try:
        lista = consultas.listar_cobrancas(competencia or None, situacao or None)
    except ErroDeNegocio as erro:
        _avisar(request, str(erro), "erro")
        lista = consultas.listar_cobrancas(situacao=situacao or None)
    return _pagina(request, "cobrancas.html", cobrancas=lista, competencia=competencia, situacao=situacao,
                   total=sum(c["saldo_centavos"] for c in lista))


@app.get("/cobrancas/{cobranca_id}")
def cobranca(request: Request, cobranca_id: int):
    base = consultas.obter("cobranca", cobranca_id)
    extrato = consultas.extrato_contrato(base["contrato_id"])
    return _pagina(request, "cobranca.html", c=next(c for c in extrato["cobrancas"] if c["id"] == cobranca_id),
                   contrato=extrato)


def _acao_cobranca(request, cobranca_id, funcao, sucesso):
    return _acao(request, f"/cobrancas/{cobranca_id}", funcao, sucesso)


@app.post("/cobrancas/{cobranca_id}/valor")
async def cobranca_valor(request: Request, cobranca_id: int):
    form = await _form(request)
    return _acao_cobranca(request, cobranca_id, lambda: servicos.editar_valor_cobranca(
        _quem(request), cobranca_id, _centavos(form.get("valor")), form.get("motivo")), "Valor alterado.")


@app.post("/cobrancas/{cobranca_id}/isentar")
async def cobranca_isentar(request: Request, cobranca_id: int):
    form = await _form(request)
    return _acao_cobranca(request, cobranca_id, lambda: {"pendencias": [p for p in [servicos.isentar_cobranca(
        _quem(request), cobranca_id, form.get("motivo"))] if p]}, "Cobrança isentada.")


@app.post("/cobrancas/{cobranca_id}/cancelar")
async def cobranca_cancelar(request: Request, cobranca_id: int):
    form = await _form(request)
    return _acao_cobranca(request, cobranca_id, lambda: {"pendencias": [p for p in [servicos.cancelar_cobranca(
        _quem(request), cobranca_id, form.get("motivo"))] if p]}, "Cobrança cancelada.")


@app.post("/cobrancas/{cobranca_id}/boleto")
async def cobranca_boleto(request: Request, cobranca_id: int):
    form = await _form(request)
    return _acao_cobranca(request, cobranca_id, lambda: servicos.registrar_boleto(
        _quem(request), cobranca_id, form.get("banco"), form.get("identificador"), form.get("linha_digitavel"),
        form.get("link"), substituir=form.get("substituir") == "on"), "Boleto registrado.")


@app.post("/cobrancas/{cobranca_id}/enviado")
def cobranca_enviado(request: Request, cobranca_id: int):
    return _acao_cobranca(request, cobranca_id, lambda: servicos.marcar_boleto_enviado(_quem(request), cobranca_id),
                          "Boleto marcado como enviado.")


# --- PAGAMENTOS ---
def _cobrancas_para_pagar():
    return [c for c in consultas.listar_cobrancas() if c["situacao"] == "normal" and c["saldo_centavos"] > 0]


@app.get("/pagamentos/novo")
def pagamento_novo(request: Request, cobranca_id: str = ""):
    dados = {"cobranca_id": cobranca_id, "data_pagamento": regras.hoje().isoformat(), "forma": "pix"}
    return _pagina(request, "pagamento_form.html", dados=dados, cobrancas=_cobrancas_para_pagar())


@app.post("/pagamentos/novo")
async def pagamento_novo_post(request: Request):
    form = await _form(request)
    quem = _quem(request)

    def registrar():
        if not form.get("cobranca_id"):
            raise ErroDeNegocio("Escolha a cobrança.")
        cobranca_id = int(form["cobranca_id"])
        valor = _centavos(form.get("valor"), "valor pago")
        comprovante = None
        arquivo = form.get("comprovante")
        if arquivo is not None and getattr(arquivo, "filename", ""):
            cobranca = consultas.obter("cobranca", cobranca_id)
            doc_id = servicos.salvar_documento(
                quem, "contrato", cobranca["contrato_id"], "comprovante", arquivo.filename, arquivo.file.read(),
                nome_base=f"comprovante-{cobranca['competencia']}")
            comprovante = consultas.obter("documento", doc_id)["caminho"]
        resultado = servicos.registrar_pagamento(
            quem, cobranca_id, form.get("data_pagamento"), valor, form.get("forma"),
            identificador_externo=form.get("identificador_externo") or None, comprovante_caminho=comprovante,
            observacao=form.get("observacao"))
        for pendencia in resultado["pendencias"]:
            _avisar(request, f"Pendência criada: {pendencia['descricao']}", "aviso")
        return resultado

    dados = {k: v for k, v in form.items() if isinstance(v, str)}
    return _salvar_form(request, "pagamento_form.html", {"dados": dados, "cobrancas": _cobrancas_para_pagar()},
                        registrar, lambda r: f"/cobrancas/{r['cobranca_id']}", "Pagamento registrado.")


@app.get("/pagamentos")
def pagamentos(request: Request, data_de: str = "", data_ate: str = "", grupo: str = "", locatario_id: str = "",
               cancelados: str = ""):
    try:
        historico = consultas.historico_pagamentos(data_de or None, data_ate or None, grupo or None,
                                                   locatario_id=_int_ou_none(locatario_id),
                                                   incluir_cancelados=cancelados == "on")
    except ErroDeNegocio as erro:
        _avisar(request, str(erro), "erro")
        historico = consultas.historico_pagamentos()
    return _pagina(request, "pagamentos.html", h=historico, grupos=consultas.grupos(),
                   locatarios=consultas.listar_locatarios(),
                   filtros=dict(data_de=data_de, data_ate=data_ate, grupo=grupo, locatario_id=locatario_id,
                                cancelados=cancelados))


@app.post("/pagamentos/{pagamento_id}/cancelar")
async def pagamento_cancelar(request: Request, pagamento_id: int):
    form = await _form(request)
    return _acao(request, _local(form.get("voltar"), "/pagamentos"),
                 lambda: servicos.cancelar_pagamento(_quem(request), pagamento_id, form.get("motivo")),
                 "Pagamento cancelado.")


# --- PENDÊNCIAS E AUDITORIA ---
@app.get("/pendencias")
def pendencias(request: Request, todas: str = ""):
    return _pagina(request, "pendencias.html", pendencias=consultas.listar_pendencias(abertas=not todas),
                   todas=todas)


@app.post("/pendencias/{pendencia_id}/resolver")
async def pendencia_resolver(request: Request, pendencia_id: int):
    form = await _form(request)
    return _acao(request, "/pendencias", lambda: servicos.resolver_pendencia(
        _quem(request), pendencia_id, form.get("resolucao")), "Pendência resolvida.")


@app.get("/auditoria")
def auditoria(request: Request, entidade: str = ""):
    return _pagina(request, "auditoria.html", registros=consultas.auditoria(entidade or None, limite=200),
                   entidade=entidade)


# --- DOCUMENTOS ---
@app.post("/documentos")
async def documento_enviar(request: Request):
    form = await _form(request)
    voltar = _local(form.get("voltar"))
    arquivo = form.get("arquivo")

    def salvar():
        if arquivo is None or not getattr(arquivo, "filename", ""):
            raise ErroDeNegocio("Escolha um arquivo.")
        servicos.salvar_documento(_quem(request), form.get("entidade"), int(form.get("entidade_id")),
                                  form.get("tipo"), arquivo.filename, arquivo.file.read(), form.get("descricao"))

    return _acao(request, voltar, salvar, "Documento enviado.")


@app.get("/documentos/{documento_id}")
def documento(request: Request, documento_id: int):
    doc = consultas.obter("documento", documento_id)
    caminho = servicos.caminho_absoluto(doc["caminho"])
    if not caminho.is_file():
        raise ErroDeNegocio(f"O arquivo não está mais na pasta de documentos: {doc['caminho']}")
    return FileResponse(caminho, filename=caminho.name, content_disposition_type="inline")
