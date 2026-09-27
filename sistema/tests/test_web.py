import re

import pytest
from fastapi.testclient import TestClient

from sistema import consultas, servicos
from sistema.web import app


@pytest.fixture
def cliente():
    servicos.criar_usuario("paulo", "Paulo", "senha-segura")
    c = TestClient(app)
    r = c.post("/login", data={"login": "paulo", "senha": "senha-segura"})
    assert r.status_code == 200 and "Painel" in r.text
    return c


def test_sem_login_vai_para_login():
    c = TestClient(app)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    assert c.get("/saude").json() == {"ok": True}
    assert c.get("/static/estilo.css").status_code == 200


def test_login_errado():
    servicos.criar_usuario("paulo", "Paulo", "senha-segura")
    r = TestClient(app).post("/login", data={"login": "paulo", "senha": "errada"})
    assert "Login ou senha incorretos" in r.text


def _id(resposta, prefixo):
    return int(re.search(rf"{prefixo}/(\d+)$", str(resposta.url)).group(1))


def test_fluxo_completo(cliente):
    r = cliente.post("/imoveis/novo", data={"grupo": "Anel Viário", "unidade": "Apto 101", "endereco": "Rua A",
                                            "iptu_anual": "1.200,00"})
    assert "Imóvel cadastrado" in r.text and "IPTU anual: R$ 1.200,00" in r.text
    imovel = _id(r, "/imoveis")
    r = cliente.post("/locatarios/novo", data={"nome": "Maria Souza", "cpf_cnpj": "123.456.789-00",
                                               "email": "maria@x.com", "telefone": "62 99999-0000"})
    locatario = _id(r, "/locatarios")
    r = cliente.post("/contratos/novo", data={
        "imovel_id": imovel, "locatario_id": locatario, "data_inicio": "2026-10-05",
        "data_fim_prevista": "2027-10-04", "valor_aluguel": "1.500,00", "dia_vencimento": "10",
        "multa_pct": "2", "juros_mes_pct": "1", "garantia_tipo": "caucao", "garantia_valor": "3.000,00",
        "indice_reajuste": "IGP-M"})
    assert "Contrato criado" in r.text and "R$ 1.500,00" in r.text
    contrato = _id(r, "/contratos")

    cobranca = consultas.listar_cobrancas(contrato_id=contrato)[0]
    r = cliente.get(f"/pagamentos/novo?cobranca_id={cobranca['id']}")
    assert "Maria Souza" in r.text
    r = cliente.post("/pagamentos/novo", data={"cobranca_id": cobranca["id"], "data_pagamento": "2026-10-09",
                                               "valor": "1.500,00", "forma": "pix"},
                     files={"comprovante": ("recibo.pdf", b"%PDF-1.4", "application/pdf")})
    assert "Pagamento registrado" in r.text and "Paga" in r.text and "comprovante-2026-10.pdf" in r.text
    extrato = consultas.extrato_contrato(contrato)
    assert extrato["cobrancas"][0]["situacao_calculada"] == "paga"
    assert extrato["cobrancas"][0]["pagamentos"][0]["registrado_por"] == "paulo"

    # Todas as páginas abrem.
    for url in ["/", "/imoveis", f"/imoveis/{imovel}", f"/imoveis/{imovel}/editar", "/locatarios",
                "/locatarios?q=maria", f"/locatarios/{locatario}", f"/locatarios/{locatario}/editar", "/corretores",
                "/corretores/novo", "/contratos", "/contratos?status=todos", f"/contratos/{contrato}",
                f"/contratos/{contrato}/editar", "/contratos/novo", "/cobrancas", "/cobrancas?competencia=2026-10",
                f"/cobrancas/{cobranca['id']}", "/pagamentos", "/pagamentos?data_de=2026-10-01&grupo=Anel+Vi%C3%A1rio",
                "/pendencias", "/pendencias?todas=1", "/auditoria", "/senha"]:
        assert cliente.get(url).status_code == 200, url


def test_erro_de_negocio_aparece_no_formulario(cliente):
    cliente.post("/locatarios/novo", data={"nome": "Ana", "cpf_cnpj": "12345678900", "email": "a@x.com"})
    r = cliente.post("/locatarios/novo", data={"nome": "Ana 2", "cpf_cnpj": "123.456.789-00", "email": "b@x.com"})
    assert "Já existe um locatário" in r.text and 'value="Ana 2"' in r.text
    r = cliente.post("/imoveis/novo", data={"grupo": "G", "unidade": "U", "endereco": "E", "iptu_anual": "abc"})
    assert "IPTU inválido" in r.text


