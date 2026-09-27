import pytest

from sistema import consultas, db, servicos
from sistema.regras import ErroDeNegocio


def _acoes():
    with db.leitura() as con:
        return [linha["acao"] for linha in con.execute("SELECT acao FROM auditoria ORDER BY id")]


def test_cpf_duplicado():
    servicos.cadastrar_locatario("t", "Ana", "12345678900", "ana@x.com")
    with pytest.raises(ErroDeNegocio, match="CPF"):
        servicos.cadastrar_locatario("t", "Ana B", "123.456.789-00", "ana2@x.com")


def test_email_obrigatorio():
    with pytest.raises(ErroDeNegocio, match="e-mail"):
        servicos.cadastrar_locatario("t", "Ana", "12345678900", "")


def test_imovel_duplicado():
    servicos.cadastrar_imovel("t", "Anel Viário", "Apto 101", "Rua A")
    with pytest.raises(ErroDeNegocio, match="Já existe"):
        servicos.cadastrar_imovel("t", "Anel Viário", "Apto 101", "Rua B")


def test_um_contrato_ativo_por_imovel(cenario):
    outro = servicos.cadastrar_locatario("t", "João", "98765432100", "joao@x.com")
    with pytest.raises(ErroDeNegocio, match="já tem um contrato ativo"):
        servicos.criar_contrato("t", cenario["imovel"], outro, "2026-11-01", "2027-11-01", 5, 100000)
    servicos.encerrar_contrato("t", cenario["contrato"], "2026-10-31", "saída do locatário")
    novo = servicos.criar_contrato("t", cenario["imovel"], outro, "2026-11-01", "2027-11-01", 5, 100000)
    assert novo


def test_situacao_do_imovel_e_calculada(cenario):
    assert consultas.listar_imoveis()[0]["situacao"] == "alugado"
    servicos.encerrar_contrato("t", cenario["contrato"], "2026-10-31", "saída")
    assert consultas.listar_imoveis()[0]["situacao"] == "vago"
    servicos.atualizar_imovel("t", cenario["imovel"], em_manutencao=True)
    assert consultas.listar_imoveis()[0]["situacao"] == "em_manutencao"


def test_nao_apaga_cadastro_com_contrato(cenario):
    with pytest.raises(ErroDeNegocio):
        servicos.apagar_imovel("t", cenario["imovel"])
    with pytest.raises(ErroDeNegocio):
        servicos.apagar_locatario("t", cenario["locatario"])
    livre = servicos.cadastrar_imovel("t", "Centro", "Sala 1", "Rua C")
    servicos.apagar_imovel("t", livre)
    assert len(consultas.listar_imoveis()) == 1


def test_reajuste_mantem_valor_antigo(cenario):
    servicos.registrar_reajuste("t", cenario["contrato"], 160000, "2027-10-05", "IGP-M 2027")
    extrato = consultas.extrato_contrato(cenario["contrato"], hoje="2026-10-01")
    assert [v["valor_centavos"] for v in extrato["valores"]] == [150000, 160000]
    with pytest.raises(ErroDeNegocio, match="depois de"):
        servicos.registrar_reajuste("t", cenario["contrato"], 170000, "2027-01-01")


def test_renovacao(cenario):
    with pytest.raises(ErroDeNegocio, match="depois da atual"):
        servicos.renovar_contrato("t", cenario["contrato"], "2027-01-01")
    servicos.renovar_contrato("t", cenario["contrato"], "2028-10-04", novo_valor_centavos=165000)
    extrato = consultas.extrato_contrato(cenario["contrato"], hoje="2026-10-01")
    assert extrato["data_fim_prevista"] == "2028-10-04"
    assert extrato["valores"][-1]["vigente_desde"] == "2027-10-05"


def test_datas_do_contrato_validadas():
    imovel = servicos.cadastrar_imovel("t", "G", "U", "E")
    loc = servicos.cadastrar_locatario("t", "N", "12345678900", "n@x.com")
    with pytest.raises(ErroDeNegocio, match="fim prevista"):
        servicos.criar_contrato("t", imovel, loc, "2026-10-05", "2026-10-01", 10, 1000)
    with pytest.raises(ErroDeNegocio, match="maior que zero"):
        servicos.criar_contrato("t", imovel, loc, "2026-10-05", "2027-10-01", 10, 0)


def test_apagar_contrato_por_engano(cenario):
    servicos.apagar_contrato("t", cenario["contrato"])
    assert consultas.listar_contratos(ativos=None) == []


def test_auditoria(cenario):
    acoes = _acoes()
    assert {"cadastrar_imovel", "cadastrar_locatario", "criar_contrato"} <= set(acoes)
    with db.leitura() as con:
        assert con.execute("SELECT DISTINCT quem FROM auditoria WHERE acao = 'criar_contrato'").fetchone()[0] == "teste"


def test_usuario_e_login():
    servicos.criar_usuario("Paulo", "Paulo", "senha-segura")
    assert servicos.autenticar("paulo", "senha-segura") == {"login": "paulo", "nome": "Paulo"}
    assert servicos.autenticar("paulo", "errada") is None
    with pytest.raises(ErroDeNegocio):
        servicos.criar_usuario("paulo", "Outro", "outra-senha")
