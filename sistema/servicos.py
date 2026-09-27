"""Todas as operações que gravam no banco. Única porta de escrita do sistema.

A web e o MCP (Hermes) chamam estas mesmas funções. Regras:
- o primeiro argumento é `quem` (login da pessoa ou 'hermes');
- erro de regra levanta `ErroDeNegocio` com mensagem clara;
- cada gravação entra na auditoria, na mesma transação;
- dinheiro sempre em centavos (inteiro).
"""
import json
import sqlite3
from datetime import timedelta
from pathlib import Path, PurePosixPath

import bcrypt

from sistema import config, db, regras
from sistema.regras import ErroDeNegocio, para_data

FORMAS_PAGAMENTO = ("boleto", "pix", "transferencia", "dinheiro", "outro")
TIPOS_GARANTIA = ("caucao", "fiador", "seguro_fianca", "nenhuma")
ENTIDADES_DOCUMENTO = ("imovel", "locatario", "contrato")
# Documentos com nome de arquivo fixo dentro da pasta (ver docs/estrutura-de-pastas.md).
NOMES_FIXOS = ("contrato-assinado", "vistoria-entrada", "vistoria-saida")
TOLERANCIA_CENTAVOS = 100  # diferença até R$ 1,00 não vira pendência


# --- AUXILIARES ---
def _auditar(con, quem, acao, entidade=None, entidade_id=None, **detalhes):
    con.execute(
        "INSERT INTO auditoria (quando, quem, acao, entidade, entidade_id, detalhes) VALUES (?, ?, ?, ?, ?, ?)",
        (regras.agora(), quem, acao, entidade, entidade_id,
         json.dumps(detalhes, ensure_ascii=False, default=str) if detalhes else None),
    )


def _obter(con, tabela, id_, nome):
    linha = con.execute(f"SELECT * FROM {tabela} WHERE id = ?", (id_,)).fetchone()
    if linha is None:
        raise ErroDeNegocio(f"{nome} {id_} não encontrado.")
    return linha


def _texto(valor):
    texto = str(valor).strip() if valor is not None else ""
    return texto or None


def _obrigatorio(valor, campo):
    texto = _texto(valor)
    if not texto:
        raise ErroDeNegocio(f"Preencha o campo {campo}.")
    return texto


def _email(valor):
    email = _obrigatorio(valor, "e-mail")
    if "@" not in email:
        raise ErroDeNegocio(f"E-mail inválido: '{email}'.")
    return email


def _data_iso(valor, campo):
    return para_data(valor, campo).isoformat()


def _valor_positivo(centavos, campo="valor"):
    if centavos is None or int(centavos) <= 0:
        raise ErroDeNegocio(f"O {campo} precisa ser maior que zero.")
    return int(centavos)


def _atualizar(con, tabela, id_, campos):
    if not campos:
        return
    sets = ", ".join(f"{c} = ?" for c in campos)
    con.execute(f"UPDATE {tabela} SET {sets} WHERE id = ?", (*campos.values(), id_))


def _tem_contratos(con, coluna, id_):
    return con.execute(f"SELECT 1 FROM contratos WHERE {coluna} = ? LIMIT 1", (id_,)).fetchone() is not None


def _pago(con, cobranca_id):
    return con.execute(
        "SELECT COALESCE(SUM(valor_centavos), 0) FROM pagamentos WHERE cobranca_id = ? AND cancelado_em IS NULL",
        (cobranca_id,),
    ).fetchone()[0]


def _contrato_ativo(con, contrato_id):
    contrato = _obter(con, "contratos", contrato_id, "Contrato")
    if contrato["data_encerramento"]:
        raise ErroDeNegocio(f"O contrato {contrato_id} está encerrado desde {contrato['data_encerramento']}.")
    return contrato


def _nova_pendencia(con, quem, tipo, descricao, entidade=None, entidade_id=None):
    cur = con.execute(
        "INSERT INTO pendencias (tipo, descricao, entidade, entidade_id, criada_em, criada_por) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tipo, descricao, entidade, entidade_id, regras.agora(), quem),
    )
    _auditar(con, quem, "criar_pendencia", "pendencia", cur.lastrowid, tipo=tipo, descricao=descricao)
    return {"pendencia_id": cur.lastrowid, "tipo": tipo, "descricao": descricao}


def _rotulo_cobranca(con, cobranca):
    linha = con.execute(
        "SELECT i.grupo, i.unidade, l.nome FROM contratos c JOIN imoveis i ON i.id = c.imovel_id "
        "JOIN locatarios l ON l.id = c.locatario_id WHERE c.id = ?",
        (cobranca["contrato_id"],),
    ).fetchone()
    return f"{linha['grupo']} - {linha['unidade']} ({linha['nome']}), competência {cobranca['competencia']}"


# --- IMÓVEIS ---
_CAMPOS_IMOVEL = ("grupo", "unidade", "endereco", "em_manutencao", "iptu_anual_centavos",
                  "medidor_saneago", "medidor_enel", "observacoes")


def _campos_imovel(dados):
    campos = {}
    for campo in _CAMPOS_IMOVEL:
        if campo not in dados:
            continue
        valor = dados[campo]
        if campo in ("grupo", "unidade", "endereco"):
            valor = _obrigatorio(valor, campo)
        elif campo == "em_manutencao":
            valor = 1 if valor else 0
        elif campo == "iptu_anual_centavos":
            valor = int(valor) if valor not in (None, "") else None
        else:
            valor = _texto(valor)
        campos[campo] = valor
    return campos


