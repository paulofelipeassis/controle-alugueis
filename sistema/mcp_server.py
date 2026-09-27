"""Servidor MCP: as ferramentas que o Hermes usa para falar com o sistema.

Cada ferramenta só traduz parâmetros e chama `servicos` ou `consultas`, com
quem='hermes'. Nenhuma regra de negócio aqui. Ferramentas que só pessoas podem
usar (cancelar pagamento, isentar/cancelar cobrança, apagar, resolver
pendência, usuários) de propósito NÃO existem aqui.

Rodar: python -m sistema.mcp_server   (porta MCP_PORT, padrão 8001; caminho /mcp)
Toda requisição precisa do cabeçalho `Authorization: Bearer <MCP_TOKEN>`.
"""
import hmac
import json

from mcp.server.fastmcp import FastMCP

from sistema import config, consultas, regras, servicos

HERMES = "hermes"

INSTRUCOES = """\
Sistema de controle de aluguéis da família. Princípio: o sistema diz o que é devido,
o banco diz o que foi pago, e você (Hermes) executa e registra — não decide.
Valores em reais como texto no formato brasileiro ("1.234,56"). Datas no formato
AAAA-MM-DD. Competência = mês de vencimento da cobrança, no formato AAAA-MM.
Na dúvida, use criar_pendencia para uma pessoa olhar, em vez de adivinhar.
Leia o guia docs/hermes.md do projeto para as rotinas sugeridas."""

mcp = FastMCP(
    "controle-alugueis",
    instructions=INSTRUCOES,
    host="0.0.0.0",  # dentro do Docker; a proteção é o token abaixo
    stateless_http=True,
    json_response=True,
)


def _centavos(valor, campo="valor"):
    return regras.reais_para_centavos(valor, campo) if valor not in (None, "") else None


# ============ CONSULTAS ============
@mcp.tool()
def painel() -> dict:
    """Resumo geral de hoje: imóveis alugados/vagos, quanto é devido e quanto já entrou no
    mês, atrasados (de qualquer mês), alertas e número de pendências abertas."""
    return consultas.painel()


@mcp.tool()
def alertas() -> list:
    """Avisos que pedem ação: contratos terminando em 60 dias, contratos com prazo vencido
    (renovar ou encerrar), reajustes devidos, cobranças sem boleto vencendo em até 10 dias e
    boletos emitidos que ainda não foram enviados."""
    return consultas.alertas()


@mcp.tool()
def listar_imoveis(situacao: str | None = None) -> list:
    """Lista os imóveis com situação calculada e locatário atual.
    situacao (opcional): 'alugado', 'vago' ou 'em_manutencao'."""
    return consultas.listar_imoveis(situacao)


@mcp.tool()
def ficha_imovel(imovel_id: int) -> dict:
    """Dados do imóvel, situação, contrato atual, histórico de contratos e documentos."""
    return consultas.ficha_imovel(imovel_id)


@mcp.tool()
def buscar_locatarios(texto: str) -> list:
    """Procura locatários por parte do nome ou do CPF/CNPJ. Use antes de cadastrar, para não
    duplicar, e para achar o locatário de um comprovante."""
    return consultas.buscar_locatarios(texto)


@mcp.tool()
def ficha_locatario(locatario_id: int) -> dict:
    """Dados do locatário, todos os contratos (atuais e antigos), total atrasado, total a
    vencer e documentos."""
    return consultas.ficha_locatario(locatario_id)


@mcp.tool()
def listar_contratos(ativos: bool | None = True) -> list:
    """Lista contratos. ativos=true (padrão): só ativos; false: só encerrados; null: todos."""
    return consultas.listar_contratos(ativos)


@mcp.tool()
def extrato_contrato(contrato_id: int) -> dict:
    """Tudo de um contrato: dados, histórico de valores, cada cobrança (valor, pago, saldo,
    situação, boleto, pagamentos) e documentos. Use para escolher a cobrança certa antes de
    registrar um pagamento."""
    return consultas.extrato_contrato(contrato_id)


