"""Módulo opcional: primeiro período proporcional.

Contrato que começa no meio do mês costuma cobrar, na primeira cobrança, só os dias usados daquele
mês (17 de 31 dias, por exemplo). O sistema gera a primeira cobrança com o aluguel cheio, porque não
sabe como cada contrato cobra. Este módulo faz a pergunta na hora certa (aviso no painel e bloco na
página do contrato, até alguém decidir) e, se a resposta for "proporcional", aplica o valor na cobrança.

Só há sugestão quando: o contrato está ativo e começou depois do dia 1, dentro do período em que o
sistema já cobra (INICIO_COBRANCAS); a primeira cobrança ainda está intocada (sem boleto, sem
pagamento e com o valor do aluguel); e ninguém decidiu ainda. Para remover: apagar esta pasta.
"""
import sqlite3

from sistema import config, db, regras, servicos
from sistema.regras import ErroDeNegocio, para_data


def _primeira_cobranca(con, contrato):
    """A primeira cobrança do contrato, se ela nasce do início do contrato (e não do início das cobranças)."""
    inicio = para_data(contrato["data_inicio"])
    competencia = regras.competencia_de(inicio)
    if regras.vencimento(competencia, contrato["dia_vencimento"]) < inicio:
        competencia = regras.proxima_competencia(competencia)
    return con.execute("SELECT * FROM cobrancas WHERE contrato_id = ? AND competencia = ?",
                       (contrato["id"], competencia)).fetchone()


def sugerir(contrato_id, hoje=None, gerar=True):
    """A sugestão para o contrato, ou None se não se aplica (ou se já foi decidida)."""
    hoje = para_data(hoje) if hoje else regras.hoje()
    if gerar:
        servicos.gerar_cobrancas("sistema", hoje)  # a primeira cobrança pode ainda não existir
    with db.leitura() as con:
        contrato = con.execute("SELECT * FROM contratos WHERE id = ?", (contrato_id,)).fetchone()
        if contrato is None or contrato["data_encerramento"]:
            return None
        inicio = para_data(contrato["data_inicio"])
        mes_inicio = regras.competencia_de(inicio)
        if inicio.day == 1 or mes_inicio < config.INICIO_COBRANCAS:
            return None  # mês inteiro, ou mês que veio do sistema antigo
        if con.execute("SELECT 1 FROM primeiro_periodo WHERE contrato_id = ?", (contrato_id,)).fetchone():
            return None
        cobranca = _primeira_cobranca(con, contrato)
        if cobranca is None or cobranca["situacao"] != "normal" or cobranca["boleto_identificador"]:
            return None
        if con.execute("SELECT 1 FROM pagamentos WHERE cobranca_id = ? AND cancelado_em IS NULL",
                       (cobranca["id"],)).fetchone():
            return None
        if cobranca["valor_centavos"] != servicos.valor_vigente(con, contrato_id, cobranca["vencimento"]):
            return None  # alguém já mexeu no valor
        imovel = con.execute("SELECT grupo, unidade FROM imoveis WHERE id = ?", (contrato["imovel_id"],)).fetchone()
        locatario = con.execute("SELECT nome FROM locatarios WHERE id = ?", (contrato["locatario_id"],)).fetchone()
    no_mes = regras.dias_do_mes(mes_inicio)
    dias = no_mes - inicio.day + 1
    valor = regras.valor_proporcional(cobranca["valor_centavos"], dias, no_mes)
    return {
        "contrato_id": contrato_id, "cobranca_id": cobranca["id"], "competencia": cobranca["competencia"],
        "descricao": f"{imovel['grupo']} - {imovel['unidade']} — {locatario['nome']}",
        "inicio": contrato["data_inicio"], "vencimento": cobranca["vencimento"], "mes_do_inicio": mes_inicio,
        "dias": dias, "dias_do_mes": no_mes,
        "valor_cheio_centavos": cobranca["valor_centavos"], "valor_cheio": regras.formatar_reais(cobranca["valor_centavos"]),
        "valor_sugerido_centavos": valor, "valor_sugerido": regras.formatar_reais(valor),
    }


def decidir(quem, contrato_id, proporcional, hoje=None):
    """Registra a decisão: proporcional=True aplica o valor sugerido na primeira cobrança; False mantém o
    aluguel cheio. Depois disso o aviso some."""
    sugestao = sugerir(contrato_id, hoje)
    if sugestao is None:
        raise ErroDeNegocio("Esse contrato não tem primeiro período a decidir (já foi decidido, a cobrança já "
                            "tem boleto ou pagamento, ou o contrato começa no dia 1).")
    if proporcional:
        servicos.editar_valor_cobranca(
            quem, sugestao["cobranca_id"], sugestao["valor_sugerido_centavos"],
            f"primeiro período proporcional: {sugestao['dias']} de {sugestao['dias_do_mes']} dias de "
            f"{sugestao['mes_do_inicio']}")
    decisao = "proporcional" if proporcional else "cheio"
    valor = sugestao["valor_sugerido_centavos"] if proporcional else sugestao["valor_cheio_centavos"]
    try:
        with db.transacao() as con:
            con.execute("INSERT INTO primeiro_periodo (contrato_id, decisao, decidido_por, decidido_em) "
                        "VALUES (?, ?, ?, ?)", (contrato_id, decisao, quem, regras.agora()))
            servicos.auditar(con, quem, "decidir_primeiro_periodo", "contrato", contrato_id,
                             decisao=decisao, valor_centavos=valor)
    except sqlite3.IntegrityError:  # outra pessoa decidiu no mesmo instante
        raise ErroDeNegocio("O primeiro período desse contrato acabou de ser decidido por outra pessoa.") from None
    return {"decisao": decisao, "cobranca_id": sugestao["cobranca_id"], "valor_centavos": valor}


def pendentes(hoje=None):
    """Sugestões em aberto, de todos os contratos ativos."""
    hoje = para_data(hoje) if hoje else regras.hoje()
    servicos.gerar_cobrancas("sistema", hoje)  # uma vez só, e não uma por contrato
    with db.leitura() as con:
        ids = [r[0] for r in con.execute("SELECT id FROM contratos WHERE data_encerramento IS NULL ORDER BY id")]
    return [s for s in (sugerir(i, hoje, gerar=False) for i in ids) if s]
