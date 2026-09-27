"""Todas as leituras e relatórios. Mesma saída para a web e para o Hermes.

Cada campo `*_centavos` vem acompanhado do mesmo valor já formatado, sem o
sufixo (ex.: `valor_centavos: 123456` e `valor: "R$ 1.234,56"`).
"""
from datetime import timedelta

from sistema import db, regras, servicos
from sistema.regras import ErroDeNegocio, para_data

ROTULOS_SITUACAO = {
    "paga": "Paga", "parcial": "Parcial", "em_aberto": "Em aberto", "atrasada": "Atrasada",
    "isenta": "Isenta", "cancelada": "Cancelada",
    "alugado": "Alugado", "vago": "Vago", "em_manutencao": "Em manutenção",
    "ativo": "Ativo", "encerrado": "Encerrado",
}


# --- AUXILIARES ---
def _hoje(hoje):
    return para_data(hoje) if hoje else regras.hoje()


def _com_reais(dados):
    for chave in list(dados):
        if chave.endswith("_centavos"):
            dados[chave.removesuffix("_centavos")] = regras.formatar_reais(dados[chave])
    return dados


def _dicts(linhas):
    return [dict(linha) for linha in linhas]


def _imovel_nome(linha):
    return f"{linha['grupo']} - {linha['unidade']}"


def obter(entidade, entidade_id):
    """Uma linha de uma tabela, como dict (para formulários de edição)."""
    tabelas = {"imovel": "imoveis", "locatario": "locatarios", "corretor": "corretores", "contrato": "contratos",
               "cobranca": "cobrancas", "pagamento": "pagamentos", "pendencia": "pendencias",
               "documento": "documentos"}
    if entidade not in tabelas:
        raise ErroDeNegocio(f"Entidade inválida: '{entidade}'.")
    with db.leitura() as con:
        linha = con.execute(f"SELECT * FROM {tabelas[entidade]} WHERE id = ?", (entidade_id,)).fetchone()
    if linha is None:
        raise ErroDeNegocio(f"{entidade.capitalize()} {entidade_id} não encontrado.")
    return _com_reais(dict(linha))


# --- CADASTROS ---
def listar_imoveis(situacao=None):
    with db.leitura() as con:
        linhas = con.execute(
            "SELECT i.*, c.id AS contrato_id, l.id AS locatario_id, l.nome AS locatario_nome "
            "FROM imoveis i LEFT JOIN contratos c ON c.imovel_id = i.id AND c.data_encerramento IS NULL "
            "LEFT JOIN locatarios l ON l.id = c.locatario_id ORDER BY i.grupo, i.unidade"
        ).fetchall()
    imoveis = []
    for linha in linhas:
        imovel = _com_reais(dict(linha))
        imovel["nome"] = _imovel_nome(linha)
        imovel["situacao"] = regras.situacao_imovel(linha["contrato_id"] is not None, linha["em_manutencao"])
        imovel["situacao_texto"] = ROTULOS_SITUACAO[imovel["situacao"]]
        if situacao is None or imovel["situacao"] == situacao:
            imoveis.append(imovel)
    return imoveis


def grupos():
    with db.leitura() as con:
        return [linha[0] for linha in con.execute("SELECT DISTINCT grupo FROM imoveis ORDER BY grupo")]


def listar_locatarios():
    with db.leitura() as con:
        return _dicts(con.execute(
            "SELECT l.*, (SELECT COUNT(*) FROM contratos c WHERE c.locatario_id = l.id "
            "AND c.data_encerramento IS NULL) AS contratos_ativos FROM locatarios l ORDER BY l.nome"
        ))


def buscar_locatarios(texto):
    """Busca por parte do nome ou do CPF/CNPJ."""
    texto = (texto or "").strip()
    digitos = regras.so_digitos(texto)
    with db.leitura() as con:
        return _dicts(con.execute(
            "SELECT l.*, (SELECT COUNT(*) FROM contratos c WHERE c.locatario_id = l.id "
            "AND c.data_encerramento IS NULL) AS contratos_ativos FROM locatarios l "
            "WHERE l.nome LIKE ? OR (? <> '' AND l.cpf_cnpj LIKE ?) ORDER BY l.nome",
            (f"%{texto}%", digitos, f"%{digitos}%"),
        ))