@mcp.tool()
def listar_cobrancas(competencia: str | None = None, situacao: str | None = None) -> list:
    """Lista cobranças. competencia (opcional): AAAA-MM. situacao (opcional): 'paga',
    'parcial', 'em_aberto', 'atrasada', 'isenta' ou 'cancelada'."""
    return consultas.listar_cobrancas(competencia, situacao)


@mcp.tool()
def cobrancas_sem_boleto(dias: int = 10) -> list:
    """Cobranças que precisam de boleto: com saldo, sem boleto, vencendo em até `dias` dias
    (ou já vencidas). Traz nome, CPF/CNPJ e e-mail do locatário, valor, vencimento, multa% e
    juros% ao mês — tudo que é preciso para emitir o boleto no banco."""
    return consultas.cobrancas_sem_boleto(dias)


@mcp.tool()
def boletos_em_aberto() -> list:
    """Cobranças com boleto emitido e ainda não pagas. Use para conferir no banco quais
    foram pagos."""
    return consultas.boletos_em_aberto()


@mcp.tool()
def inadimplentes() -> list:
    """Locatários com cobranças atrasadas, por contrato: saldo, valor com multa e juros,
    maior atraso em dias e as cobranças."""
    return consultas.inadimplentes()


@mcp.tool()
def resumo_do_mes(competencia: str | None = None) -> dict:
    """Quanto é devido, quanto foi recebido e quanto falta no mês (AAAA-MM; padrão: mês atual)."""
    return consultas.resumo_do_mes(competencia)


@mcp.tool()
def historico_pagamentos(data_de: str | None = None, data_ate: str | None = None, grupo: str | None = None,
                         imovel_id: int | None = None, locatario_id: int | None = None) -> dict:
    """Pagamentos válidos num período (datas AAAA-MM-DD), com filtros opcionais por grupo,
    imóvel ou locatário, e o total."""
    return consultas.historico_pagamentos(data_de, data_ate, grupo, imovel_id, locatario_id)


@mcp.tool()
def listar_pendencias() -> list:
    """Pendências abertas: coisas que uma pessoa precisa conferir ou resolver."""
    return consultas.listar_pendencias()


@mcp.tool()
def pasta_documento(entidade: str, entidade_id: int) -> dict:
    """Pasta (relativa à pasta de documentos) onde guardar arquivos de um 'imovel',
    'locatario' ou 'contrato'. Salve o arquivo lá e depois chame registrar_documento (ou
    passe o caminho como comprovante em registrar_pagamento)."""
    return {"pasta": servicos.pasta_documento(entidade, entidade_id)}


# ============ CADASTROS ============
@mcp.tool()
def cadastrar_imovel(grupo: str, unidade: str, endereco: str, iptu_anual: str | None = None,
                     medidor_saneago: str | None = None, medidor_enel: str | None = None,
                     observacoes: str | None = None) -> dict:
    """Cadastra um imóvel. grupo: nome do prédio/conjunto (ex.: 'Anel Viário'); unidade: ex.
    'Apto 101'. iptu_anual em reais ('1.234,56'). Devolve o id."""
    return {"imovel_id": servicos.cadastrar_imovel(
        HERMES, grupo, unidade, endereco, _centavos(iptu_anual, "IPTU"), medidor_saneago, medidor_enel,
        observacoes)}


@mcp.tool()
def cadastrar_locatario(nome: str, cpf_cnpj: str, email: str, telefone: str | None = None,
                        observacoes: str | None = None) -> dict:
    """Cadastra um locatário (pessoa ou empresa). CPF/CNPJ com ou sem pontuação. E-mail é
    obrigatório (os boletos vão por e-mail). Use buscar_locatarios antes, para não duplicar."""
    return {"locatario_id": servicos.cadastrar_locatario(HERMES, nome, cpf_cnpj, email, telefone, observacoes)}


