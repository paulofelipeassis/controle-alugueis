import asyncio
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

from sistema import consultas, db
from sistema import mcp_server as m
from sistema.regras import ErroDeNegocio


def test_fluxo_completo_do_hermes():
    imovel = m.cadastrar_imovel("Anel Viário", "Apto 101", "Rua A, 1", iptu_anual="1.234,56")["imovel_id"]
    locatario = m.cadastrar_locatario("Maria Souza", "123.456.789-00", "maria@x.com")["locatario_id"]
    contrato = m.criar_contrato(imovel, locatario, "2026-10-05", "2027-10-04", 10, "1.500,00")["contrato_id"]
    assert consultas.obter("imovel", imovel)["iptu_anual_centavos"] == 123456

    pendentes = [c for c in m.cobrancas_sem_boleto(dias=60) if c["contrato_id"] == contrato]
    cobranca = pendentes[0]
    assert cobranca["locatario_email"] == "maria@x.com" and cobranca["valor"] == "R$ 1.500,00"
    m.registrar_boleto(cobranca["id"], "Caixa", "NN-123", "1049...", "https://banco/boleto.pdf")
    m.marcar_boleto_enviado(cobranca["id"])
    r = m.registrar_pagamento_boleto("NN-123", cobranca["vencimento"], "1.500,00")
    assert r["registrado"] and r["pendencias"] == []
    assert m.registrar_pagamento_boleto("NN-123", cobranca["vencimento"], "1.500,00")["ja_existia"]

    extrato = m.extrato_contrato(contrato)
    assert extrato["cobrancas"][0]["situacao_calculada"] == "paga"
    with db.leitura() as con:
        quem = {linha[0] for linha in con.execute("SELECT quem FROM auditoria WHERE acao <> 'gerar_cobrancas'")}
    assert quem == {"hermes"}


def test_erro_de_negocio_chega_ao_hermes():
    with pytest.raises(ErroDeNegocio, match="CPF/CNPJ inválido"):
        m.cadastrar_locatario("X", "123", "x@x.com")


def test_ferramentas_so_de_pessoas_nao_existem():
    nomes = {t.name for t in asyncio.run(m.mcp.list_tools())}
    assert {"painel", "registrar_pagamento_boleto", "criar_contrato"} <= nomes
    proibidas = {"cancelar_pagamento", "isentar_cobranca", "cancelar_cobranca", "editar_valor_cobranca",
                 "resolver_pendencia", "apagar_imovel", "apagar_locatario", "apagar_contrato", "criar_usuario"}
    assert not nomes & proibidas


def _porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def servidor(tmp_path):
    porta = _porta_livre()
    env = {**os.environ, "MCP_TOKEN": "token-de-teste", "MCP_PORT": str(porta),
           "DB_PATH": str(tmp_path / "rede.db"), "DOCS_DIR": str(tmp_path / "docs")}
    proc = subprocess.Popen([sys.executable, "-m", "sistema.mcp_server"], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{porta}/mcp"
    for _ in range(100):
        try:
            httpx.get(url, timeout=0.2)
            break
        except httpx.TransportError:
            time.sleep(0.1)
    yield url
    proc.terminate()
    proc.wait(timeout=10)


def test_rede_exige_token(servidor):
    resposta = httpx.post(servidor, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resposta.status_code == 401


def test_rede_com_cliente_mcp(servidor):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def conversa():
        async with streamablehttp_client(servidor, headers={"Authorization": "Bearer token-de-teste"}) as (l, e, _):
            async with ClientSession(l, e) as sessao:
                await sessao.initialize()
                ferramentas = await sessao.list_tools()
                ok = await sessao.call_tool("cadastrar_imovel", {"grupo": "G", "unidade": "U", "endereco": "E"})
                erro = await sessao.call_tool("cadastrar_locatario",
                                              {"nome": "X", "cpf_cnpj": "1", "email": "x@x.com"})
                return ferramentas, ok, erro

    ferramentas, ok, erro = asyncio.run(conversa())
    assert len(ferramentas.tools) == 31
    assert not ok.isError and '"imovel_id"' in ok.content[0].text
    assert erro.isError and "CPF/CNPJ inválido" in erro.content[0].text
