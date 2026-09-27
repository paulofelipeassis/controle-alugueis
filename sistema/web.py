"""Páginas web (FastAPI + Jinja2, HTML gerado no servidor, sem JavaScript de build).

Páginas do núcleo. Só chama `servicos` e `consultas`, com quem = login do usuário.
Auxiliares e templates ficam em web_comum.py; as páginas dos módulos opcionais
(sistema/modulos/*/web.py) são incluídas no fim deste arquivo.

Rodar: uvicorn sistema.web:app --port 8000
"""
import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from sistema import arquivos, config, consultas, modulos, regras, servicos
from sistema.regras import ErroDeNegocio
from sistema.web_comum import (PASTA, acao, avisar, centavos, int_ou_none, ir, ler_form, local, pagina, pct, quem,
                               salvar_form, templates)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=PASTA / "static"), name="static")


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


@app.exception_handler(ErroDeNegocio)
async def _erro_de_negocio(request, erro):
    """Erro em página de consulta (ex.: id que não existe)."""
    return pagina(request, "erro.html", erro=str(erro))


@app.get("/saude")
def saude():
    return {"ok": True}


@app.get("/login")
def login(request: Request):
    return pagina(request, "login.html")


@app.post("/login")
async def login_post(request: Request):
    form = await ler_form(request)
    usuario = servicos.autenticar(form.get("login"), form.get("senha"))
    if not usuario:
        return pagina(request, "login.html", erro="Login ou senha incorretos.", login=form.get("login"))
    request.session.clear()
    request.session["usuario"] = usuario
    return ir("/")


@app.get("/sair")
def sair(request: Request):
    request.session.clear()
    return ir("/login")


@app.get("/senha")
def senha(request: Request):
    return pagina(request, "senha.html")


@app.post("/senha")
async def senha_post(request: Request):
    form = await ler_form(request)
    if not servicos.autenticar(quem(request), form.get("atual")):
        return pagina(request, "senha.html", erro="Senha atual incorreta.")
    if form.get("nova") != form.get("repetir"):
        return pagina(request, "senha.html", erro="As senhas novas não conferem.")
    return salvar_form(request, "senha.html", {}, lambda: servicos.alterar_senha(
        quem(request), quem(request), form.get("nova")), lambda _: "/", "Senha alterada.")


# --- PAINEL ---
@app.get("/")
def painel(request: Request):
    return pagina(request, "painel.html", p=consultas.painel(), recebido=consultas.recebido_por_mes())


# --- IMÓVEIS ---
def _dados_imovel(form):
    return dict(grupo=form.get("grupo"), unidade=form.get("unidade"), endereco=form.get("endereco"),
                iptu_anual_centavos=centavos(form.get("iptu_anual"), "IPTU"),
                medidor_saneago=form.get("medidor_saneago"), medidor_enel=form.get("medidor_enel"),
                observacoes=form.get("observacoes"), em_manutencao=form.get("em_manutencao") == "on")


@app.get("/imoveis")
def imoveis(request: Request, situacao: str = ""):
    return pagina(request, "imoveis.html", imoveis=consultas.listar_imoveis(situacao or None), situacao=situacao)


@app.get("/imoveis/novo")
def imovel_novo(request: Request):
    return pagina(request, "imovel_form.html", dados={}, grupos=consultas.grupos())


@app.post("/imoveis/novo")
async def imovel_novo_post(request: Request):
    form = await ler_form(request)
    return salvar_form(request, "imovel_form.html", {"dados": form, "grupos": consultas.grupos()},
                        lambda: servicos.cadastrar_imovel(quem(request), **_dados_imovel(form)),
                        lambda id_: f"/imoveis/{id_}", "Imóvel cadastrado.")


@app.get("/imoveis/{imovel_id}")
def imovel(request: Request, imovel_id: int):
    return pagina(request, "imovel.html", i=consultas.ficha_imovel(imovel_id))


@app.get("/imoveis/{imovel_id}/editar")
def imovel_editar(request: Request, imovel_id: int):
    dados = consultas.obter("imovel", imovel_id)
    dados["iptu_anual"] = templates.env.filters["reais_campo"](dados["iptu_anual_centavos"])
    return pagina(request, "imovel_form.html", dados=dados, grupos=consultas.grupos(), editar=imovel_id)