def _erro_imovel_duplicado(campos):
    return ErroDeNegocio(f"Já existe o imóvel '{campos.get('grupo')} - {campos.get('unidade')}'.")


def cadastrar_imovel(quem, grupo, unidade, endereco, iptu_anual_centavos=None, medidor_saneago=None,
                     medidor_enel=None, observacoes=None, em_manutencao=False):
    campos = _campos_imovel(dict(
        grupo=grupo, unidade=unidade, endereco=endereco, iptu_anual_centavos=iptu_anual_centavos,
        medidor_saneago=medidor_saneago, medidor_enel=medidor_enel, observacoes=observacoes,
        em_manutencao=em_manutencao,
    ))
    try:
        with db.transacao() as con:
            cur = con.execute(
                f"INSERT INTO imoveis ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
                tuple(campos.values()),
            )
            _auditar(con, quem, "cadastrar_imovel", "imovel", cur.lastrowid, **campos)
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise _erro_imovel_duplicado(campos) from None


def atualizar_imovel(quem, imovel_id, **dados):
    campos = _campos_imovel(dados)
    try:
        with db.transacao() as con:
            _obter(con, "imoveis", imovel_id, "Imóvel")
            _atualizar(con, "imoveis", imovel_id, campos)
            _auditar(con, quem, "atualizar_imovel", "imovel", imovel_id, **campos)
    except sqlite3.IntegrityError:
        raise _erro_imovel_duplicado(campos) from None


def apagar_imovel(quem, imovel_id):
    with db.transacao() as con:
        imovel = _obter(con, "imoveis", imovel_id, "Imóvel")
        if _tem_contratos(con, "imovel_id", imovel_id):
            raise ErroDeNegocio("Esse imóvel tem contratos e não pode ser apagado.")
        con.execute("DELETE FROM documentos WHERE entidade = 'imovel' AND entidade_id = ?", (imovel_id,))
        con.execute("DELETE FROM imoveis WHERE id = ?", (imovel_id,))
        _auditar(con, quem, "apagar_imovel", "imovel", imovel_id, **dict(imovel))


# --- LOCATÁRIOS ---
_CAMPOS_LOCATARIO = ("nome", "cpf_cnpj", "telefone", "email", "observacoes")


def _campos_locatario(dados):
    campos = {}
    for campo in _CAMPOS_LOCATARIO:
        if campo not in dados:
            continue
        valor = dados[campo]
        if campo == "nome":
            valor = _obrigatorio(valor, "nome")
        elif campo == "cpf_cnpj":
            valor = regras.validar_cpf_cnpj(valor)
        elif campo == "email":
            valor = _email(valor)
        else:
            valor = _texto(valor)
        campos[campo] = valor
    return campos


def _erro_cpf_duplicado(cpf):
    return ErroDeNegocio(f"Já existe um locatário com o CPF/CNPJ {cpf}.")


def cadastrar_locatario(quem, nome, cpf_cnpj, email, telefone=None, observacoes=None):
    campos = _campos_locatario(dict(nome=nome, cpf_cnpj=cpf_cnpj, email=email, telefone=telefone,
                                    observacoes=observacoes))
    try:
        with db.transacao() as con:
            cur = con.execute(
                f"INSERT INTO locatarios ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
                tuple(campos.values()),
            )
            _auditar(con, quem, "cadastrar_locatario", "locatario", cur.lastrowid, **campos)
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise _erro_cpf_duplicado(campos["cpf_cnpj"]) from None


def atualizar_locatario(quem, locatario_id, **dados):
    campos = _campos_locatario(dados)
    try:
        with db.transacao() as con:
            _obter(con, "locatarios", locatario_id, "Locatário")
            _atualizar(con, "locatarios", locatario_id, campos)
            _auditar(con, quem, "atualizar_locatario", "locatario", locatario_id, **campos)
    except sqlite3.IntegrityError:
        raise _erro_cpf_duplicado(campos.get("cpf_cnpj")) from None


def apagar_locatario(quem, locatario_id):
    with db.transacao() as con:
        locatario = _obter(con, "locatarios", locatario_id, "Locatário")
        if _tem_contratos(con, "locatario_id", locatario_id):
            raise ErroDeNegocio("Esse locatário tem contratos e não pode ser apagado.")
        con.execute("DELETE FROM documentos WHERE entidade = 'locatario' AND entidade_id = ?", (locatario_id,))
        con.execute("DELETE FROM locatarios WHERE id = ?", (locatario_id,))
        _auditar(con, quem, "apagar_locatario", "locatario", locatario_id, **dict(locatario))


# --- CORRETORES ---
_CAMPOS_CORRETOR = ("nome", "telefone", "email", "observacoes")


def _campos_corretor(dados):
    return {c: (_obrigatorio(dados[c], "nome") if c == "nome" else _texto(dados[c]))
            for c in _CAMPOS_CORRETOR if c in dados}


def cadastrar_corretor(quem, nome, telefone=None, email=None, observacoes=None):
    campos = _campos_corretor(dict(nome=nome, telefone=telefone, email=email, observacoes=observacoes))
    with db.transacao() as con:
        cur = con.execute(
            f"INSERT INTO corretores ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
            tuple(campos.values()),
        )
        _auditar(con, quem, "cadastrar_corretor", "corretor", cur.lastrowid, **campos)
        return cur.lastrowid


