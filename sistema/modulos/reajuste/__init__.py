"""Sugestão de reajuste anual pelo IPCA ou IGP-M. Módulo opcional.

Só busca o índice quando alguém pede (pela tela do contrato ou pelo Hermes): pega as
últimas 12 variações mensais publicadas na API pública do Banco Central e calcula o
acumulado. Não grava nada; quem registra o reajuste é uma pessoa, com
`servicos.registrar_reajuste`.

Para remover: apagar esta pasta. O núcleo continua avisando do reajuste anual e
registrando o valor à mão (servicos.registrar_reajuste).
"""
import json
import urllib.request

from sistema import db, regras
from sistema.regras import ErroDeNegocio, para_data

# Séries do SGS do Banco Central, variação % no mês: IPCA (IBGE) e IGP-M (FGV).
SERIES_BCB = {"IPCA": 433, "IGP-M": 189}
URL_BCB = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/12?formato=json"


def ultimos_12_meses(indice):
    """[(competência 'AAAA-MM', variação % em texto)] das 12 últimas publicadas."""
    with urllib.request.urlopen(URL_BCB.format(serie=SERIES_BCB[indice]), timeout=20) as resposta:
        dados = json.load(resposta)
    return [(f"{d['data'][6:10]}-{d['data'][3:5]}", str(d["valor"])) for d in dados]


def sugerir(contrato_id, buscar=None):
    """Sugestão para o próximo reajuste do contrato. Índice negativo mantém o valor."""
    with db.leitura() as con:
        contrato = con.execute(
            "SELECT c.*, i.grupo, i.unidade, l.nome AS locatario_nome FROM contratos c "
            "JOIN imoveis i ON i.id = c.imovel_id JOIN locatarios l ON l.id = c.locatario_id WHERE c.id = ?",
            (contrato_id,)).fetchone()
        if contrato is None:
            raise ErroDeNegocio(f"Contrato {contrato_id} não encontrado.")
        ultimo = con.execute(
            "SELECT valor_centavos, vigente_desde FROM valores_aluguel WHERE contrato_id = ? "
            "ORDER BY vigente_desde DESC LIMIT 1", (contrato_id,)).fetchone()
    aniversario = regras.proximo_aniversario(para_data(ultimo["vigente_desde"]))
    sugestao = {
        "contrato_id": contrato_id,
        "descricao": f"{contrato['grupo']} - {contrato['unidade']} — {contrato['locatario_nome']}",
        "indice": contrato["indice_reajuste"],
        "valor_atual_centavos": ultimo["valor_centavos"],
        "valor_atual": regras.formatar_reais(ultimo["valor_centavos"]),
        "vigente_desde": aniversario.isoformat(),
    }
    indice = regras.normalizar_indice(contrato["indice_reajuste"])
    if not indice:
        sugestao["erro"] = (f"O índice '{contrato['indice_reajuste'] or 'não informado'}' não é calculado pelo "
                            "sistema. Registre o novo valor à mão.")
        return sugestao
    try:
        meses = (buscar or ultimos_12_meses)(indice)
    except Exception:  # noqa: BLE001 — sem internet ou Banco Central fora do ar
        sugestao["erro"] = f"Não consegui buscar o {indice} no Banco Central agora. Tente mais tarde ou registre à mão."
        return sugestao
    percentual = regras.acumulado_pct(v for _, v in meses)
    valor = regras.valor_reajustado(ultimo["valor_centavos"], percentual)
    periodo = f"{meses[0][0][5:]}/{meses[0][0][:4]} a {meses[-1][0][5:]}/{meses[-1][0][:4]}"
    pct = regras.formatar_pct(percentual)
    sugestao.update({
        "indice": indice, "percentual": str(percentual), "periodo": periodo,
        "valor_sugerido_centavos": valor, "valor_sugerido": regras.formatar_reais(valor),
        "motivo": f"{indice} {pct}% ({periodo})" + (" — negativo, valor mantido" if percentual <= 0 else ""),
    })
    if percentual <= 0:
        sugestao["resumo"] = f"{indice} de {periodo} = {pct}% (negativo): valor mantido em {sugestao['valor_atual']}"
    else:
        sugestao["resumo"] = (f"{indice} de {periodo} = {pct}%: {sugestao['valor_atual']} → "
                              f"{sugestao['valor_sugerido']} a partir de {aniversario:%d/%m/%Y}")
    return sugestao