@mcp.tool()
def atualizar_contato_locatario(locatario_id: int, telefone: str | None = None, email: str | None = None) -> dict:
    """Atualiza telefone e/ou e-mail de um locatário. Só os campos informados mudam."""
    campos = {k: v for k, v in {"telefone": telefone, "email": email}.items() if v is not None}
    servicos.atualizar_locatario(HERMES, locatario_id, **campos)
    return {"ok": True}


@mcp.tool()
def cadastrar_corretor(nome: str, telefone: str | None = None, email: str | None = None,
                       observacoes: str | None = None) -> dict:
    """Cadastra um corretor (quem intermediou e cobra o contrato)."""
    return {"corretor_id": servicos.cadastrar_corretor(HERMES, nome, telefone, email, observacoes)}


@mcp.tool()
def criar_contrato(imovel_id: int, locatario_id: int, data_inicio: str, data_fim_prevista: str,
                   dia_vencimento: int, valor_aluguel: str, corretor_id: int | None = None,
                   multa_pct: float = 2, juros_mes_pct: float = 1, garantia_tipo: str = "nenhuma",
                   garantia_valor: str | None = None, fiador: str | None = None,
                   indice_reajuste: str | None = None, observacoes: str | None = None) -> dict:
    """Cria um contrato ligando imóvel e locatário. Datas AAAA-MM-DD; valor_aluguel em reais
    ('1.500,00'); dia_vencimento 1 a 31. garantia_tipo: 'caucao', 'fiador', 'seguro_fianca'
    ou 'nenhuma'. indice_reajuste: ex. 'IGP-M' ou 'IPCA'. O imóvel não pode ter outro
    contrato ativo. As cobranças são geradas automaticamente."""
    return {"contrato_id": servicos.criar_contrato(
        HERMES, imovel_id, locatario_id, data_inicio, data_fim_prevista, dia_vencimento,
        _centavos(valor_aluguel, "valor do aluguel"), corretor_id, multa_pct, juros_mes_pct, garantia_tipo,
        _centavos(garantia_valor, "valor da garantia"), fiador, indice_reajuste, observacoes)}


@mcp.tool()
def registrar_reajuste(contrato_id: int, novo_valor: str, vigente_desde: str, motivo: str | None = None) -> dict:
    """Registra novo valor de aluguel a partir de uma data (AAAA-MM-DD). O valor antigo fica
    no histórico. Cobranças futuras sem boleto e sem pagamento passam a ter o valor novo.
    O cálculo do índice é seu; confirme com o Paulo antes."""
    servicos.registrar_reajuste(HERMES, contrato_id, _centavos(novo_valor, "novo valor"), vigente_desde, motivo)
    return {"ok": True}


@mcp.tool()
def renovar_contrato(contrato_id: int, nova_data_fim: str, novo_valor: str | None = None,
                     vigente_desde: str | None = None) -> dict:
    """Renova o mesmo contrato com nova data de fim (AAAA-MM-DD). Se houver novo valor, ele
    vale a partir de vigente_desde (padrão: dia seguinte ao fim atual)."""
    servicos.renovar_contrato(HERMES, contrato_id, nova_data_fim, _centavos(novo_valor, "novo valor"),
                              vigente_desde)
    return {"ok": True}


@mcp.tool()
def encerrar_contrato(contrato_id: int, data_encerramento: str, motivo: str) -> dict:
    """Encerra um contrato (AAAA-MM-DD). Cobranças que vencem depois e não foram pagas são
    canceladas; se alguma tinha boleto, é criada pendência para cancelar no banco. Dívidas
    anteriores continuam em aberto."""
    return servicos.encerrar_contrato(HERMES, contrato_id, data_encerramento, motivo)


# ============ BOLETOS E PAGAMENTOS ============
@mcp.tool()
def registrar_boleto(cobranca_id: int, banco: str, identificador: str, linha_digitavel: str | None = None,
                     link: str | None = None, substituir: bool = False) -> dict:
    """Registra na cobrança o boleto que você emitiu no banco. identificador = nosso número.
    Registrar de novo o mesmo boleto não dá erro. Para segunda via (boleto diferente), use
    substituir=true."""
    return servicos.registrar_boleto(HERMES, cobranca_id, banco, identificador, linha_digitavel, link, substituir)