def atualizar_corretor(quem, corretor_id, **dados):
    campos = _campos_corretor(dados)
    with db.transacao() as con:
        _obter(con, "corretores", corretor_id, "Corretor")
        _atualizar(con, "corretores", corretor_id, campos)
        _auditar(con, quem, "atualizar_corretor", "corretor", corretor_id, **campos)


def apagar_corretor(quem, corretor_id):
    with db.transacao() as con:
        corretor = _obter(con, "corretores", corretor_id, "Corretor")
        if _tem_contratos(con, "corretor_id", corretor_id):
            raise ErroDeNegocio("Esse corretor tem contratos e não pode ser apagado.")
        con.execute("DELETE FROM corretores WHERE id = ?", (corretor_id,))
        _auditar(con, quem, "apagar_corretor", "corretor", corretor_id, **dict(corretor))


# --- CONTRATOS ---
def _campos_contrato_editaveis(dados):
    campos = {}
    for campo, valor in dados.items():
        if campo == "corretor_id":
            campos[campo] = int(valor) if valor not in (None, "") else None
        elif campo == "garantia_tipo":
            if valor not in TIPOS_GARANTIA:
                raise ErroDeNegocio(f"Tipo de garantia inválido: '{valor}'. Use: {', '.join(TIPOS_GARANTIA)}.")
            campos[campo] = valor
        elif campo == "garantia_valor_centavos":
            campos[campo] = int(valor) if valor not in (None, "") else None
        elif campo in ("multa_pct", "juros_mes_pct"):
            if valor is None or float(valor) < 0:
                raise ErroDeNegocio(f"Percentual inválido em {campo}.")
            campos[campo] = float(valor)
        elif campo in ("fiador", "indice_reajuste", "observacoes"):
            campos[campo] = _texto(valor)
        else:
            raise ErroDeNegocio(f"O campo '{campo}' não pode ser alterado por aqui.")
    return campos


def criar_contrato(quem, imovel_id, locatario_id, data_inicio, data_fim_prevista, dia_vencimento,
                   valor_centavos, corretor_id=None, multa_pct=2, juros_mes_pct=1, garantia_tipo="nenhuma",
                   garantia_valor_centavos=None, fiador=None, indice_reajuste=None, observacoes=None):
    inicio = para_data(data_inicio, "data de início")
    fim = para_data(data_fim_prevista, "data de fim prevista")
    if fim <= inicio:
        raise ErroDeNegocio("A data de fim prevista precisa ser depois da data de início.")
    dia = int(dia_vencimento)
    if not 1 <= dia <= 31:
        raise ErroDeNegocio("O dia de vencimento precisa estar entre 1 e 31.")
    valor = _valor_positivo(valor_centavos, "valor do aluguel")
    extras = _campos_contrato_editaveis(dict(
        corretor_id=corretor_id, multa_pct=multa_pct, juros_mes_pct=juros_mes_pct, garantia_tipo=garantia_tipo,
        garantia_valor_centavos=garantia_valor_centavos, fiador=fiador, indice_reajuste=indice_reajuste,
        observacoes=observacoes,
    ))
    with db.transacao() as con:
        imovel = _obter(con, "imoveis", imovel_id, "Imóvel")
        _obter(con, "locatarios", locatario_id, "Locatário")
        if extras["corretor_id"] is not None:
            _obter(con, "corretores", extras["corretor_id"], "Corretor")
        ativo = con.execute(
            "SELECT id FROM contratos WHERE imovel_id = ? AND data_encerramento IS NULL", (imovel_id,)
        ).fetchone()
        if ativo:
            raise ErroDeNegocio(
                f"O imóvel '{imovel['grupo']} - {imovel['unidade']}' já tem um contrato ativo "
                f"(contrato {ativo['id']}). Encerre-o antes de criar outro."
            )
        campos = dict(imovel_id=imovel_id, locatario_id=locatario_id, data_inicio=inicio.isoformat(),
                      data_fim_prevista=fim.isoformat(), dia_vencimento=dia, **extras)
        cur = con.execute(
            f"INSERT INTO contratos ({', '.join(campos)}) VALUES ({', '.join('?' * len(campos))})",
            tuple(campos.values()),
        )
        contrato_id = cur.lastrowid
        con.execute(
            "INSERT INTO valores_aluguel (contrato_id, valor_centavos, vigente_desde, motivo) VALUES (?, ?, ?, ?)",
            (contrato_id, valor, inicio.isoformat(), "inicial"),
        )
        _auditar(con, quem, "criar_contrato", "contrato", contrato_id, valor_centavos=valor, **campos)
    gerar_cobrancas("sistema")
    return contrato_id


def atualizar_contrato(quem, contrato_id, **dados):
    """Só campos que não mexem em datas nem valores de cobrança."""
    campos = _campos_contrato_editaveis(dados)
    with db.transacao() as con:
        _obter(con, "contratos", contrato_id, "Contrato")
        if campos.get("corretor_id") is not None:
            _obter(con, "corretores", campos["corretor_id"], "Corretor")
        _atualizar(con, "contratos", contrato_id, campos)
        _auditar(con, quem, "atualizar_contrato", "contrato", contrato_id, **campos)