def listar_corretores():
    with db.leitura() as con:
        return _dicts(con.execute("SELECT * FROM corretores ORDER BY nome"))


def listar_usuarios():
    with db.leitura() as con:
        return _dicts(con.execute("SELECT id, login, nome, ativo FROM usuarios ORDER BY nome"))


def _documentos(con, entidade, entidade_id):
    return _dicts(con.execute(
        "SELECT * FROM documentos WHERE entidade = ? AND entidade_id = ? ORDER BY registrado_em",
        (entidade, entidade_id),
    ))


# --- CONTRATOS ---
_SQL_CONTRATOS = (
    "SELECT c.*, i.grupo, i.unidade, l.nome AS locatario_nome, l.cpf_cnpj AS locatario_cpf_cnpj, "
    "l.email AS locatario_email, l.telefone AS locatario_telefone, co.nome AS corretor_nome "
    "FROM contratos c JOIN imoveis i ON i.id = c.imovel_id JOIN locatarios l ON l.id = c.locatario_id "
    "LEFT JOIN corretores co ON co.id = c.corretor_id "
)


def _contrato(con, linha, hoje):
    contrato = _com_reais(dict(linha))
    contrato["imovel_nome"] = _imovel_nome(linha)
    contrato["status"] = "encerrado" if linha["data_encerramento"] else "ativo"
    contrato["status_texto"] = ROTULOS_SITUACAO[contrato["status"]]
    contrato["prazo_vencido"] = (not linha["data_encerramento"]
                                 and linha["data_fim_prevista"] < hoje.isoformat())
    valor = con.execute(
        "SELECT valor_centavos, vigente_desde FROM valores_aluguel WHERE contrato_id = ? "
        "AND vigente_desde <= ? ORDER BY vigente_desde DESC LIMIT 1",
        (linha["id"], max(hoje.isoformat(), linha["data_inicio"])),
    ).fetchone()
    contrato["valor_atual_centavos"] = valor["valor_centavos"] if valor else None
    contrato["valor_atual_desde"] = valor["vigente_desde"] if valor else None
    contrato["descricao"] = f"{contrato['imovel_nome']} — {linha['locatario_nome']}"
    return _com_reais(contrato)


def listar_contratos(ativos=True, hoje=None):
    """ativos=True: só ativos; False: só encerrados; None: todos."""
    hoje = _hoje(hoje)
    filtro = {True: "WHERE c.data_encerramento IS NULL ", False: "WHERE c.data_encerramento IS NOT NULL ",
              None: ""}[ativos]
    with db.leitura() as con:
        linhas = con.execute(_SQL_CONTRATOS + filtro + "ORDER BY i.grupo, i.unidade, c.data_inicio").fetchall()
        return [_contrato(con, linha, hoje) for linha in linhas]


# --- COBRANÇAS ---
_SQL_COBRANCAS = (
    "SELECT cb.*, c.imovel_id, c.locatario_id, c.multa_pct, c.juros_mes_pct, c.data_encerramento, "
    "i.grupo, i.unidade, l.nome AS locatario_nome, l.email AS locatario_email, "
    "l.cpf_cnpj AS locatario_cpf_cnpj, l.telefone AS locatario_telefone, "
    "COALESCE((SELECT SUM(p.valor_centavos) FROM pagamentos p WHERE p.cobranca_id = cb.id "
    "AND p.cancelado_em IS NULL), 0) AS pago_centavos "
    "FROM cobrancas cb JOIN contratos c ON c.id = cb.contrato_id JOIN imoveis i ON i.id = c.imovel_id "
    "JOIN locatarios l ON l.id = c.locatario_id "
)


