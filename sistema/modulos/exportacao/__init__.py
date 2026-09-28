"""Módulo opcional: baixar os pagamentos em planilha (CSV), por exemplo para o imposto de renda.

Dois arquivos, ambos no formato que o Excel e o Google Planilhas em português abrem direto
(separador ponto e vírgula, vírgula nos decimais, acentos corretos):
  - pagamentos: cada pagamento, com os mesmos filtros do histórico financeiro;
  - recebimentos do ano: por locatário e imóvel, o total recebido em cada mês (pela data em que o
    dinheiro entrou) e o total do ano. É a visão que o contador pede.
Não guarda nada e não altera nada. Para remover: apagar esta pasta.
"""
import csv
import io
from collections import OrderedDict

from sistema import consultas, regras
from sistema.regras import ErroDeNegocio

BOM = "﻿"  # sem isto o Excel abre o arquivo com os acentos quebrados
MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def seguro(texto):
    """Texto que o Excel poderia tratar como fórmula (começa com = + - @) ganha um apóstrofo na frente.
    Sem isso, um nome digitado como '=HYPERLINK(...)' executaria ao abrir a planilha."""
    texto = "" if texto is None else str(texto)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def reais(centavos):
    """1500 centavos -> '15,00' (vírgula decimal, sem separador de milhar: o Excel lê como número)."""
    if centavos is None:
        return ""
    sinal = "-" if centavos < 0 else ""
    reais_, cent = divmod(abs(int(centavos)), 100)
    return f"{sinal}{reais_},{cent:02d}"


def cpf_cnpj(digitos):
    """Com pontuação, para o Excel não comer o zero da frente (CPF 01234567890 viraria 1234567890)."""
    d = regras.so_digitos(digitos)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return d


def _data(iso):
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if iso else ""


def _csv(linhas):
    saida = io.StringIO()
    csv.writer(saida, delimiter=";", lineterminator="\r\n").writerows(linhas)
    return BOM + saida.getvalue()


def pagamentos_csv(data_de=None, data_ate=None, grupo=None, locatario_id=None, incluir_cancelados=False):
    """Um pagamento por linha, do mais recente para o mais antigo (mesma ordem do histórico financeiro)."""
    historico = consultas.historico_pagamentos(data_de, data_ate, grupo, None, locatario_id, incluir_cancelados)
    linhas = [["Data do pagamento", "Mês da cobrança", "Imóvel", "Locatário", "CPF/CNPJ", "Valor pago", "Forma",
               "Identificador (boleto ou PIX)", "Registrado por", "Situação", "Motivo do cancelamento", "Observação"]]
    for p in historico["pagamentos"]:
        linhas.append([_data(p["data_pagamento"]), f"{p['competencia'][5:]}/{p['competencia'][:4]}",
                       seguro(p["imovel_nome"]), seguro(p["locatario_nome"]), cpf_cnpj(p["locatario_cpf_cnpj"]),
                       reais(p["valor_centavos"]), p["forma"], seguro(p["identificador_externo"]),
                       seguro(p["registrado_por"]), "Cancelado" if p["cancelado_em"] else "Válido",
                       seguro(p["motivo_cancelamento"]), seguro(p["observacao"])])
    return _csv(linhas)


def _ano(ano):
    try:
        valor = int(ano)
    except (TypeError, ValueError):
        valor = 0
    if not 2000 <= valor <= 2100:
        raise ErroDeNegocio(f"Ano inválido: '{ano}'. Use quatro dígitos, por exemplo 2027.")
    return valor


def recebimentos_do_ano_csv(ano):
    """Por locatário e imóvel: o que entrou em cada mês do ano (pagamentos válidos, pela data do pagamento)."""
    ano = _ano(ano)
    pagamentos = consultas.historico_pagamentos(f"{ano}-01-01", f"{ano}-12-31")["pagamentos"]
    grupos = OrderedDict()
    for p in sorted(pagamentos, key=lambda p: (p["locatario_nome"].casefold(), p["imovel_nome"].casefold())):
        chave = (p["locatario_id"], p["imovel_id"])
        linha = grupos.setdefault(chave, {"locatario": p["locatario_nome"], "cpf_cnpj": p["locatario_cpf_cnpj"],
                                          "imovel": p["imovel_nome"], "meses": [0] * 12})
        linha["meses"][int(p["data_pagamento"][5:7]) - 1] += p["valor_centavos"]
    linhas = [["Locatário", "CPF/CNPJ", "Imóvel", *MESES, f"Total {ano}"]]
    totais = [0] * 12
    for g in grupos.values():
        linhas.append([seguro(g["locatario"]), cpf_cnpj(g["cpf_cnpj"]), seguro(g["imovel"]),
                       *[reais(v) if v else "" for v in g["meses"]], reais(sum(g["meses"]))])
        totais = [a + b for a, b in zip(totais, g["meses"])]
    linhas.append(["TOTAL", "", "", *[reais(v) if v else "" for v in totais], reais(sum(totais))])
    return _csv(linhas)