def _registrar_reajuste(con, quem, contrato_id, novo_valor_centavos, vigente_desde, motivo):
    valor = _valor_positivo(novo_valor_centavos, "novo valor")
    desde = para_data(vigente_desde, "data de vigência").isoformat()
    ultimo = con.execute(
        "SELECT MAX(vigente_desde) FROM valores_aluguel WHERE contrato_id = ?", (contrato_id,)
    ).fetchone()[0]
    if ultimo and desde <= ultimo:
        raise ErroDeNegocio(f"O novo valor precisa valer a partir de uma data depois de {ultimo}.")
    con.execute(
        "INSERT INTO valores_aluguel (contrato_id, valor_centavos, vigente_desde, motivo) VALUES (?, ?, ?, ?)",
        (contrato_id, valor, desde, _texto(motivo) or "reajuste"),
    )
    # Cobranças futuras ainda "intocadas" passam a ter o valor novo.
    cur = con.execute(
        "UPDATE cobrancas SET valor_centavos = ? WHERE contrato_id = ? AND situacao = 'normal' "
        "AND boleto_identificador IS NULL AND vencimento >= ? AND NOT EXISTS ("
        "  SELECT 1 FROM pagamentos p WHERE p.cobranca_id = cobrancas.id AND p.cancelado_em IS NULL)",
        (valor, contrato_id, desde),
    )
    _auditar(con, quem, "registrar_reajuste", "contrato", contrato_id, valor_centavos=valor,
             vigente_desde=desde, motivo=motivo, cobrancas_atualizadas=cur.rowcount)


def registrar_reajuste(quem, contrato_id, novo_valor_centavos, vigente_desde, motivo=None):
    with db.transacao() as con:
        _contrato_ativo(con, contrato_id)
        _registrar_reajuste(con, quem, contrato_id, novo_valor_centavos, vigente_desde, motivo)
    gerar_cobrancas("sistema")


def renovar_contrato(quem, contrato_id, nova_data_fim, novo_valor_centavos=None, vigente_desde=None, motivo=None):
    """Renovação = nova data de fim no mesmo contrato (e, se vier, novo valor)."""
    nova_fim = para_data(nova_data_fim, "nova data de fim")
    with db.transacao() as con:
        contrato = _contrato_ativo(con, contrato_id)
        fim_atual = para_data(contrato["data_fim_prevista"])
        if nova_fim <= fim_atual:
            raise ErroDeNegocio(f"A nova data de fim precisa ser depois da atual ({fim_atual.isoformat()}).")
        con.execute("UPDATE contratos SET data_fim_prevista = ? WHERE id = ?", (nova_fim.isoformat(), contrato_id))
        _auditar(con, quem, "renovar_contrato", "contrato", contrato_id,
                 data_fim_anterior=fim_atual.isoformat(), nova_data_fim=nova_fim.isoformat())
        if novo_valor_centavos:
            desde = vigente_desde or (fim_atual + timedelta(days=1))
            _registrar_reajuste(con, quem, contrato_id, novo_valor_centavos, desde, motivo or "renovação")
    gerar_cobrancas("sistema")


def encerrar_contrato(quem, contrato_id, data_encerramento, motivo):
    data = para_data(data_encerramento, "data de encerramento")
    motivo = _obrigatorio(motivo, "motivo do encerramento")
    # Gera o que faltava até hoje antes de encerrar, para o encerramento enxergar tudo.
    gerar_cobrancas("sistema")
    with db.transacao() as con:
        contrato = _contrato_ativo(con, contrato_id)
        if data < para_data(contrato["data_inicio"]):
            raise ErroDeNegocio("A data de encerramento não pode ser antes do início do contrato.")
        con.execute(
            "UPDATE contratos SET data_encerramento = ?, motivo_encerramento = ? WHERE id = ?",
            (data.isoformat(), motivo, contrato_id),
        )
        futuras = con.execute(
            "SELECT * FROM cobrancas c WHERE contrato_id = ? AND situacao = 'normal' AND vencimento > ? "
            "AND NOT EXISTS (SELECT 1 FROM pagamentos p WHERE p.cobranca_id = c.id AND p.cancelado_em IS NULL)",
            (contrato_id, data.isoformat()),
        ).fetchall()
        pendencias = []
        for cobranca in futuras:
            con.execute(
                "UPDATE cobrancas SET situacao = 'cancelada', motivo_situacao = 'contrato encerrado' WHERE id = ?",
                (cobranca["id"],),
            )
            if cobranca["boleto_identificador"]:
                pendencias.append(_nova_pendencia(
                    con, quem, "cancelar_boleto",
                    f"Cancelar no banco o boleto {cobranca['boleto_identificador']} "
                    f"({_rotulo_cobranca(con, cobranca)}): o contrato foi encerrado.",
                    "cobranca", cobranca["id"],
                ))
        _auditar(con, quem, "encerrar_contrato", "contrato", contrato_id, data_encerramento=data.isoformat(),
                 motivo=motivo, cobrancas_canceladas=[c["id"] for c in futuras])
    return {"cobrancas_canceladas": len(futuras), "pendencias": pendencias}


