"""Aviso no painel e no Hermes: caução que ainda não foi devolvida."""
from sistema.modulos import caucao


def alertas(hoje):
    return [{"tipo": "caucao_a_devolver", "contrato_id": c["contrato_id"],
             "mensagem": f"{c['descricao']}: caução de {c['valor']} aguardando devolução. Contrato encerrado em "
                         f"{c['encerramento'][8:]}/{c['encerramento'][5:7]}/{c['encerramento'][:4]} "
                         f"(há {c['dias']} dias)."}
            for c in caucao.a_devolver(hoje)]