def _cobranca(linha, hoje):
    cobranca = dict(linha)
    venc = para_data(linha["vencimento"])
    saldo = max(linha["valor_centavos"] - linha["pago_centavos"], 0)
    cobranca["imovel_nome"] = _imovel_nome(linha)
    cobranca["saldo_centavos"] = saldo if linha["situacao"] == "normal" else 0
    cobranca["situacao_calculada"] = regras.situacao_cobranca(
        linha["situacao"], linha["valor_centavos"], linha["pago_centavos"], venc, hoje)
    cobranca["situacao_texto"] = ROTULOS_SITUACAO[cobranca["situacao_calculada"]]
    cobranca["dias_atraso"] = 0
    cobranca["valor_atualizado_centavos"] = cobranca["saldo_centavos"]
    if cobranca["situacao_calculada"] == "atrasada":
        multa, juros = regras.encargos(saldo, linha["multa_pct"], linha["juros_mes_pct"], venc, hoje)
        cobranca["dias_atraso"] = (hoje - venc).days
        cobranca["encargos_centavos"] = multa + juros
        cobranca["valor_atualizado_centavos"] = saldo + multa + juros
    return _com_reais(cobranca)


def _cobrancas(con, hoje, where="", params=()):
    linhas = con.execute(_SQL_COBRANCAS + where + " ORDER BY cb.vencimento, i.grupo, i.unidade", params).fetchall()
    return [_cobranca(linha, hoje) for linha in linhas]


def listar_cobrancas(competencia=None, situacao=None, contrato_id=None, hoje=None):
    """situacao: paga, parcial, em_aberto, atrasada, isenta ou cancelada."""
    hoje = _hoje(hoje)
    servicos.gerar_cobrancas("sistema", hoje)
    condicoes, params = [], []
    if competencia:
        condicoes.append("cb.competencia = ?")
        params.append(regras.validar_competencia(competencia))
    if contrato_id:
        condicoes.append("cb.contrato_id = ?")
        params.append(contrato_id)
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    with db.leitura() as con:
        cobrancas = _cobrancas(con, hoje, where, tuple(params))
    if situacao:
        cobrancas = [c for c in cobrancas if c["situacao_calculada"] == situacao]
    return cobrancas


def cobrancas_sem_boleto(dias=10, hoje=None):
    """Cobranças com saldo, sem boleto, vencendo em até `dias` dias (ou já vencidas)."""
    hoje = _hoje(hoje)
    servicos.gerar_cobrancas("sistema", hoje)
    with db.leitura() as con:
        cobrancas = _cobrancas(con, hoje, "WHERE cb.situacao = 'normal' AND cb.boleto_identificador IS NULL "
                                          "AND cb.vencimento <= ?", ((hoje + timedelta(days=dias)).isoformat(),))
    return [c for c in cobrancas if c["saldo_centavos"] > 0]


def boletos_em_aberto(hoje=None):
    hoje = _hoje(hoje)
    with db.leitura() as con:
        cobrancas = _cobrancas(con, hoje, "WHERE cb.situacao = 'normal' AND cb.boleto_identificador IS NOT NULL")
    return [c for c in cobrancas if c["saldo_centavos"] > 0]


def inadimplentes(hoje=None):
    """Cobranças atrasadas de qualquer mês, agrupadas por contrato."""
    hoje = _hoje(hoje)
    servicos.gerar_cobrancas("sistema", hoje)
    with db.leitura() as con:
        atrasadas = [c for c in _cobrancas(con, hoje, "WHERE cb.situacao = 'normal'")
                     if c["situacao_calculada"] == "atrasada"]
    grupos_ = {}
    for c in atrasadas:
        grupo = grupos_.setdefault(c["contrato_id"], {
            "contrato_id": c["contrato_id"], "imovel_nome": c["imovel_nome"], "locatario_id": c["locatario_id"],
            "locatario_nome": c["locatario_nome"], "locatario_telefone": c["locatario_telefone"],
            "locatario_email": c["locatario_email"], "saldo_centavos": 0, "valor_atualizado_centavos": 0,
            "maior_atraso_dias": 0, "cobrancas": [],
        })
        grupo["saldo_centavos"] += c["saldo_centavos"]
        grupo["valor_atualizado_centavos"] += c["valor_atualizado_centavos"]
        grupo["maior_atraso_dias"] = max(grupo["maior_atraso_dias"], c["dias_atraso"])
        grupo["cobrancas"].append(c)
    return [_com_reais(g) for g in sorted(grupos_.values(), key=lambda g: -g["maior_atraso_dias"])]


