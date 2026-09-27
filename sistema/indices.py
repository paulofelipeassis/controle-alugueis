"""Índices de reajuste (IPCA e IGP-M) buscados na API pública do Banco Central (SGS).

Séries mensais em % (variação no mês): IPCA = 433 (IBGE), IGP-M = 189 (FGV).
O que é buscado fica guardado na tabela `indices`, para não buscar de novo.
"""
import json
import urllib.request
from datetime import date

from sistema import db, regras

SERIES_BCB = {"IPCA": 433, "IGP-M": 189}
URL_BCB = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados"
           "?formato=json&dataInicial={de}&dataFinal={ate}")


def buscar_no_banco_central(indice, de, ate):
    """{competencia: variacao_pct (texto)} publicados entre as competências de e ate."""
    url = URL_BCB.format(serie=SERIES_BCB[indice], de=f"01/{de[5:7]}/{de[0:4]}",
                         ate=regras.vencimento(ate, 31).strftime("%d/%m/%Y"))
    with urllib.request.urlopen(url, timeout=20) as resposta:
        dados = json.load(resposta)
    resultado = {}
    for item in dados:
        dia, mes, ano = item["data"].split("/")
        resultado[regras.competencia_de(date(int(ano), int(mes), int(dia)))] = str(item["valor"])
    return resultado


def variacoes(indice, de, ate, buscar=buscar_no_banco_central):
    """Variações mensais de de..ate; None se algum mês ainda não foi publicado."""
    meses = regras.competencias_entre(de, ate)
    with db.leitura() as con:
        guardadas = dict(con.execute(
            "SELECT competencia, variacao_pct FROM indices WHERE indice = ? AND competencia BETWEEN ? AND ?",
            (indice, de, ate)).fetchall())
    if any(m not in guardadas for m in meses):
        novas = buscar(indice, de, ate)
        with db.transacao() as con:
            con.executemany("INSERT OR REPLACE INTO indices (indice, competencia, variacao_pct) VALUES (?, ?, ?)",
                            [(indice, m, v) for m, v in novas.items()])
        guardadas.update(novas)
    if any(m not in guardadas for m in meses):
        return None
    return [guardadas[m] for m in meses]
