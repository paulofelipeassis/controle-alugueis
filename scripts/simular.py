"""Simulação de 15 meses de operação com dados fictícios, conferindo as contas todo mês.

Cria 20 imóveis, locatários com comportamentos diferentes (pontual, atrasa, paga
parcial, paga por PIX, para de pagar), contratos antigos e novos, e faz o papel do
Hermes (boletos e baixas) e das pessoas (reajustes, encerramento, isenção, correções)
dia a dia, de outubro de 2026 a dezembro de 2027. No fim de cada mês confere se o que
o sistema mostra bate com o que a simulação pagou de fato.

Uso: python -m scripts.simular          (banco temporário; não toca no banco real)
Também roda nos testes (sistema/tests/test_simulacao.py).
"""
import random
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path

from sistema import config, consultas, db, regras, servicos

INICIO = date(2026, 10, 1)
FIM = date(2027, 12, 31)
REAJUSTE_PCT = "4.00"  # índice fictício (o módulo de reajuste buscaria no Banco Central)

GRUPOS = [("Anel Viário", "Apto", 8, "Rua das Acácias, 120 - Goiânia"),
          ("Centro", "Sala", 6, "Av. Goiás, 900 - Goiânia"),
          ("Jardim América", "Casa", 6, "Rua C-140, 45 - Goiânia")]

# nome, CPF/CNPJ, perfil de pagamento
LOCATARIOS = [
    ("Maria Souza", "11111111111", "pontual"), ("João Pereira", "22222222222", "pontual"),
    ("Ana Lima", "33333333333", "atrasa_com_juros"), ("Carlos Dias", "44444444444", "atrasa_sem_juros"),
    ("Beatriz Rocha", "55555555555", "parcial"), ("Construtora XYZ Ltda", "12345678000199", "pix"),
    ("Pedro Alves", "66666666666", "para_de_pagar"), ("Luiza Martins", "77777777777", "pontual"),
    ("Rafael Costa", "88888888888", "atrasa_com_juros"), ("Fernanda Gomes", "99999999999", "pix"),
    ("Clínica Bem Estar", "98765432000110", "pontual"), ("Tiago Ramos", "10101010101", "pontual"),
    ("Juliana Freitas", "12121212121", "atrasa_sem_juros"), ("Marcos Vieira", "13131313131", "pontual"),
    ("Paula Nunes", "14141414141", "pontual"),
]

# (imóvel nº 0-19, locatário nº, início, fim previsto, dia venc., valor R$, índice, valor vale desde)
CONTRATOS = [
    (0, 0, "2024-03-01", "2027-02-28", 5, 1500, "IGP-M", "2026-03-01"),
    (1, 1, "2025-11-10", "2026-11-09", 10, 1450, "IPCA", "2025-11-10"),   # prazo vence na simulação
    (2, 2, "2023-06-15", "2027-06-14", 15, 1600, "IGP-M", "2026-06-15"),
    (3, 3, "2026-01-20", "2027-01-19", 20, 1380, "IPCA", "2026-01-20"),
    (4, 4, "2025-10-01", "2028-09-30", 31, 1550, "IGP-M", "2025-10-01"),  # vence dia 31
    (5, 5, "2024-10-05", "2027-10-04", 5, 1700, "IPCA", "2025-10-05"),    # empresa, 3 unidades
    (6, 5, "2024-10-05", "2027-10-04", 5, 1700, "IPCA", "2025-10-05"),
    (7, 5, "2025-04-05", "2028-04-04", 5, 1750, "IPCA", "2026-04-05"),
    (8, 6, "2026-02-10", "2028-02-09", 10, 2800, "IGP-M", "2026-02-10"),  # sala; para de pagar
    (9, 7, "2025-12-01", "2027-11-30", 1, 3100, "IPCA", "2025-12-01"),
    (10, 8, "2026-05-15", "2027-05-14", 15, 2600, "INPC", "2026-05-15"),  # índice sem cálculo automático
    (11, 9, "2026-09-01", "2027-08-31", 10, 2900, "IPCA", "2026-09-01"),
    (12, 10, "2022-08-01", "2027-07-31", 10, 4200, "IGP-M", "2026-08-01"),
    (14, 11, "2026-10-20", "2029-10-19", 20, 2300, "IPCA", None),         # contrato novo
    (15, 12, "2025-07-01", "2028-06-30", 5, 2400, "IGP-M", "2026-07-01"),
    (16, 13, "2026-03-25", "2028-03-24", 25, 2250, None, "2026-03-25"),   # sem índice
    (17, 14, "2026-11-15", "2029-11-14", 15, 2500, "IPCA", None),         # contrato novo
]
EM_MANUTENCAO = 18