def apagar_contrato(quem, contrato_id):
    """Só para contrato cadastrado por engano: sem pagamento, sem boleto e sem documento."""
    with db.transacao() as con:
        contrato = _obter(con, "contratos", contrato_id, "Contrato")
        if con.execute(
            "SELECT 1 FROM pagamentos p JOIN cobrancas c ON c.id = p.cobranca_id WHERE c.contrato_id = ?",
            (contrato_id,),
        ).fetchone():
            raise ErroDeNegocio("Esse contrato tem pagamentos e não pode ser apagado. Encerre-o.")
        if con.execute(
            "SELECT 1 FROM cobrancas WHERE contrato_id = ? AND boleto_identificador IS NOT NULL", (contrato_id,)
        ).fetchone():
            raise ErroDeNegocio("Esse contrato tem boleto emitido e não pode ser apagado. Encerre-o.")
        if con.execute(
            "SELECT 1 FROM documentos WHERE entidade = 'contrato' AND entidade_id = ?", (contrato_id,)
        ).fetchone():
            raise ErroDeNegocio("Esse contrato tem documentos e não pode ser apagado. Encerre-o.")
        con.execute("DELETE FROM cobrancas WHERE contrato_id = ?", (contrato_id,))
        con.execute("DELETE FROM valores_aluguel WHERE contrato_id = ?", (contrato_id,))
        con.execute("DELETE FROM contratos WHERE id = ?", (contrato_id,))
        _auditar(con, quem, "apagar_contrato", "contrato", contrato_id, **dict(contrato))


# --- COBRANÇAS ---
def _valor_vigente(con, contrato_id, data_iso):
    linha = con.execute(
        "SELECT valor_centavos FROM valores_aluguel WHERE contrato_id = ? AND vigente_desde <= ? "
        "ORDER BY vigente_desde DESC LIMIT 1",
        (contrato_id, data_iso),
    ).fetchone()
    return linha[0] if linha else None


def gerar_cobrancas(quem="sistema", hoje=None):
    """Cria as cobranças que faltam, até 30 dias à frente. Rodar de novo não duplica nada."""
    limite = (para_data(hoje) if hoje else regras.hoje()) + timedelta(days=30)
    criadas = []
    with db.transacao() as con:
        for contrato in con.execute("SELECT * FROM contratos").fetchall():
            dia = contrato["dia_vencimento"]
            fim = para_data(contrato["data_encerramento"]) if contrato["data_encerramento"] else None
            competencia = regras.primeira_competencia(para_data(contrato["data_inicio"]), dia,
                                                      config.INICIO_COBRANCAS)
            while True:
                venc = regras.vencimento(competencia, dia)
                if venc > limite or (fim and venc > fim):
                    break
                valor = _valor_vigente(con, contrato["id"], venc.isoformat())
                if valor:
                    cur = con.execute(
                        "INSERT OR IGNORE INTO cobrancas (contrato_id, competencia, vencimento, valor_centavos) "
                        "VALUES (?, ?, ?, ?)",
                        (contrato["id"], competencia, venc.isoformat(), valor),
                    )
                    if cur.rowcount:
                        criadas.append(cur.lastrowid)
                competencia = regras.proxima_competencia(competencia)
        if criadas:
            _auditar(con, quem, "gerar_cobrancas", "cobranca", None, cobrancas=criadas)
    return len(criadas)


def _cobranca_sem_movimento(con, cobranca_id, acao):
    cobranca = _obter(con, "cobrancas", cobranca_id, "Cobrança")
    if cobranca["situacao"] != "normal":
        raise ErroDeNegocio(f"Essa cobrança está {cobranca['situacao']}.")
    if _pago(con, cobranca_id):
        raise ErroDeNegocio(f"Essa cobrança já tem pagamento; não é possível {acao}. Cancele o pagamento antes.")
    return cobranca


def editar_valor_cobranca(quem, cobranca_id, valor_centavos, motivo):
    valor = _valor_positivo(valor_centavos)
    motivo = _obrigatorio(motivo, "motivo")
    with db.transacao() as con:
        cobranca = _cobranca_sem_movimento(con, cobranca_id, "mudar o valor")
        if cobranca["boleto_identificador"]:
            raise ErroDeNegocio("Essa cobrança já tem boleto. Emita um boleto novo com o valor certo e "
                                "registre-o como substituto.")
        con.execute("UPDATE cobrancas SET valor_centavos = ? WHERE id = ?", (valor, cobranca_id))
        _auditar(con, quem, "editar_valor_cobranca", "cobranca", cobranca_id,
                 valor_anterior=cobranca["valor_centavos"], valor_centavos=valor, motivo=motivo)


def _mudar_situacao(quem, cobranca_id, nova, motivo):
    motivo = _obrigatorio(motivo, "motivo")
    verbo = "isentar" if nova == "isenta" else "cancelar"
    with db.transacao() as con:
        cobranca = _cobranca_sem_movimento(con, cobranca_id, verbo)
        con.execute("UPDATE cobrancas SET situacao = ?, motivo_situacao = ? WHERE id = ?",
                    (nova, motivo, cobranca_id))
        _auditar(con, quem, f"{verbo}_cobranca", "cobranca", cobranca_id, motivo=motivo)
        if cobranca["boleto_identificador"]:
            return _nova_pendencia(
                con, quem, "cancelar_boleto",
                f"Cancelar no banco o boleto {cobranca['boleto_identificador']} "
                f"({_rotulo_cobranca(con, cobranca)}): a cobrança foi {nova}.",
                "cobranca", cobranca_id,
            )
    return None


def isentar_cobranca(quem, cobranca_id, motivo):
    return _mudar_situacao(quem, cobranca_id, "isenta", motivo)


def cancelar_cobranca(quem, cobranca_id, motivo):
    return _mudar_situacao(quem, cobranca_id, "cancelada", motivo)