@app.post("/imoveis/{imovel_id}/editar")
async def imovel_editar_post(request: Request, imovel_id: int):
    form = await ler_form(request)
    return salvar_form(request, "imovel_form.html", {"dados": form, "grupos": consultas.grupos(),
                                                       "editar": imovel_id},
                        lambda: servicos.atualizar_imovel(quem(request), imovel_id, **_dados_imovel(form)),
                        lambda _: f"/imoveis/{imovel_id}", "Imóvel atualizado.")


@app.post("/imoveis/{imovel_id}/apagar")
def imovel_apagar(request: Request, imovel_id: int):
    try:
        servicos.apagar_imovel(quem(request), imovel_id)
    except ErroDeNegocio as erro:
        avisar(request, str(erro), "erro")
        return ir(f"/imoveis/{imovel_id}")
    avisar(request, "Imóvel apagado.")
    return ir("/imoveis")


# --- LOCATÁRIOS ---
def _dados_locatario(form):
    return dict(nome=form.get("nome"), cpf_cnpj=form.get("cpf_cnpj"), email=form.get("email"),
                telefone=form.get("telefone"), observacoes=form.get("observacoes"))


@app.get("/locatarios")
def locatarios(request: Request, q: str = ""):
    lista = consultas.buscar_locatarios(q) if q else consultas.listar_locatarios()
    return pagina(request, "locatarios.html", locatarios=lista, q=q)


@app.get("/locatarios/novo")
def locatario_novo(request: Request):
    return pagina(request, "locatario_form.html", dados={})


@app.post("/locatarios/novo")
async def locatario_novo_post(request: Request):
    form = await ler_form(request)
    return salvar_form(request, "locatario_form.html", {"dados": form},
                        lambda: servicos.cadastrar_locatario(quem(request), **_dados_locatario(form)),
                        lambda id_: f"/locatarios/{id_}", "Locatário cadastrado.")


@app.get("/locatarios/{locatario_id}")
def locatario(request: Request, locatario_id: int):
    return pagina(request, "locatario.html", l=consultas.ficha_locatario(locatario_id))


@app.get("/locatarios/{locatario_id}/editar")
def locatario_editar(request: Request, locatario_id: int):
    return pagina(request, "locatario_form.html", dados=consultas.obter("locatario", locatario_id),
                   editar=locatario_id)


@app.post("/locatarios/{locatario_id}/editar")
async def locatario_editar_post(request: Request, locatario_id: int):
    form = await ler_form(request)
    return salvar_form(request, "locatario_form.html", {"dados": form, "editar": locatario_id},
                        lambda: servicos.atualizar_locatario(quem(request), locatario_id, **_dados_locatario(form)),
                        lambda _: f"/locatarios/{locatario_id}", "Locatário atualizado.")


@app.post("/locatarios/{locatario_id}/apagar")
def locatario_apagar(request: Request, locatario_id: int):
    try:
        servicos.apagar_locatario(quem(request), locatario_id)
    except ErroDeNegocio as erro:
        avisar(request, str(erro), "erro")
        return ir(f"/locatarios/{locatario_id}")
    avisar(request, "Locatário apagado.")
    return ir("/locatarios")


# --- CORRETORES ---
def _dados_corretor(form):
    return dict(nome=form.get("nome"), telefone=form.get("telefone"), email=form.get("email"),
                observacoes=form.get("observacoes"))


@app.get("/corretores")
def corretores(request: Request):
    return pagina(request, "corretores.html", corretores=consultas.listar_corretores())


@app.get("/corretores/novo")
def corretor_novo(request: Request):
    return pagina(request, "corretor_form.html", dados={})


@app.post("/corretores/novo")
async def corretor_novo_post(request: Request):
    form = await ler_form(request)
    return salvar_form(request, "corretor_form.html", {"dados": form},
                        lambda: servicos.cadastrar_corretor(quem(request), **_dados_corretor(form)),
                        lambda _: "/corretores", "Corretor cadastrado.")


@app.get("/corretores/{corretor_id}/editar")
def corretor_editar(request: Request, corretor_id: int):
    return pagina(request, "corretor_form.html", dados=consultas.obter("corretor", corretor_id),
                   editar=corretor_id)


@app.post("/corretores/{corretor_id}/editar")
async def corretor_editar_post(request: Request, corretor_id: int):
    form = await ler_form(request)
    return salvar_form(request, "corretor_form.html", {"dados": form, "editar": corretor_id},
                        lambda: servicos.atualizar_corretor(quem(request), corretor_id, **_dados_corretor(form)),
                        lambda _: "/corretores", "Corretor atualizado.")