class Simulacao:
    def __init__(self, semente=2026):
        self.rng = random.Random(semente)
        self.hoje = INICIO
        self.agendados = {}          # data -> [(cobranca_id, valor_centavos, forma, identificador)]
        self.pago_pela_simulacao = 0  # o que "entrou no banco", menos o que foi cancelado
        self.violacoes = []
        self.eventos = []
        self.boletos_emitidos = 0
        self.baixas_repetidas = 0
        self.perfil = {}             # contrato_id -> perfil

    # --- utilidades ---
    def log(self, texto):
        self.eventos.append(f"{self.hoje:%d/%m/%Y} {texto}")

    def agendar(self, dia, cobranca_id, valor, forma, identificador=None):
        self.agendados.setdefault(dia, []).append((cobranca_id, valor, forma, identificador))

    def conferir(self, condicao, mensagem):
        if not condicao:
            self.violacoes.append(f"{self.hoje:%d/%m/%Y}: {mensagem}")

    # --- montagem ---
    def cadastrar(self):
        self.imoveis = []
        for grupo, tipo, quantidade, endereco in GRUPOS:
            for n in range(1, quantidade + 1):
                unidade = f"{tipo} {100 + n if tipo == 'Apto' else n}"
                self.imoveis.append(servicos.cadastrar_imovel(
                    "hermes", grupo, unidade, endereco, iptu_anual_centavos=self.rng.randint(80, 300) * 1000))
        servicos.atualizar_imovel("paulo", self.imoveis[EM_MANUTENCAO], em_manutencao=True)
        self.locatarios = [servicos.cadastrar_locatario("hermes", nome, doc, f"contato{i}@exemplo.com",
                                                        telefone=f"62 9{i:04d}-0000")
                           for i, (nome, doc, _) in enumerate(LOCATARIOS)]
        self.corretor = servicos.cadastrar_corretor("hermes", "Imobiliária Parceira", "62 3333-0000")
        self.contratos = []
        for im, lo, inicio, fim, dia, valor, indice, desde in CONTRATOS:
            if regras.para_data(inicio) > self.hoje:
                continue  # contratos novos entram no dia certo
            self.criar_contrato(im, lo, inicio, fim, dia, valor, indice, desde)

    def criar_contrato(self, im, lo, inicio, fim, dia, valor, indice, desde):
        contrato = servicos.criar_contrato(
            "hermes", self.imoveis[im], self.locatarios[lo], inicio, fim, dia, valor * 100,
            corretor_id=self.corretor if im % 3 == 0 else None, indice_reajuste=indice,
            garantia_tipo="caucao", garantia_valor_centavos=valor * 200, valor_vigente_desde=desde)
        self.contratos.append(contrato)
        self.perfil[contrato] = LOCATARIOS[lo][2]
        return contrato

    # --- o que o Hermes faz todo dia ---
    def rotina_hermes(self):
        reajustados = set()
        for cb in consultas.cobrancas_sem_boleto(10, hoje=self.hoje):
            if cb["reajuste_pendente"]:
                if cb["contrato_id"] not in reajustados:
                    self.reajustar(cb["contrato_id"])  # a pessoa registra; o boleto sai no dia seguinte
                    reajustados.add(cb["contrato_id"])
                continue
            identificador = f"NN{cb['id']:06d}"
            servicos.registrar_boleto("hermes", cb["id"], "Caixa", identificador, "10490.00000 00000.000000")
            servicos.marcar_boleto_enviado("hermes", cb["id"])
            self.boletos_emitidos += 1
            self.decidir_pagamento(cb, identificador)
        for cb_id, valor, forma, identificador in self.agendados.pop(self.hoje, []):
            if forma == "boleto":
                r = servicos.registrar_pagamento_boleto("hermes", identificador, self.hoje, valor)
                if r.get("registrado") and not r.get("ja_existia"):
                    self.pago_pela_simulacao += valor
                if self.rng.random() < 0.1:  # o Hermes repete a baixa sem querer
                    r2 = servicos.registrar_pagamento_boleto("hermes", identificador, self.hoje, valor)
                    self.conferir(r2.get("ja_existia") or not r2.get("registrado"),
                                  f"baixa repetida do boleto {identificador} duplicou o pagamento")
                    self.baixas_repetidas += 1
            else:
                try:
                    r = servicos.registrar_pagamento("hermes", cb_id, self.hoje, valor, forma,
                                                     identificador_externo=identificador)
                    if not r["ja_existia"]:
                        self.pago_pela_simulacao += valor
                except regras.ErroDeNegocio as erro:
                    self.log(f"pagamento recusado: {erro}")

    def decidir_pagamento(self, cb, identificador):
        venc = regras.para_data(cb["vencimento"])
        valor = cb["saldo_centavos"]
        perfil = self.perfil[cb["contrato_id"]]
        if perfil == "pontual":
            if self.rng.random() < 0.4:  # paga no último dia possível: o dia útil do vencimento (sem encargos)
                self.agendar(regras.vencimento_efetivo(venc), cb["id"], valor, "boleto", identificador)
            else:
                self.agendar(venc - timedelta(days=self.rng.randint(0, 3)), cb["id"], valor, "boleto", identificador)
        elif perfil == "atrasa_com_juros":
            dia = venc + timedelta(days=self.rng.randint(3, 20))
            multa, juros = regras.encargos(valor, cb["multa_pct"], cb["juros_mes_pct"],
                                           regras.vencimento_efetivo(venc), dia)
            self.agendar(dia, cb["id"], valor + multa + juros, "boleto", identificador)
        elif perfil == "atrasa_sem_juros":
            self.agendar(venc + timedelta(days=self.rng.randint(3, 10)), cb["id"], valor, "pix", f"E2E{cb['id']}")
        elif perfil == "parcial":
            metade = valor // 2
            self.agendar(venc, cb["id"], metade, "pix", f"E2E{cb['id']}a")
            self.agendar(venc + timedelta(days=10), cb["id"], valor - metade, "dinheiro")
        elif perfil == "pix":
            self.agendar(venc - timedelta(days=1), cb["id"], valor, "pix", f"E2E{cb['id']}")
        elif perfil == "para_de_pagar" and self.hoje < date(2026, 12, 1):
            self.agendar(venc, cb["id"], valor, "boleto", identificador)

    # --- o que as pessoas fazem ---
    def reajustar(self, contrato_id):
        extrato = consultas.extrato_contrato(contrato_id, hoje=self.hoje)
        desde = regras.proximo_aniversario(regras.para_data(extrato["valores"][-1]["vigente_desde"]))
        atual = extrato["valores"][-1]["valor_centavos"]
        novo = regras.valor_reajustado(atual, REAJUSTE_PCT)
        servicos.registrar_reajuste("paulo", contrato_id, novo, desde, f"{extrato['indice_reajuste']} 4,00%")
        self.log(f"reajuste {extrato['descricao']}: {regras.formatar_reais(atual)} → {regras.formatar_reais(novo)}")

    def eventos_do_dia(self):
        d = self.hoje
        for im, lo, inicio, fim, dia, valor, indice, desde in CONTRATOS:
            if regras.para_data(inicio) == d:
                self.criar_contrato(im, lo, inicio, fim, dia, valor, indice, desde)
                self.log(f"contrato novo: {LOCATARIOS[lo][0]}")
        if d == date(2026, 11, 12):  # pagamento lançado no contrato errado: cancela e relança
            cb = consultas.listar_cobrancas(competencia="2026-11", contrato_id=self.contratos[9], hoje=d)[0]
            errado = consultas.listar_cobrancas(competencia="2026-11", contrato_id=self.contratos[10], hoje=d)[0]
            r = servicos.registrar_pagamento("marta", errado["id"], d, cb["valor_centavos"], "transferencia")
            servicos.cancelar_pagamento("marta", r["pagamento_id"], "lançado no contrato errado")
            self.log("pagamento lançado no contrato errado foi cancelado")
        if d == date(2026, 12, 3):  # banco avisa de um boleto que não existe no sistema
            r = servicos.registrar_pagamento_boleto("hermes", "NN999999", d, 123400)
            self.conferir(not r["registrado"], "boleto desconhecido virou pagamento")
        if d == date(2027, 1, 20):  # acordo: isenta a cobrança de fevereiro de um locatário
            cb = consultas.listar_cobrancas(competencia="2027-02", contrato_id=self.contratos[0], hoje=d)
            if cb and not cb[0]["pago_centavos"]:
                servicos.isentar_cobranca("paulo", cb[0]["id"], "acordo: reforma do banheiro")
                self.cancelar_agendados(cb[0]["id"])
                self.log("cobrança isentada por acordo")
        if d == date(2027, 2, 1):  # renovação antes do fim
            servicos.renovar_contrato("paulo", self.contratos[0], "2030-02-28")
            self.log("contrato renovado")
        if d == date(2027, 3, 2):  # locatário que parou de pagar sai em 28/02; boleto de março já tinha saído
            contrato = self.contratos[8]
            r = servicos.encerrar_contrato("paulo", contrato, "2027-02-28", "inadimplência, entregou as chaves")
            self.conferir([p["tipo"] for p in r["pendencias"]] == ["cancelar_boleto"],
                          "encerrar com boleto emitido não pediu para cancelar o boleto")
            self.cancelar_agendados_do_contrato(contrato)
            self.log(f"contrato encerrado; {r['cobrancas_canceladas']} cobrança(s) cancelada(s), "
                     f"{len(r['pendencias'])} pendência(s)")
        if d == date(2027, 4, 15):  # o ex-locatário paga, por PIX, o mês mais antigo que deve
            cb = [c for c in consultas.listar_cobrancas(contrato_id=self.contratos[8], hoje=d)
                  if c["situacao_calculada"] == "atrasada"][0]
            r = servicos.registrar_pagamento("hermes", cb["id"], d, cb["saldo_centavos"], "pix",
                                             identificador_externo="E2E-DIVIDA")
            self.pago_pela_simulacao += cb["saldo_centavos"]
            self.conferir("contrato_encerrado" in [p["tipo"] for p in r["pendencias"]],
                          "pagamento em contrato encerrado não gerou pendência")
            self.log(f"ex-locatário pagou a dívida de {cb['competencia']}")
        if d == date(2027, 7, 8):  # locatário paga duas vezes o mesmo mês (dois PIX diferentes)
            cb = consultas.listar_cobrancas(competencia="2027-07", contrato_id=self.contratos[0], hoje=d)[0]
            r = servicos.registrar_pagamento("hermes", cb["id"], d, cb["valor_centavos"], "pix",
                                             identificador_externo="E2E-DUPLICADO")
            self.pago_pela_simulacao += cb["valor_centavos"]
            self.conferir("possivel_duplicidade" in [p["tipo"] for p in r["pendencias"]],
                          "pagamento duplicado não gerou pendência")
            self.log("locatário pagou julho duas vezes")
        if d == date(2027, 3, 10):  # a sala volta a ser alugada
            servicos.atualizar_imovel("paulo", self.imoveis[8], observacoes="pintada em março/2027")
            self.criar_contrato(8, 7, "2027-03-10", "2029-03-09", 10, 2900, "IPCA", None)
            self.log("sala alugada de novo")
        if d == date(2027, 5, 1):  # retificação de cadastro
            servicos.atualizar_locatario("paulo", self.locatarios[3], telefone="62 98888-7777", email="carlos@novo.com")

    def cancelar_agendados_do_contrato(self, contrato_id):
        with db.leitura() as con:
            ids = {r[0] for r in con.execute("SELECT id FROM cobrancas WHERE contrato_id = ? AND situacao <> 'normal'",
                                             (contrato_id,))}
        for cobranca_id in ids:
            self.cancelar_agendados(cobranca_id)

    def cancelar_agendados(self, cobranca_id):
        for dia in list(self.agendados):
            self.agendados[dia] = [a for a in self.agendados[dia] if a[0] != cobranca_id]

    # --- conferência no fim do mês ---
    def conferir_mes(self):
        d = self.hoje
        with db.leitura() as con:
            pagos = con.execute("SELECT COALESCE(SUM(valor_centavos), 0) FROM pagamentos "
                                "WHERE cancelado_em IS NULL").fetchone()[0]
            duplicadas = con.execute("SELECT contrato_id, competencia, COUNT(*) FROM cobrancas "
                                     "GROUP BY 1, 2 HAVING COUNT(*) > 1").fetchall()
        self.conferir(pagos == self.pago_pela_simulacao,
                      f"total pago no sistema {pagos} ≠ pago pela simulação {self.pago_pela_simulacao}")
        historico = consultas.historico_pagamentos()
        self.conferir(historico["total_centavos"] == pagos, "histórico financeiro não bate com os pagamentos")
        self.conferir(not duplicadas, f"cobranças duplicadas: {duplicadas}")
        todas = consultas.listar_cobrancas(hoje=d)
        for cb in todas:
            esperado = regras.situacao_cobranca(cb["situacao"], cb["valor_centavos"], cb["pago_centavos"],
                                                regras.para_data(cb["vencimento"]), d)
            self.conferir(cb["situacao_calculada"] == esperado, f"situação errada na cobrança {cb['id']}")
            if cb["boleto_identificador"] and cb["situacao"] == "normal":
                # o boleto nunca sai com valor anterior ao reajuste do ano
                self.conferir(not cb["reajuste_pendente"], f"boleto emitido com reajuste pendente: {cb['id']}")
        # cada contrato ativo tem todas as cobranças do início até o mês atual, sem buracos
        for c in consultas.listar_contratos(ativos=True, hoje=d):
            comps = [cb["competencia"] for cb in todas if cb["contrato_id"] == c["id"]]
            primeira = regras.primeira_competencia(regras.para_data(c["data_inicio"]), c["dia_vencimento"],
                                                   config.INICIO_COBRANCAS)
            if primeira <= regras.competencia_de(d):
                esperadas = []
                comp = primeira
                while regras.vencimento(comp, c["dia_vencimento"]) <= d + timedelta(days=30):
                    esperadas.append(comp)
                    comp = regras.proxima_competencia(comp)
                self.conferir(comps == esperadas, f"cobranças do contrato {c['id']}: {comps} ≠ {esperadas}")
        painel = consultas.painel(hoje=d)
        imoveis = consultas.listar_imoveis()
        ativos = {c["imovel_id"] for c in consultas.listar_contratos(ativos=True, hoje=d)}
        for im in imoveis:
            self.conferir((im["situacao"] == "alugado") == (im["id"] in ativos), f"situação do imóvel {im['id']}")
        atrasado = sum(cb["saldo_centavos"] for cb in todas if cb["situacao_calculada"] == "atrasada")
        self.conferir(painel["total_atrasado_centavos"] == atrasado, "total atrasado do painel não bate")
        comp = regras.competencia_de(d)
        devido = sum(cb["valor_centavos"] for cb in todas if cb["competencia"] == comp and cb["situacao"] == "normal")
        self.conferir(painel["resumo_do_mes"]["devido_centavos"] == devido, "devido do mês não bate")
        return painel

    # --- execução ---
    def rodar(self, verbose=False):
        original = regras.hoje
        regras.hoje = lambda: self.hoje
        try:
            self.cadastrar()
            resumo = []
            while self.hoje <= FIM:
                self.eventos_do_dia()
                self.rotina_hermes()
                amanha = self.hoje + timedelta(days=1)
                if amanha.day == 1:
                    painel = self.conferir_mes()
                    resumo.append((regras.competencia_de(self.hoje), painel))
                    if verbose:
                        r = painel["resumo_do_mes"]
                        print(f"{regras.competencia_de(self.hoje)}: devido {r['devido']:>13}  recebido "
                              f"{r['recebido']:>13}  atrasado total {painel['total_atrasado']:>12}  "
                              f"ocupação {painel['ocupacao_pct']}%  pendências {painel['pendencias_abertas']}")
                self.hoje = amanha
            self.hoje = FIM
            self.conferir_final()
        finally:
            regras.hoje = original
        return resumo

    def conferir_final(self):
        with db.leitura() as con:
            tipos = {r[0] for r in con.execute("SELECT DISTINCT tipo FROM pendencias")}
        esperados = {"pagamento_divergente", "boleto_desconhecido", "cancelar_boleto", "contrato_encerrado",
                     "possivel_duplicidade"}
        self.conferir(esperados <= tipos, f"faltaram pendências dos tipos {esperados - tipos}")
        alertas = consultas.alertas(hoje=self.hoje)
        self.conferir(any(a["tipo"] == "prazo_vencido" for a in alertas), "contrato com prazo vencido sem alerta")
        with db.leitura() as con:  # quem paga em dia (mesmo no dia útil do vencimento) nunca vira 'pagamento diferente'
            falsos = con.execute(
                "SELECT COUNT(*) FROM pendencias pe JOIN pagamentos pg ON pe.entidade = 'pagamento' AND pe.entidade_id = pg.id "
                "JOIN cobrancas cb ON cb.id = pg.cobranca_id WHERE pe.tipo = 'pagamento_divergente' AND cb.contrato_id IN (%s)"
                % ",".join(str(c) for c, p in self.perfil.items() if p == "pontual")).fetchone()[0]
        self.conferir(falsos == 0, f"{falsos} pendência(s) falsa(s) para locatários pontuais")
        devedores = {g["contrato_id"] for g in consultas.inadimplentes(hoje=self.hoje)}
        self.conferir(self.contratos[8] in devedores, "dívida do contrato encerrado sumiu dos inadimplentes")