# --- BOLETOS ---
def registrar_boleto(quem, cobranca_id, banco, identificador, linha_digitavel=None, link=None, substituir=False):
    banco = _obrigatorio(banco, "banco")
    identificador = _obrigatorio(identificador, "identificador do boleto")
    try:
        with db.transacao() as con:
            cobranca = _obter(con, "cobrancas", cobranca_id, "Cobrança")
            if cobranca["boleto_identificador"] == identificador:
                return {"cobranca_id": cobranca_id, "ja_existia": True}
            if cobranca["situacao"] != "normal":
                raise ErroDeNegocio(f"Essa cobrança está {cobranca['situacao']}; não precisa de boleto.")
            if _pago(con, cobranca_id) >= cobranca["valor_centavos"]:
                raise ErroDeNegocio("Essa cobrança já está paga.")
            if cobranca["boleto_identificador"] and not substituir:
                raise ErroDeNegocio(
                    f"Essa cobrança já tem o boleto {cobranca['boleto_identificador']}. "
                    "Se for segunda via, registre de novo com substituir=verdadeiro."
                )
            con.execute(
                "UPDATE cobrancas SET boleto_banco = ?, boleto_identificador = ?, boleto_linha_digitavel = ?, "
                "boleto_link = ?, boleto_emitido_em = ?, boleto_enviado_em = NULL WHERE id = ?",
                (banco, identificador, _texto(linha_digitavel), _texto(link), regras.agora(), cobranca_id),
            )
            _auditar(con, quem, "registrar_boleto", "cobranca", cobranca_id, banco=banco,
                     identificador=identificador, boleto_anterior=cobranca["boleto_identificador"])
            return {"cobranca_id": cobranca_id, "ja_existia": False}
    except sqlite3.IntegrityError:
        raise ErroDeNegocio(f"O boleto {identificador} já está registrado em outra cobrança.") from None


def marcar_boleto_enviado(quem, cobranca_id):
    with db.transacao() as con:
        cobranca = _obter(con, "cobrancas", cobranca_id, "Cobrança")
        if not cobranca["boleto_identificador"]:
            raise ErroDeNegocio("Essa cobrança ainda não tem boleto registrado.")
        con.execute("UPDATE cobrancas SET boleto_enviado_em = ? WHERE id = ?", (regras.agora(), cobranca_id))
        _auditar(con, quem, "marcar_boleto_enviado", "cobranca", cobranca_id,
                 identificador=cobranca["boleto_identificador"])


# --- PAGAMENTOS ---
def registrar_pagamento(quem, cobranca_id, data_pagamento, valor_centavos, forma, identificador_externo=None,
                        comprovante_caminho=None, observacao=None):
    """Registra o dinheiro que entrou. Se algo não bate, registra mesmo assim e cria pendência."""
    data = para_data(data_pagamento, "data do pagamento")
    valor = _valor_positivo(valor_centavos, "valor pago")
    if forma not in FORMAS_PAGAMENTO:
        raise ErroDeNegocio(f"Forma de pagamento inválida: '{forma}'. Use: {', '.join(FORMAS_PAGAMENTO)}.")
    identificador_externo = _texto(identificador_externo)
    comprovante = _caminho_relativo(comprovante_caminho, exigir_arquivo=True) if _texto(comprovante_caminho) else None
    with db.transacao() as con:
        if identificador_externo:
            existente = con.execute(
                "SELECT id, cobranca_id FROM pagamentos WHERE identificador_externo = ? AND cancelado_em IS NULL",
                (identificador_externo,),
            ).fetchone()
            if existente:
                return {"pagamento_id": existente["id"], "cobranca_id": existente["cobranca_id"],
                        "ja_existia": True, "pendencias": []}
        cobranca = _obter(con, "cobrancas", cobranca_id, "Cobrança")
        if cobranca["situacao"] != "normal":
            raise ErroDeNegocio(f"Essa cobrança está {cobranca['situacao']}; não recebe pagamento.")
        contrato = _obter(con, "contratos", cobranca["contrato_id"], "Contrato")
        saldo = cobranca["valor_centavos"] - _pago(con, cobranca_id)
        multa, juros = regras.encargos(max(saldo, 0), contrato["multa_pct"], contrato["juros_mes_pct"],
                                       para_data(cobranca["vencimento"]), data)
        esperado = max(saldo, 0) + multa + juros
        cur = con.execute(
            "INSERT INTO pagamentos (cobranca_id, data_pagamento, valor_centavos, forma, identificador_externo, "
            "comprovante_caminho, observacao, registrado_por, registrado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cobranca_id, data.isoformat(), valor, forma, identificador_externo, comprovante,
             _texto(observacao), quem, regras.agora()),
        )
        pagamento_id = cur.lastrowid
        _auditar(con, quem, "registrar_pagamento", "pagamento", pagamento_id, cobranca_id=cobranca_id,
                 valor_centavos=valor, data_pagamento=data.isoformat(), forma=forma,
                 identificador_externo=identificador_externo)
        rotulo = _rotulo_cobranca(con, cobranca)
        pendencias = []
        if saldo <= 0:
            pendencias.append(_nova_pendencia(
                con, quem, "possivel_duplicidade",
                f"Pagamento de {regras.formatar_reais(valor)} registrado em cobrança que já estava paga: {rotulo}.",
                "pagamento", pagamento_id,
            ))
        elif abs(valor - esperado) > TOLERANCIA_CENTAVOS:
            detalhe = f"saldo {regras.formatar_reais(saldo)}"
            if multa or juros:
                detalhe += f" + multa e juros {regras.formatar_reais(multa + juros)}"
            pendencias.append(_nova_pendencia(
                con, quem, "pagamento_divergente",
                f"Pago {regras.formatar_reais(valor)}, esperado {regras.formatar_reais(esperado)} ({detalhe}): "
                f"{rotulo}.",
                "pagamento", pagamento_id,
            ))
        if contrato["data_encerramento"]:
            pendencias.append(_nova_pendencia(
                con, quem, "contrato_encerrado",
                f"Pagamento de {regras.formatar_reais(valor)} em contrato encerrado: {rotulo}.",
                "pagamento", pagamento_id,
            ))
        return {"pagamento_id": pagamento_id, "cobranca_id": cobranca_id, "ja_existia": False,
                "pendencias": pendencias}