@app.post("/corretores/{corretor_id}/apagar")
def corretor_apagar(request: Request, corretor_id: int):
    return acao(request, "/corretores", lambda: servicos.apagar_corretor(quem(request), corretor_id),
                 "Corretor apagado.")


# --- CONTRATOS ---
def _opcoes_contrato():
    return {"imoveis": [i for i in consultas.listar_imoveis() if i["situacao"] != "alugado"],
            "locatarios": consultas.listar_locatarios(), "corretores": consultas.listar_corretores()}


def _dados_contrato_editaveis(form):
    return dict(corretor_id=int_ou_none(form.get("corretor_id")), multa_pct=pct(form.get("multa_pct"), "multa"),
                juros_mes_pct=pct(form.get("juros_mes_pct"), "juros"), garantia_tipo=form.get("garantia_tipo"),
                garantia_valor_centavos=centavos(form.get("garantia_valor"), "valor da garantia"),
                fiador=form.get("fiador"), indice_reajuste=form.get("indice_reajuste"),
                observacoes=form.get("observacoes"))


@app.get("/contratos")
def contratos(request: Request, status: str = "ativos"):
    ativos = {"ativos": True, "encerrados": False}.get(status)
    return pagina(request, "contratos.html", contratos=consultas.listar_contratos(ativos), status=status)


@app.get("/contratos/novo")
def contrato_novo(request: Request, imovel_id: str = "", locatario_id: str = ""):
    dados = {"multa_pct": "2", "juros_mes_pct": "1", "imovel_id": imovel_id, "locatario_id": locatario_id}
    return pagina(request, "contrato_form.html", dados=dados, **_opcoes_contrato())


@app.post("/contratos/novo")
async def contrato_novo_post(request: Request):
    form = await ler_form(request)

    def criar():
        if not form.get("imovel_id") or not form.get("locatario_id"):
            raise ErroDeNegocio("Escolha o imóvel e o locatário.")
        return servicos.criar_contrato(
            quem(request), int(form["imovel_id"]), int(form["locatario_id"]), form.get("data_inicio"),
            form.get("data_fim_prevista"), int(form.get("dia_vencimento") or 0),
            centavos(form.get("valor_aluguel"), "valor do aluguel"),
            valor_vigente_desde=form.get("valor_vigente_desde") or None, **_dados_contrato_editaveis(form))

    return salvar_form(request, "contrato_form.html", {"dados": form, **_opcoes_contrato()}, criar,
                        lambda id_: f"/contratos/{id_}", "Contrato criado. As cobranças foram geradas.")


@app.get("/contratos/{contrato_id}")
def contrato(request: Request, contrato_id: int):
    return pagina(request, "contrato.html", c=consultas.extrato_contrato(contrato_id))


@app.get("/contratos/{contrato_id}/editar")
def contrato_editar(request: Request, contrato_id: int):
    dados = consultas.extrato_contrato(contrato_id)
    dados["garantia_valor"] = templates.env.filters["reais_campo"](dados["garantia_valor_centavos"])
    for campo in ("multa_pct", "juros_mes_pct"):
        dados[campo] = templates.env.filters["pct"](dados[campo])
    return pagina(request, "contrato_form.html", dados=dados, editar=contrato_id, **_opcoes_contrato())


@app.post("/contratos/{contrato_id}/editar")
async def contrato_editar_post(request: Request, contrato_id: int):
    form = await ler_form(request)
    contexto = {"dados": {**consultas.extrato_contrato(contrato_id), **form}, "editar": contrato_id,
                **_opcoes_contrato()}
    return salvar_form(request, "contrato_form.html", contexto,
                        lambda: servicos.atualizar_contrato(quem(request), contrato_id,
                                                            **_dados_contrato_editaveis(form)),
                        lambda _: f"/contratos/{contrato_id}", "Contrato atualizado.")


@app.post("/contratos/{contrato_id}/reajuste")
async def contrato_reajuste(request: Request, contrato_id: int):
    form = await ler_form(request)
    return acao(request, f"/contratos/{contrato_id}", lambda: servicos.registrar_reajuste(
        quem(request), contrato_id, centavos(form.get("novo_valor"), "novo valor"), form.get("vigente_desde"),
        form.get("motivo")), "Reajuste registrado.")


