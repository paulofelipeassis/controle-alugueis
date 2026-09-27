"""Demonstração das regras num banco temporário. Não toca no banco real.

Uso: python -m scripts.demo
"""
import tempfile
from pathlib import Path

from sistema import config

pasta = Path(tempfile.mkdtemp())
config.DB_PATH = str(pasta / "demo.db")
config.DOCS_DIR = str(pasta / "documentos")

from sistema import consultas, servicos  # noqa: E402

HOJE = "2026-11-20"
servicos.gerar_cobrancas("demo", HOJE)
a101 = servicos.cadastrar_imovel("demo", "Anel Viário", "Apto 101", "Rua A, 1")
a102 = servicos.cadastrar_imovel("demo", "Anel Viário", "Apto 102", "Rua A, 1")
servicos.cadastrar_imovel("demo", "Centro", "Sala 3", "Av. B, 20")
maria = servicos.cadastrar_locatario("demo", "Maria Souza", "12345678900", "maria@exemplo.com")
xyz = servicos.cadastrar_locatario("demo", "Construtora XYZ", "12345678000199", "financeiro@xyz.com")
c1 = servicos.criar_contrato("demo", a101, maria, "2026-10-01", "2027-09-30", 10, 150000, indice_reajuste="IGP-M")
c2 = servicos.criar_contrato("demo", a102, xyz, "2026-10-01", "2027-09-30", 5, 220000, indice_reajuste="IPCA")
servicos.gerar_cobrancas("demo", HOJE)
outubro = consultas.listar_cobrancas(competencia="2026-10", contrato_id=c1, hoje=HOJE)[0]
servicos.registrar_pagamento("demo", outubro["id"], "2026-10-10", 150000, "pix")

painel = consultas.painel(hoje=HOJE)
print(f"Painel em {HOJE}")
print(f"  Imóveis: {painel['imoveis_alugados']} alugados, {painel['imoveis_vagos']} vagos "
      f"(ocupação {painel['ocupacao_pct']}%)")
r = painel["resumo_do_mes"]
print(f"  Mês {r['competencia']}: devido {r['devido']}, recebido {r['recebido']}, falta {r['falta_receber']}")
print("  Atrasados:")
for g in painel["inadimplentes"]:
    meses = ", ".join(c["competencia"] for c in g["cobrancas"])
    print(f"    {g['imovel_nome']} — {g['locatario_nome']}: {g['saldo']} (com multa e juros: "
          f"{g['valor_atualizado']}), meses {meses}")
print("  Alertas:")
for a in painel["alertas"]:
    print(f"    - {a['mensagem']}")
print(f"  Pendências abertas: {painel['pendencias_abertas']}")