def resumo_do_mes(competencia=None, hoje=None):
    hoje = _hoje(hoje)
    competencia = regras.validar_competencia(competencia) if competencia else regras.competencia_de(hoje)
    cobrancas = [c for c in listar_cobrancas(competencia=competencia, hoje=hoje) if c["situacao"] == "normal"]
    devido = sum(c["valor_centavos"] for c in cobrancas)
    recebido = sum(c["pago_centavos"] for c in cobrancas)
    falta = sum(c["saldo_centavos"] for c in cobrancas)
    return _com_reais({
        "competencia": competencia, "cobrancas": len(cobrancas), "devido_centavos": devido,
        "recebido_centavos": recebido, "falta_receber_centavos": falta,
        "pagas": sum(1 for c in cobrancas if c["situacao_calculada"] == "paga"),
    })


# --- FICHAS E EXTRATO ---
def ficha_imovel(imovel_id, hoje=None):
    hoje = _hoje(hoje)
    imovel = next((i for i in listar_imoveis() if i["id"] == int(imovel_id)), None)
    if imovel is None:
        raise ErroDeNegocio(f"Imóvel {imovel_id} não encontrado.")
    with db.leitura() as con:
        contratos = [_contrato(con, linha, hoje) for linha in con.execute(
            _SQL_CONTRATOS + "WHERE c.imovel_id = ? ORDER BY c.data_inicio DESC", (imovel_id,))]
        imovel["documentos"] = _documentos(con, "imovel", imovel_id)
    imovel["contrato_atual"] = next((c for c in contratos if c["status"] == "ativo"), None)
    imovel["contratos"] = contratos
    return imovel


def ficha_locatario(locatario_id, hoje=None):
    hoje = _hoje(hoje)
    servicos.gerar_cobrancas("sistema", hoje)
    with db.leitura() as con:
        linha = con.execute("SELECT * FROM locatarios WHERE id = ?", (locatario_id,)).fetchone()
        if linha is None:
            raise ErroDeNegocio(f"Locatário {locatario_id} não encontrado.")
        locatario = dict(linha)
        locatario["contratos"] = [_contrato(con, c, hoje) for c in con.execute(
            _SQL_CONTRATOS + "WHERE c.locatario_id = ? ORDER BY c.data_inicio DESC", (locatario_id,))]
        cobrancas = _cobrancas(con, hoje, "WHERE c.locatario_id = ? AND cb.situacao = 'normal'", (locatario_id,))
        locatario["documentos"] = _documentos(con, "locatario", locatario_id)
    locatario["total_atrasado_centavos"] = sum(
        c["saldo_centavos"] for c in cobrancas if c["situacao_calculada"] == "atrasada")
    locatario["total_atualizado_centavos"] = sum(
        c["valor_atualizado_centavos"] for c in cobrancas if c["situacao_calculada"] == "atrasada")
    locatario["total_a_vencer_centavos"] = sum(
        c["saldo_centavos"] for c in cobrancas if c["situacao_calculada"] in ("em_aberto", "parcial"))
    locatario["total_pago_centavos"] = sum(c["pago_centavos"] for c in cobrancas)
    return _com_reais(locatario)