@mcp.tool()
def marcar_boleto_enviado(cobranca_id: int) -> dict:
    """Marca que o boleto da cobrança foi enviado ao locatário."""
    servicos.marcar_boleto_enviado(HERMES, cobranca_id)
    return {"ok": True}


@mcp.tool()
def registrar_pagamento_boleto(identificador: str, data_pagamento: str, valor_pago: str,
                               comprovante_caminho: str | None = None) -> dict:
    """Baixa de boleto pago, pelo identificador (nosso número) informado pelo banco. Pode
    repetir sem medo: o mesmo boleto nunca gera dois pagamentos. Se o boleto não existir no
    sistema, cria uma pendência e não registra pagamento. Se o valor não bater, registra e
    cria pendência para conferência."""
    return servicos.registrar_pagamento_boleto(HERMES, identificador, data_pagamento,
                                               _centavos(valor_pago, "valor pago"), comprovante_caminho)


@mcp.tool()
def registrar_pagamento(cobranca_id: int, data_pagamento: str, valor_pago: str, forma: str,
                        identificador_externo: str | None = None, comprovante_caminho: str | None = None,
                        observacao: str | None = None) -> dict:
    """Registra um pagamento que não veio de boleto (ex.: comprovante de PIX). Escolha a
    cobrança com extrato_contrato. forma: 'pix', 'transferencia', 'dinheiro', 'boleto' ou
    'outro'. identificador_externo: código da transação (ex.: E2E do PIX) — evita registrar o
    mesmo pagamento duas vezes. comprovante_caminho: caminho do arquivo na pasta de
    documentos (use pasta_documento do contrato)."""
    return servicos.registrar_pagamento(HERMES, cobranca_id, data_pagamento, _centavos(valor_pago, "valor pago"),
                                        forma, identificador_externo, comprovante_caminho, observacao)


# ============ DOCUMENTOS E PENDÊNCIAS ============
@mcp.tool()
def registrar_documento(entidade: str, entidade_id: int, tipo: str, caminho: str,
                        descricao: str | None = None) -> dict:
    """Liga ao sistema um arquivo que você já salvou na pasta de documentos. entidade:
    'imovel', 'locatario' ou 'contrato'. tipo: ex. 'contrato-assinado', 'vistoria-entrada',
    'vistoria-saida', 'aditivo', 'documento-pessoal'. caminho: relativo à pasta de documentos."""
    return {"documento_id": servicos.registrar_documento(HERMES, entidade, entidade_id, tipo, caminho, descricao)}


@mcp.tool()
def criar_pendencia(descricao: str, tipo: str = "outro", entidade: str | None = None,
                    entidade_id: int | None = None) -> dict:
    """Cria uma pendência para uma pessoa olhar (ex.: comprovante ilegível, valor estranho,
    dúvida). Prefira isso a adivinhar."""
    return servicos.criar_pendencia(HERMES, tipo, descricao, entidade, entidade_id)


# ============ SERVIDOR HTTP COM TOKEN ============
class ExigeToken:
    """Middleware ASGI: recusa requisições HTTP sem `Authorization: Bearer <MCP_TOKEN>`."""

    def __init__(self, app, token):
        self.app = app
        self.esperado = f"Bearer {token}".encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            recebido = dict(scope.get("headers") or []).get(b"authorization", b"")
            if not hmac.compare_digest(recebido, self.esperado):
                corpo = json.dumps({"erro": "token inválido"}).encode()
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json")]})
                await send({"type": "http.response.body", "body": corpo})
                return
        await self.app(scope, receive, send)


def criar_app():
    if not config.MCP_TOKEN:
        raise SystemExit("Defina a variável MCP_TOKEN antes de iniciar o servidor MCP.")
    return ExigeToken(mcp.streamable_http_app(), config.MCP_TOKEN)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(criar_app(), host="0.0.0.0", port=config.MCP_PORT)