def registrar_pagamento_boleto(quem, identificador, data_pagamento, valor_centavos, comprovante_caminho=None):
    """Baixa de boleto pelo identificador (nosso número). Repetir não duplica."""
    identificador = _obrigatorio(identificador, "identificador do boleto")
    with db.leitura() as con:
        ja_pago = con.execute(
            "SELECT id, cobranca_id FROM pagamentos WHERE identificador_externo = ? AND cancelado_em IS NULL",
            (identificador,),
        ).fetchone()
        cobranca = con.execute("SELECT id FROM cobrancas WHERE boleto_identificador = ?", (identificador,)).fetchone()
    if ja_pago:
        return {"registrado": True, "pagamento_id": ja_pago["id"], "cobranca_id": ja_pago["cobranca_id"],
                "ja_existia": True, "pendencias": []}
    if cobranca is None:
        with db.transacao() as con:
            aberta = con.execute(
                "SELECT id FROM pendencias WHERE tipo = 'boleto_desconhecido' AND resolvida_em IS NULL "
                "AND descricao LIKE ?", (f"%{identificador}%",),
            ).fetchone()
            if aberta:
                return {"registrado": False, "pendencia_id": aberta["id"]}
            pendencia = _nova_pendencia(
                con, quem, "boleto_desconhecido",
                f"O banco informou pagamento de {regras.formatar_reais(int(valor_centavos))} em "
                f"{para_data(data_pagamento).isoformat()} do boleto {identificador}, que não está em nenhuma "
                "cobrança do sistema.",
            )
        return {"registrado": False, "pendencia_id": pendencia["pendencia_id"]}
    resultado = registrar_pagamento(quem, cobranca["id"], data_pagamento, valor_centavos, "boleto",
                                    identificador_externo=identificador, comprovante_caminho=comprovante_caminho)
    return {"registrado": True, **resultado}


def cancelar_pagamento(quem, pagamento_id, motivo):
    motivo = _obrigatorio(motivo, "motivo")
    with db.transacao() as con:
        pagamento = _obter(con, "pagamentos", pagamento_id, "Pagamento")
        if pagamento["cancelado_em"]:
            raise ErroDeNegocio("Esse pagamento já está cancelado.")
        con.execute("UPDATE pagamentos SET cancelado_em = ?, motivo_cancelamento = ? WHERE id = ?",
                    (regras.agora(), motivo, pagamento_id))
        _auditar(con, quem, "cancelar_pagamento", "pagamento", pagamento_id, motivo=motivo)


# --- PENDÊNCIAS ---
def criar_pendencia(quem, tipo, descricao, entidade=None, entidade_id=None):
    with db.transacao() as con:
        return _nova_pendencia(con, quem, _texto(tipo) or "outro", _obrigatorio(descricao, "descrição"),
                               _texto(entidade), entidade_id)


def resolver_pendencia(quem, pendencia_id, resolucao):
    resolucao = _obrigatorio(resolucao, "o que foi feito")
    with db.transacao() as con:
        pendencia = _obter(con, "pendencias", pendencia_id, "Pendência")
        if pendencia["resolvida_em"]:
            raise ErroDeNegocio("Essa pendência já foi resolvida.")
        con.execute("UPDATE pendencias SET resolvida_em = ?, resolvida_por = ?, resolucao = ? WHERE id = ?",
                    (regras.agora(), quem, resolucao, pendencia_id))
        _auditar(con, quem, "resolver_pendencia", "pendencia", pendencia_id, resolucao=resolucao)


# --- DOCUMENTOS ---
def _caminho_relativo(caminho, exigir_arquivo):
    """Normaliza um caminho relativo à pasta de documentos e recusa o que sai dela."""
    texto = _obrigatorio(caminho, "caminho do arquivo").replace("\\", "/")
    raiz = Path(config.DOCS_DIR).resolve()
    # Aceita caminho absoluto se estiver dentro da pasta de documentos.
    if texto.startswith("/"):
        try:
            texto = Path(texto).resolve().relative_to(raiz).as_posix()
        except ValueError:
            raise ErroDeNegocio(f"O arquivo precisa estar dentro da pasta de documentos: '{caminho}'.") from None
    relativo = PurePosixPath(texto)
    if ".." in relativo.parts:
        raise ErroDeNegocio(f"Caminho inválido: '{caminho}'.")
    relativo = relativo.as_posix().removeprefix("./")
    if exigir_arquivo and not (raiz / relativo).is_file():
        raise ErroDeNegocio(f"Arquivo não encontrado na pasta de documentos: '{relativo}'.")
    return relativo


def caminho_absoluto(relativo):
    return Path(config.DOCS_DIR).resolve() / _caminho_relativo(relativo, exigir_arquivo=False)