@app.post("/contratos/{contrato_id}/renovar")
async def contrato_renovar(request: Request, contrato_id: int):
    form = await ler_form(request)
    return acao(request, f"/contratos/{contrato_id}", lambda: servicos.renovar_contrato(
        quem(request), contrato_id, form.get("nova_data_fim"), centavos(form.get("novo_valor"), "novo valor"),
        form.get("vigente_desde") or None), "Contrato renovado.")


@app.post("/contratos/{contrato_id}/encerrar")
async def contrato_encerrar(request: Request, contrato_id: int):
    form = await ler_form(request)
    return acao(request, f"/contratos/{contrato_id}", lambda: servicos.encerrar_contrato(
        quem(request), contrato_id, form.get("data_encerramento"), form.get("motivo")), "Contrato encerrado.")


@app.post("/contratos/{contrato_id}/apagar")
def contrato_apagar(request: Request, contrato_id: int):
    try:
        servicos.apagar_contrato(quem(request), contrato_id)
    except ErroDeNegocio as erro:
        avisar(request, str(erro), "erro")
        return ir(f"/contratos/{contrato_id}")
    avisar(request, "Contrato apagado.")
    return ir("/contratos")


# --- COBRANÇAS ---
@app.get("/cobrancas")
def cobrancas(request: Request, competencia: str = "", situacao: str = ""):
    try:
        lista = consultas.listar_cobrancas(competencia or None, situacao or None)
    except ErroDeNegocio as erro:
        avisar(request, str(erro), "erro")
        lista = consultas.listar_cobrancas(situacao=situacao or None)
    return pagina(request, "cobrancas.html", cobrancas=lista, competencia=competencia, situacao=situacao,
                   total=sum(c["saldo_centavos"] for c in lista))


@app.get("/cobrancas/{cobranca_id}")
def cobranca(request: Request, cobranca_id: int):
    base = consultas.obter("cobranca", cobranca_id)
    extrato = consultas.extrato_contrato(base["contrato_id"])
    return pagina(request, "cobranca.html", c=next(c for c in extrato["cobrancas"] if c["id"] == cobranca_id),
                   contrato=extrato)


def _acao_cobranca(request, cobranca_id, funcao, sucesso):
    return acao(request, f"/cobrancas/{cobranca_id}", funcao, sucesso)


@app.post("/cobrancas/{cobranca_id}/valor")
async def cobranca_valor(request: Request, cobranca_id: int):
    form = await ler_form(request)
    return _acao_cobranca(request, cobranca_id, lambda: servicos.editar_valor_cobranca(
        quem(request), cobranca_id, centavos(form.get("valor")), form.get("motivo")), "Valor alterado.")


@app.post("/cobrancas/{cobranca_id}/isentar")
async def cobranca_isentar(request: Request, cobranca_id: int):
    form = await ler_form(request)
    return _acao_cobranca(request, cobranca_id, lambda: {"pendencias": [p for p in [servicos.isentar_cobranca(
        quem(request), cobranca_id, form.get("motivo"))] if p]}, "Cobrança isentada.")


@app.post("/cobrancas/{cobranca_id}/cancelar")
async def cobranca_cancelar(request: Request, cobranca_id: int):
    form = await ler_form(request)
    return _acao_cobranca(request, cobranca_id, lambda: {"pendencias": [p for p in [servicos.cancelar_cobranca(
        quem(request), cobranca_id, form.get("motivo"))] if p]}, "Cobrança cancelada.")


@app.post("/cobrancas/{cobranca_id}/boleto")
async def cobranca_boleto(request: Request, cobranca_id: int):
    form = await ler_form(request)
    return _acao_cobranca(request, cobranca_id, lambda: servicos.registrar_boleto(
        quem(request), cobranca_id, form.get("banco"), form.get("identificador"), form.get("linha_digitavel"),
        form.get("link"), substituir=form.get("substituir") == "on"), "Boleto registrado.")


@app.post("/cobrancas/{cobranca_id}/enviado")
def cobranca_enviado(request: Request, cobranca_id: int):
    return _acao_cobranca(request, cobranca_id, lambda: servicos.marcar_boleto_enviado(quem(request), cobranca_id),
                          "Boleto marcado como enviado.")


# --- PAGAMENTOS ---
def _cobrancas_para_pagar():
    return [c for c in consultas.listar_cobrancas() if c["situacao"] == "normal" and c["saldo_centavos"] > 0]


@app.get("/pagamentos/novo")
def pagamento_novo(request: Request, cobranca_id: str = ""):
    dados = {"cobranca_id": cobranca_id, "data_pagamento": regras.hoje().isoformat(), "forma": "pix"}
    return pagina(request, "pagamento_form.html", dados=dados, cobrancas=_cobrancas_para_pagar())


