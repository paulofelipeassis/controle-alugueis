"""Módulo opcional: caução (garantia em dinheiro) e a devolução quando o locatário sai.

O valor e o tipo da garantia já ficam no contrato. Este módulo acrescenta o que acontece na saída:
o aviso "caução a devolver" no painel, o registro da devolução (quanto voltou, quanto foi descontado
e por quê) e o aviso de limite. Para remover: apagar esta pasta (a tabela `caucoes` fica no banco
sem uso e não atrapalha nada).

Lei 8.245/1991, art. 38, §2º: a caução em dinheiro não pode passar de três aluguéis, deve ser
depositada em caderneta de poupança, e os rendimentos são do locatário quando ela é levantada.
O sistema não calcula o rendimento: quem devolve inclui o rendimento no valor devolvido.
"""
from sistema import db, regras, servicos
from sistema.regras import ErroDeNegocio, para_data

LIMITE_EM_ALUGUEIS = 3


def _texto(valor):
    return str(valor).strip() if valor is not None and str(valor).strip() else None


def _contrato_com_caucao(con, contrato_id):
    contrato = con.execute("SELECT * FROM contratos WHERE id = ?", (contrato_id,)).fetchone()
    if contrato is None:
        raise ErroDeNegocio(f"Contrato {contrato_id} não encontrado.")
    if contrato["garantia_tipo"] != "caucao" or not contrato["garantia_valor_centavos"]:
        raise ErroDeNegocio("Esse contrato não tem caução cadastrada.")
    return contrato


def situacao(contrato_id, hoje=None):
    """None se o contrato não tem caução; senão o estado dela: 'retida' (contrato ativo), 'a_devolver'
    (contrato encerrado, sem devolução registrada) ou 'devolvida'."""
    hoje = para_data(hoje) if hoje else regras.hoje()
    with db.leitura() as con:
        contrato = con.execute("SELECT * FROM contratos WHERE id = ?", (contrato_id,)).fetchone()
        if contrato is None or contrato["garantia_tipo"] != "caucao" or not contrato["garantia_valor_centavos"]:
            return None
        aluguel = con.execute("SELECT valor_centavos FROM valores_aluguel WHERE contrato_id = ? "
                              "ORDER BY vigente_desde LIMIT 1", (contrato_id,)).fetchone()[0]
        devolucao = con.execute("SELECT * FROM caucoes WHERE contrato_id = ?", (contrato_id,)).fetchone()
    valor = contrato["garantia_valor_centavos"]
    limite = LIMITE_EM_ALUGUEIS * aluguel
    encerramento = contrato["data_encerramento"]
    resultado = {
        "contrato_id": contrato_id,
        "estado": "devolvida" if devolucao else ("a_devolver" if encerramento else "retida"),
        "valor_centavos": valor, "valor": regras.formatar_reais(valor),
        "limite_centavos": limite, "limite": regras.formatar_reais(limite), "excede_limite": valor > limite,
        "encerramento": encerramento,
        "dias_desde_encerramento": (hoje - para_data(encerramento)).days if encerramento else None,
        "devolucao": None,
    }
    if devolucao:
        resultado["devolucao"] = dict(devolucao) | {
            "valor_devolvido": regras.formatar_reais(devolucao["valor_devolvido_centavos"]),
            "descontos": regras.formatar_reais(devolucao["descontos_centavos"])}
    return resultado


def registrar_devolucao(quem, contrato_id, data_devolucao, valor_devolvido_centavos, descontos_centavos=0,
                        motivo_descontos=None, observacao=None):
    """Registra a devolução da caução depois do encerramento. devolvido + descontos tem que fechar com a
    caução (pode passar dela: é o rendimento da poupança, que também é do locatário)."""
    data = para_data(data_devolucao, "data da devolução")
    devolvido = int(valor_devolvido_centavos or 0)
    descontos = int(descontos_centavos or 0)
    motivo = _texto(motivo_descontos)
    if devolvido < 0 or descontos < 0:
        raise ErroDeNegocio("Os valores não podem ser negativos.")
    if descontos and not motivo:
        raise ErroDeNegocio("Informe o motivo dos descontos (ex.: pintura, aluguel em aberto).")
    with db.transacao() as con:
        contrato = _contrato_com_caucao(con, contrato_id)
        if not contrato["data_encerramento"]:
            raise ErroDeNegocio("A caução só é devolvida depois de encerrar o contrato.")
        if con.execute("SELECT 1 FROM caucoes WHERE contrato_id = ?", (contrato_id,)).fetchone():
            raise ErroDeNegocio("A devolução da caução desse contrato já foi registrada.")
        caucao = contrato["garantia_valor_centavos"]
        if devolvido + descontos < caucao:
            raise ErroDeNegocio(
                f"O valor devolvido ({regras.formatar_reais(devolvido)}) mais os descontos "
                f"({regras.formatar_reais(descontos)}) é menor que a caução ({regras.formatar_reais(caucao)}). "
                "O que não foi devolvido precisa aparecer como desconto, com o motivo.")
        con.execute(
            "INSERT INTO caucoes (contrato_id, devolvida_em, valor_devolvido_centavos, descontos_centavos, "
            "motivo_descontos, observacao, registrado_por, registrado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (contrato_id, data.isoformat(), devolvido, descontos, motivo, _texto(observacao), quem, regras.agora()))
        servicos.auditar(con, quem, "devolver_caucao", "contrato", contrato_id, valor_devolvido_centavos=devolvido,
                         descontos_centavos=descontos, motivo_descontos=motivo, devolvida_em=data.isoformat())


def a_devolver(hoje=None):
    """Contratos encerrados com caução ainda não devolvida."""
    hoje = para_data(hoje) if hoje else regras.hoje()
    with db.leitura() as con:
        linhas = con.execute(
            "SELECT c.id, c.data_encerramento, c.garantia_valor_centavos, i.grupo, i.unidade, l.nome "
            "FROM contratos c JOIN imoveis i ON i.id = c.imovel_id JOIN locatarios l ON l.id = c.locatario_id "
            "LEFT JOIN caucoes k ON k.contrato_id = c.id "
            "WHERE c.garantia_tipo = 'caucao' AND c.garantia_valor_centavos > 0 "
            "AND c.data_encerramento IS NOT NULL AND k.contrato_id IS NULL ORDER BY c.data_encerramento").fetchall()
    return [{"contrato_id": l["id"], "descricao": f"{l['grupo']} - {l['unidade']} — {l['nome']}",
             "valor_centavos": l["garantia_valor_centavos"], "valor": regras.formatar_reais(l["garantia_valor_centavos"]),
             "encerramento": l["data_encerramento"],
             "dias": (hoje - para_data(l["data_encerramento"])).days} for l in linhas]