def pasta_documento(entidade, entidade_id):
    """Pasta (relativa à pasta de documentos) onde guardar os arquivos de um imóvel, locatário ou contrato."""
    if entidade not in ENTIDADES_DOCUMENTO:
        raise ErroDeNegocio(f"Entidade inválida: '{entidade}'. Use: {', '.join(ENTIDADES_DOCUMENTO)}.")
    with db.leitura() as con:
        if entidade == "locatario":
            loc = _obter(con, "locatarios", entidade_id, "Locatário")
            return f"locatarios/{regras.nome_pasta(loc['cpf_cnpj'] + ' - ' + loc['nome'])}"
        if entidade == "imovel":
            imovel = _obter(con, "imoveis", entidade_id, "Imóvel")
            return f"imoveis/{regras.nome_pasta(imovel['grupo'] + ' - ' + imovel['unidade'])}/imovel"
        contrato = _obter(con, "contratos", entidade_id, "Contrato")
        imovel = _obter(con, "imoveis", contrato["imovel_id"], "Imóvel")
        loc = _obter(con, "locatarios", contrato["locatario_id"], "Locatário")
        return (f"imoveis/{regras.nome_pasta(imovel['grupo'] + ' - ' + imovel['unidade'])}/contratos/"
                f"{regras.nome_pasta(contrato['data_inicio'][:7] + ' - ' + loc['nome'])}")


def registrar_documento(quem, entidade, entidade_id, tipo, caminho, descricao=None):
    """Liga um arquivo que já está na pasta de documentos a um imóvel, locatário ou contrato."""
    pasta_documento(entidade, entidade_id)  # valida entidade e id
    relativo = _caminho_relativo(caminho, exigir_arquivo=True)
    tipo = _obrigatorio(tipo, "tipo do documento")
    with db.transacao() as con:
        existente = con.execute("SELECT id FROM documentos WHERE caminho = ?", (relativo,)).fetchone()
        if existente:
            return existente["id"]
        cur = con.execute(
            "INSERT INTO documentos (entidade, entidade_id, tipo, caminho, descricao, registrado_por, registrado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (entidade, entidade_id, tipo, relativo, _texto(descricao), quem, regras.agora()),
        )
        _auditar(con, quem, "registrar_documento", entidade, entidade_id, documento_id=cur.lastrowid,
                 tipo=tipo, caminho=relativo)
        return cur.lastrowid


def salvar_documento(quem, entidade, entidade_id, tipo, nome_arquivo, conteudo, descricao=None):
    """Upload pela web: grava o arquivo na pasta certa e registra."""
    tipo = _obrigatorio(tipo, "tipo do documento")
    pasta = pasta_documento(entidade, entidade_id)
    original = Path(_obrigatorio(nome_arquivo, "arquivo"))
    extensao = original.suffix.lower()
    if tipo in NOMES_FIXOS:
        base = tipo
    elif tipo == "aditivo":
        base = f"aditivo-{regras.competencia_de(regras.hoje())}"
    else:
        base = regras.nome_pasta(original.stem).replace(" ", "-").lower() or tipo
    destino_pasta = Path(config.DOCS_DIR) / pasta
    destino_pasta.mkdir(parents=True, exist_ok=True)
    nome, n = f"{base}{extensao}", 2
    while (destino_pasta / nome).exists():
        nome, n = f"{base}-{n}{extensao}", n + 1
    (destino_pasta / nome).write_bytes(conteudo)
    return registrar_documento(quem, entidade, entidade_id, tipo, f"{pasta}/{nome}", descricao)


# --- USUÁRIOS ---
def criar_usuario(login, nome, senha, quem="sistema"):
    login = _obrigatorio(login, "login").lower()
    nome = _obrigatorio(nome, "nome")
    if len(senha or "") < 8:
        raise ErroDeNegocio("A senha precisa ter pelo menos 8 caracteres.")
    senha_hash = bcrypt.hashpw(senha.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    try:
        with db.transacao() as con:
            cur = con.execute("INSERT INTO usuarios (login, nome, senha_hash) VALUES (?, ?, ?)",
                              (login, nome, senha_hash))
            _auditar(con, quem, "criar_usuario", "usuario", cur.lastrowid, login=login, nome=nome)
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ErroDeNegocio(f"Já existe o usuário '{login}'.") from None


def alterar_senha(quem, login, senha_nova):
    if len(senha_nova or "") < 8:
        raise ErroDeNegocio("A senha precisa ter pelo menos 8 caracteres.")
    senha_hash = bcrypt.hashpw(senha_nova.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    with db.transacao() as con:
        cur = con.execute("UPDATE usuarios SET senha_hash = ? WHERE login = ?", (senha_hash, login.lower()))
        if not cur.rowcount:
            raise ErroDeNegocio(f"Usuário '{login}' não encontrado.")
        _auditar(con, quem, "alterar_senha", "usuario", None, login=login)


def autenticar(login, senha):
    """Devolve {'login', 'nome'} se login e senha conferem; senão None."""
    with db.leitura() as con:
        usuario = con.execute("SELECT * FROM usuarios WHERE login = ? AND ativo = 1",
                              ((login or "").strip().lower(),)).fetchone()
    if usuario and bcrypt.checkpw((senha or "").encode("utf-8"), usuario["senha_hash"].encode("ascii")):
        return {"login": usuario["login"], "nome": usuario["nome"]}
    return None
