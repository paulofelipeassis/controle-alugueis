"""Testes do módulo opcional documentos."""
import pytest

from sistema import db, servicos
from sistema.modulos import documentos
from sistema.modulos.documentos import mcp as ferramentas
from sistema.regras import ErroDeNegocio


def test_salvar_registrar_e_listar(cenario):
    doc = documentos.salvar("t", "contrato", cenario["contrato"], "contrato-assinado", "scan.PDF", b"%PDF")
    doc2 = documentos.salvar("t", "contrato", cenario["contrato"], "contrato-assinado", "scan.pdf", b"%PDF")
    caminhos = [d["caminho"] for d in documentos.listar("contrato", cenario["contrato"])]
    assert caminhos == ["imoveis/Anel Viario - Apto 101/contratos/2026-10 - Maria Souza/contrato-assinado.pdf",
                        "imoveis/Anel Viario - Apto 101/contratos/2026-10 - Maria Souza/contrato-assinado-2.pdf"]
    assert doc != doc2
    # Registrar de novo o mesmo arquivo devolve o mesmo documento (o Hermes pode repetir).
    assert documentos.registrar("hermes", "contrato", cenario["contrato"], "contrato-assinado", caminhos[0]) == doc
    assert documentos.listar("imovel", cenario["imovel"]) == []
    with pytest.raises(ErroDeNegocio, match="inválido"):
        documentos.registrar("hermes", "contrato", cenario["contrato"], "x", "../../etc/passwd")
    with pytest.raises(ErroDeNegocio, match="Entidade inválida"):
        documentos.listar("pessoa", 1)


def test_apagar_cadastro_apaga_a_ligacao(cenario):
    livre = servicos.cadastrar_imovel("t", "Centro", "Sala 1", "Rua C")
    documentos.salvar("t", "imovel", livre, "foto", "fachada.jpg", b"img")
    servicos.apagar_imovel("t", livre)  # o núcleo não sabe que o módulo existe
    with db.leitura() as con:
        assert con.execute("SELECT COUNT(*) FROM documentos").fetchone()[0] == 0


def test_ferramentas_do_hermes(cenario):
    documentos.salvar("t", "locatario", cenario["locatario"], "documento-pessoal", "rg.jpg", b"img")
    resposta = ferramentas.listar_documentos("locatario", cenario["locatario"])
    assert resposta["quantidade"] == 1
    lista = resposta["itens"]
    assert lista[0]["caminho"] == "locatarios/12345678900 - Maria Souza/rg.jpg"
    assert ferramentas.registrar_documento("locatario", cenario["locatario"], "documento-pessoal",
                                           lista[0]["caminho"])["documento_id"] == lista[0]["id"]


def test_upload_e_download_pela_web(cliente):
    imovel = servicos.cadastrar_imovel("t", "Anel Viário", "Apto 101", "E")
    r = cliente.post("/documentos", data={"entidade": "imovel", "entidade_id": imovel, "tipo": "foto",
                                          "voltar": f"/imoveis/{imovel}"},
                     files={"arquivo": ("Fachada.JPG", b"imagem", "image/jpeg")})
    assert "Documento enviado" in r.text and "fachada.jpg" in r.text
    doc = documentos.listar("imovel", imovel)[0]
    assert doc["caminho"] == "imoveis/Anel Viario - Apto 101/imovel/fachada.jpg"
    assert cliente.get("/arquivo/imoveis/Anel%20Viario%20-%20Apto%20101/imovel/fachada.jpg").content == b"imagem"