def main():
    pasta = Path(tempfile.mkdtemp())
    config.DB_PATH = str(pasta / "simulacao.db")
    config.DOCS_DIR = str(pasta / "documentos")
    config.INICIO_COBRANCAS = "2026-10"
    inicio = time.time()
    sim = Simulacao()
    sim.rodar(verbose=True)
    with db.leitura() as con:
        n = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in ("imoveis", "locatarios", "contratos", "cobrancas", "pagamentos", "pendencias", "auditoria")}
        tipos = con.execute("SELECT tipo, COUNT(*) FROM pendencias GROUP BY 1 ORDER BY 2 DESC").fetchall()
    print(f"\nRegistros: {n}")
    print(f"Boletos emitidos: {sim.boletos_emitidos}; baixas repetidas de propósito: {sim.baixas_repetidas}")
    print("Pendências por tipo:", {t: q for t, q in tipos})
    print("\nEventos:")
    for e in sim.eventos:
        print(" ", e)
    t = time.time()
    consultas.painel(hoje=FIM)
    print(f"\nPainel com 15 meses de dados: {1000 * (time.time() - t):.0f} ms. Simulação: {time.time() - inicio:.0f} s.")
    print(f"Arquivo do banco: {Path(config.DB_PATH).stat().st_size // 1024} KB")
    print("\nCONFERÊNCIA:", "tudo bateu, nenhum erro." if not sim.violacoes else f"{len(sim.violacoes)} erro(s):")
    for v in sim.violacoes[:30]:
        print("  -", v)


if __name__ == "__main__":
    main()