@app.post("/pagamentos/novo")
async def pagamento_novo_post(request: Request):
    form = await ler_form(request)
    login = quem(request)

    def registrar():
        if not form.get("cobranca_id"):
            raise ErroDeNegocio("Escolha a cobrança.")
        cobranca_id = int(form["cobranca_id"])
        valor = centavos(form.get("valor"), "valor pago")
        comprovante = None
        arquivo = form.get("comprovante")
        if arquivo is not None and getattr(arquivo, "filename", ""):
            cobranca = consultas.obter("cobranca", cobranca_id)
            comprovante = arquivos.salvar(arquivos.pasta("contrato", cobranca["contrato_id"]),
                                          f"comprovante-{cobranca['competencia']}", Path(arquivo.filename).suffix,
                                          arquivo.file.read())
        resultado = servicos.registrar_pagamento(
            login, cobranca_id, form.get("data_pagamento"), valor, form.get("forma"),
            identificador_externo=form.get("identificador_externo") or None, comprovante_caminho=comprovante,
            observacao=form.get("observacao"))
        for pendencia in resultado["pendencias"]:
            avisar(request, f"Pendência criada: {pendencia['descricao']}", "aviso")
        return resultado

    dados = {k: v for k, v in form.items() if isinstance(v, str)}
    return salvar_form(request, "pagamento_form.html", {"dados": dados, "cobrancas": _cobrancas_para_pagar()},
                        registrar, lambda r: f"/cobrancas/{r['cobranca_id']}", "Pagamento registrado.")


@app.get("/pagamentos")
def pagamentos(request: Request, data_de: str = "", data_ate: str = "", grupo: str = "", locatario_id: str = "",
               cancelados: str = ""):
    try:
        historico = consultas.historico_pagamentos(data_de or None, data_ate or None, grupo or None,
                                                   locatario_id=int_ou_none(locatario_id),
                                                   incluir_cancelados=cancelados == "on")
    except ErroDeNegocio as erro:
        avisar(request, str(erro), "erro")
        historico = consultas.historico_pagamentos()
    return pagina(request, "pagamentos.html", h=historico, grupos=consultas.grupos(),
                   locatarios=consultas.listar_locatarios(),
                   filtros=dict(data_de=data_de, data_ate=data_ate, grupo=grupo, locatario_id=locatario_id,
                                cancelados=cancelados))


@app.post("/pagamentos/{pagamento_id}/cancelar")
async def pagamento_cancelar(request: Request, pagamento_id: int):
    form = await ler_form(request)
    return acao(request, local(form.get("voltar"), "/pagamentos"),
                 lambda: servicos.cancelar_pagamento(quem(request), pagamento_id, form.get("motivo")),
                 "Pagamento cancelado.")


# --- PENDÊNCIAS E AUDITORIA ---
@app.get("/pendencias")
def pendencias(request: Request, todas: str = ""):
    return pagina(request, "pendencias.html", pendencias=consultas.listar_pendencias(abertas=not todas),
                   todas=todas)


@app.post("/pendencias/{pendencia_id}/resolver")
async def pendencia_resolver(request: Request, pendencia_id: int):
    form = await ler_form(request)
    return acao(request, "/pendencias", lambda: servicos.resolver_pendencia(
        quem(request), pendencia_id, form.get("resolucao")), "Pendência resolvida.")


@app.get("/auditoria")
def auditoria(request: Request, entidade: str = ""):
    return pagina(request, "auditoria.html", registros=consultas.auditoria(entidade or None, limite=200),
                   entidade=entidade)


# --- ARQUIVOS DA PASTA DE DOCUMENTOS ---
@app.get("/arquivo/{caminho:path}")
def arquivo(caminho: str):
    """Abre um arquivo da pasta de documentos (comprovantes e documentos dos módulos)."""
    absoluto = arquivos.caminho_absoluto(caminho)
    if not absoluto.is_file():
        raise ErroDeNegocio(f"O arquivo não está na pasta de documentos: {caminho}")
    return FileResponse(absoluto, filename=absoluto.name, content_disposition_type="inline")


# --- MÓDULOS OPCIONAIS (sistema/modulos/*/web.py) ---
for _nome in modulos.nomes():
    _web = modulos.carregar(_nome, "web")
    if _web is not None:
        app.include_router(_web.router)
