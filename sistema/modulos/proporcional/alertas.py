"""Aviso no painel e no Hermes: primeiro período de contrato que começou no meio do mês."""
from sistema.modulos import proporcional


def _data(iso):
    return f"{iso[8:]}/{iso[5:7]}"


def alertas(hoje):
    return [{"tipo": "primeiro_periodo_proporcional", "contrato_id": s["contrato_id"],
             "mensagem": f"{s['descricao']}: o contrato começou em {_data(s['inicio'])} e a primeira cobrança "
                         f"(vence {_data(s['vencimento'])}) está com o aluguel cheio ({s['valor_cheio']}). Se ela deve "
                         f"cobrar só os dias usados em {s['mes_do_inicio'][5:]}/{s['mes_do_inicio'][:4]} "
                         f"({s['dias']} de {s['dias_do_mes']} dias), o valor seria {s['valor_sugerido']}."}
            for s in proporcional.pendentes(hoje)]