def extrato_contrato(contrato_id, hoje=None):
    hoje = _hoje(hoje)
    servicos.gerar_cobrancas("sistema", hoje)
    with db.leitura() as con:
        linha = con.execute(_SQL_CONTRATOS + "WHERE c.id = ?", (contrato_id,)).fetchone()
        if linha is None:
            raise ErroDeNegocio(f"Contrato {contrato_id} não encontrado.")
        contrato = _contrato(con, linha, hoje)
        contrato["valores"] = [_com_reais(v) for v in _dicts(con.execute(
            "SELECT * FROM valores_aluguel WHERE contrato_id = ? ORDER BY vigente_desde", (contrato_id,)))]
        cobrancas = _cobrancas(con, hoje, "WHERE cb.contrato_id = ?", (contrato_id,))
        pagamentos = _dicts(con.execute(
            "SELECT p.* FROM pagamentos p JOIN cobrancas cb ON cb.id = p.cobranca_id WHERE cb.contrato_id = ? "
            "ORDER BY p.data_pagamento, p.id", (contrato_id,)))
        contrato["documentos"] = _documentos(con, "contrato", contrato_id)
    for cobranca in cobrancas:
        cobranca["pagamentos"] = [_com_reais(p) for p in pagamentos if p["cobranca_id"] == cobranca["id"]]
    contrato["cobrancas"] = cobrancas
    normais = [c for c in cobrancas if c["situacao"] == "normal"]
    contrato["total_devido_centavos"] = sum(c["valor_centavos"] for c in normais)
    contrato["total_pago_centavos"] = sum(c["pago_centavos"] for c in normais)
    contrato["total_atrasado_centavos"] = sum(
        c["saldo_centavos"] for c in normais if c["situacao_calculada"] == "atrasada")
    return _com_reais(contrato)


# --- PAINEL E ALERTAS ---
def alertas(hoje=None):
    hoje = _hoje(hoje)
    lista = []
    for c in listar_contratos(ativos=True, hoje=hoje):
        fim = para_data(c["data_fim_prevista"])
        if c["prazo_vencido"]:
            lista.append({"tipo": "prazo_vencido", "contrato_id": c["id"],
                          "mensagem": f"{c['descricao']}: prazo terminou em {fim:%d/%m/%Y}. Renovar ou encerrar."})
        elif fim <= hoje + timedelta(days=60):
            lista.append({"tipo": "contrato_a_vencer", "contrato_id": c["id"],
                          "mensagem": f"{c['descricao']}: contrato termina em {fim:%d/%m/%Y}."})
        if c["valor_atual_desde"]:
            reajuste = regras.somar_meses(para_data(c["valor_atual_desde"]), 12)
            if reajuste <= hoje + timedelta(days=30):
                lista.append({"tipo": "reajuste", "contrato_id": c["id"],
                              "mensagem": f"{c['descricao']}: reajuste anual devido em {reajuste:%d/%m/%Y} "
                                          f"(índice: {c['indice_reajuste'] or 'não informado'})."})
    for cb in cobrancas_sem_boleto(10, hoje):
        lista.append({"tipo": "sem_boleto", "contrato_id": cb["contrato_id"], "cobranca_id": cb["id"],
                      "mensagem": f"{cb['imovel_nome']} ({cb['locatario_nome']}): cobrança de {cb['competencia']} "
                                  f"vence em {para_data(cb['vencimento']):%d/%m/%Y} e está sem boleto."})
    for cb in boletos_em_aberto(hoje):
        if not cb["boleto_enviado_em"]:
            lista.append({"tipo": "boleto_nao_enviado", "contrato_id": cb["contrato_id"], "cobranca_id": cb["id"],
                          "mensagem": f"{cb['imovel_nome']} ({cb['locatario_nome']}): boleto de {cb['competencia']} "
                                      "emitido e ainda não enviado."})
    return lista


def recebido_por_mes(meses=12, hoje=None):
    """Total recebido (pagamentos válidos) por mês de pagamento, dos últimos `meses` meses."""
    hoje = _hoje(hoje)
    competencias = [regras.competencia_de(regras.somar_meses(hoje.replace(day=1), -i)) for i in range(meses - 1, -1, -1)]
    with db.leitura() as con:
        totais = dict(con.execute(
            "SELECT substr(data_pagamento, 1, 7), SUM(valor_centavos) FROM pagamentos WHERE cancelado_em IS NULL "
            "AND substr(data_pagamento, 1, 7) >= ? GROUP BY 1", (competencias[0],)).fetchall())
    return [_com_reais({"mes": c, "recebido_centavos": totais.get(c, 0)}) for c in competencias]