def test_acoes_do_contrato_e_cobranca(cliente):
    imovel = servicos.cadastrar_imovel("t", "G", "U", "E")
    loc = servicos.cadastrar_locatario("t", "N", "12345678900", "n@x.com")
    contrato = servicos.criar_contrato("t", imovel, loc, "2026-10-05", "2027-10-04", 10, 150000)
    cobranca = consultas.listar_cobrancas(contrato_id=contrato)[0]["id"]
    r = cliente.post(f"/cobrancas/{cobranca}/boleto", data={"banco": "Caixa", "identificador": "NN-1"})
    assert "Boleto registrado" in r.text
    r = cliente.post(f"/cobrancas/{cobranca}/enviado")
    assert "enviado em" in r.text
    r = cliente.post(f"/cobrancas/{cobranca}/isentar", data={"motivo": "acordo"})
    assert "Pendência criada" in r.text and "Isenta" in r.text
    r = cliente.post(f"/contratos/{contrato}/reajuste", data={"novo_valor": "1.600,00", "vigente_desde": "2026-01-01"})
    assert "precisa valer a partir" in r.text
    r = cliente.post(f"/contratos/{contrato}/encerrar", data={"data_encerramento": "2026-10-31", "motivo": "saída"})
    assert "Contrato encerrado" in r.text
    pendencia = consultas.listar_pendencias()[0]["id"]
    r = cliente.post(f"/pendencias/{pendencia}/resolver", data={"resolucao": "boleto cancelado na Caixa"})
    assert "Pendência resolvida" in r.text


def test_documentos_upload_e_download(cliente):
    imovel = servicos.cadastrar_imovel("t", "Anel Viário", "Apto 101", "E")
    r = cliente.post("/documentos", data={"entidade": "imovel", "entidade_id": imovel, "tipo": "foto",
                                          "voltar": f"/imoveis/{imovel}"},
                     files={"arquivo": ("Fachada.JPG", b"imagem", "image/jpeg")})
    assert "Documento enviado" in r.text and "fachada.jpg" in r.text
    doc = consultas.ficha_imovel(imovel)["documentos"][0]
    assert doc["caminho"] == "imoveis/Anel Viario - Apto 101/imovel/fachada.jpg"
    assert cliente.get(f"/documentos/{doc['id']}").content == b"imagem"


def test_id_inexistente_mostra_erro(cliente):
    r = cliente.get("/contratos/999")
    assert "não encontrado" in r.text


def test_trocar_senha(cliente):
    r = cliente.post("/senha", data={"atual": "senha-segura", "nova": "nova-senha-1", "repetir": "nova-senha-1"})
    assert "Senha alterada" in r.text
    assert servicos.autenticar("paulo", "nova-senha-1")



def test_reajuste_pela_web(cliente, monkeypatch):
    from sistema import reajuste

    imovel = servicos.cadastrar_imovel("t", "G", "U", "E")
    loc = servicos.cadastrar_locatario("t", "N", "12345678900", "n@x.com")
    dados = {"imovel_id": imovel, "locatario_id": loc, "data_inicio": "2024-10-05",
             "data_fim_prevista": "2027-10-04", "valor_aluguel": "1.500,00", "dia_vencimento": "5",
             "multa_pct": "2", "juros_mes_pct": "1", "garantia_tipo": "nenhuma", "indice_reajuste": "IGP-M"}
    r = cliente.post("/contratos/novo", data=dados)
    assert "último reajuste" in r.text  # contrato antigo sem a data do valor atual
    r = cliente.post("/contratos/novo", data={**dados, "valor_vigente_desde": "2025-10-05"})
    assert "Contrato criado" in r.text and "Calcular pelo IGP-M" in r.text
    contrato = int(str(r.url).rsplit("/", 1)[1])
    monkeypatch.setattr(reajuste, "ultimos_12_meses",
                        lambda indice: [(f"2025-{m:02d}", "0.5") for m in range(1, 13)])
    r = cliente.get(f"/contratos/{contrato}/reajuste")
    assert "6,17%" in r.text and 'value="1.592,55"' in r.text and 'value="2026-10-05"' in r.text
    r = cliente.post(f"/contratos/{contrato}/reajuste",
                     data={"novo_valor": "1.580,00", "vigente_desde": "2026-10-05", "motivo": "IGP-M combinado"})
    assert "Reajuste registrado" in r.text and "R$ 1.580,00 desde 05/10/2026" in r.text