def painel(hoje=None):
    hoje = _hoje(hoje)
    imoveis = listar_imoveis()
    contagem = {s: sum(1 for i in imoveis if i["situacao"] == s) for s in ("alugado", "vago", "em_manutencao")}
    lista_inadimplentes = inadimplentes(hoje)
    with db.leitura() as con:
        pendencias = con.execute("SELECT COUNT(*) FROM pendencias WHERE resolvida_em IS NULL").fetchone()[0]
    return _com_reais({
        "data": hoje.isoformat(),
        "imoveis_total": len(imoveis),
        "imoveis_alugados": contagem["alugado"],
        "imoveis_vagos": contagem["vago"],
        "imoveis_em_manutencao": contagem["em_manutencao"],
        "ocupacao_pct": round(100 * contagem["alugado"] / len(imoveis)) if imoveis else 0,
        "resumo_do_mes": resumo_do_mes(hoje=hoje),
        "inadimplentes": lista_inadimplentes,
        "total_atrasado_centavos": sum(g["saldo_centavos"] for g in lista_inadimplentes),
        "alertas": alertas(hoje),
        "pendencias_abertas": pendencias,
    })


# --- PENDÊNCIAS, HISTÓRICO, AUDITORIA ---
def listar_pendencias(abertas=True):
    filtro = "WHERE resolvida_em IS NULL " if abertas else ""
    with db.leitura() as con:
        return _dicts(con.execute(f"SELECT * FROM pendencias {filtro}ORDER BY criada_em DESC, id DESC"))


def historico_pagamentos(data_de=None, data_ate=None, grupo=None, imovel_id=None, locatario_id=None,
                         incluir_cancelados=False):
    condicoes, params = [], []
    if not incluir_cancelados:
        condicoes.append("p.cancelado_em IS NULL")
    if data_de:
        condicoes.append("p.data_pagamento >= ?")
        params.append(para_data(data_de, "data inicial").isoformat())
    if data_ate:
        condicoes.append("p.data_pagamento <= ?")
        params.append(para_data(data_ate, "data final").isoformat())
    if grupo:
        condicoes.append("i.grupo = ?")
        params.append(grupo)
    if imovel_id:
        condicoes.append("i.id = ?")
        params.append(int(imovel_id))
    if locatario_id:
        condicoes.append("l.id = ?")
        params.append(int(locatario_id))
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    with db.leitura() as con:
        pagamentos = _dicts(con.execute(
            "SELECT p.*, cb.competencia, cb.contrato_id, i.grupo, i.unidade, l.nome AS locatario_nome "
            "FROM pagamentos p JOIN cobrancas cb ON cb.id = p.cobranca_id JOIN contratos c ON c.id = cb.contrato_id "
            "JOIN imoveis i ON i.id = c.imovel_id JOIN locatarios l ON l.id = c.locatario_id "
            f"{where} ORDER BY p.data_pagamento DESC, p.id DESC", tuple(params)))
    for p in pagamentos:
        p["imovel_nome"] = _imovel_nome(p)
        _com_reais(p)
    total = sum(p["valor_centavos"] for p in pagamentos if not p["cancelado_em"])
    return _com_reais({"pagamentos": pagamentos, "quantidade": len(pagamentos), "total_centavos": total})


def auditoria(entidade=None, entidade_id=None, limite=100):
    condicoes, params = [], []
    if entidade:
        condicoes.append("entidade = ?")
        params.append(entidade)
    if entidade_id:
        condicoes.append("entidade_id = ?")
        params.append(int(entidade_id))
    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""
    with db.leitura() as con:
        return _dicts(con.execute(f"SELECT * FROM auditoria {where} ORDER BY id DESC LIMIT ?",
                                  (*params, int(limite))))
