"""Segurança e robustez das páginas: pontos encontrados na revisão antes de ir para o servidor."""
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from sistema import arquivos, config, consultas, servicos, web
from sistema.web import app


@pytest.fixture(autouse=True)
def zerar_limites():
    web.limite_por_login.falhas.clear()
    web.limite_por_ip.falhas.clear()


def _entrar(senha="senha-segura"):
    c = TestClient(app, raise_server_exceptions=False)
    return c, c.post("/login", data={"login": "paulo", "senha": senha})


def test_bloqueia_depois_de_cinco_senhas_erradas():
    servicos.criar_usuario("paulo", "Paulo", "senha-segura")
    servicos.criar_usuario("ana", "Ana", "outra-senha-1")
    c = TestClient(app)
    for _ in range(5):
        assert "incorretos" in c.post("/login", data={"login": "paulo", "senha": "errada-errada"}).text
    r = c.post("/login", data={"login": "paulo", "senha": "senha-segura"})  # mesmo com a senha certa
    assert "Muitas tentativas" in r.text and "Painel" not in r.text
    # Outra pessoa não é afetada, e o bloqueio não se aplica ao login de quem acertou antes.
    assert "Painel" in c.post("/login", data={"login": "ana", "senha": "outra-senha-1"}).text


def test_acertar_zera_a_contagem():
    servicos.criar_usuario("paulo", "Paulo", "senha-segura")
    c = TestClient(app)
    for _ in range(4):
        c.post("/login", data={"login": "paulo", "senha": "errada-errada"})
    assert "Painel" in c.post("/login", data={"login": "paulo", "senha": "senha-segura"}).text
    for _ in range(4):
        c.post("/login", data={"login": "paulo", "senha": "errada-errada"})
    assert "Muitas tentativas" not in c.post("/login", data={"login": "paulo", "senha": "errada-errada"}).text


def test_arquivo_perigoso_e_baixado_e_nao_aberto(cenario):
    servicos.criar_usuario("paulo", "Paulo", "senha-segura")
    c, _ = _entrar()
    pasta = arquivos.pasta("imovel", cenario["imovel"])  # só o núcleo: o módulo de documentos é opcional
    for nome, conteudo in [("pagina.html", b"<script>1</script>"), ("desenho.svg", b"<svg onload=1/>"),
                           ("recibo.pdf", b"%PDF-1.4")]:
        arquivos.salvar(pasta, nome.split(".")[0], "." + nome.split(".")[1], conteudo)
    base = "/arquivo/" + pasta.replace(" ", "%20") + "/"
    for nome in ("pagina.html", "desenho.svg"):
        r = c.get(base + nome)
        assert r.headers["content-disposition"].startswith("attachment"), nome
        assert r.headers["x-content-type-options"] == "nosniff"
    assert c.get(base + "recibo.pdf").headers["content-disposition"].startswith("inline")


def test_link_simbolico_para_fora_da_pasta_e_recusado(cenario, tmp_path):
    servicos.criar_usuario("paulo", "Paulo", "senha-segura")
    (tmp_path / "segredo.txt").write_text("nao abrir")
    raiz = arquivos.raiz()
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "atalho.txt").symlink_to(tmp_path / "segredo.txt")
    c, _ = _entrar()
    r = c.get("/arquivo/atalho.txt")
    assert "nao abrir" not in r.text and "inválido" in r.text


def test_numero_invalido_mostra_mensagem_e_nao_erro_500(cenario):
    servicos.criar_usuario("paulo", "Paulo", "senha-segura")
    c, _ = _entrar()
    r = c.post("/contratos/novo", data={"imovel_id": cenario["imovel"], "locatario_id": cenario["locatario"],
                                        "data_inicio": "2026-10-05", "data_fim_prevista": "2027-10-04",
                                        "valor_aluguel": "1.500,00", "dia_vencimento": "abc", "multa_pct": "2",
                                        "juros_mes_pct": "1", "garantia_tipo": "nenhuma"})
    assert r.status_code == 200 and "fora do formato" in r.text


def test_erro_inesperado_mostra_pagina_amigavel(monkeypatch):
    servicos.criar_usuario("paulo", "Paulo", "senha-segura")
    c, _ = _entrar()

    def quebra(*_a, **_k):
        raise RuntimeError("bug qualquer")

    monkeypatch.setattr(consultas, "painel", quebra)
    r = c.get("/")
    assert r.status_code == 500 and "Algo deu errado" in r.text and "bug qualquer" not in r.text


def test_cookie_de_sessao_e_seguro_no_servidor(tmp_path):
    """Com COOKIE_SEGURO=1 (servidor, HTTPS) o cookie de login só viaja por conexão segura."""
    codigo = (
        "from fastapi.testclient import TestClient\n"
        "from sistema import servicos\nfrom sistema.web import app\n"
        "servicos.criar_usuario('paulo', 'Paulo', 'senha-segura')\n"
        "r = TestClient(app, base_url='https://site').post('/login', data={'login': 'paulo', 'senha': 'senha-segura'},"
        " follow_redirects=False)\n"
        "print(r.headers['set-cookie'])\n")
    env = {**os.environ, "COOKIE_SEGURO": "1", "DB_PATH": str(tmp_path / "c.db"), "DOCS_DIR": str(tmp_path / "d")}
    saida = subprocess.run([sys.executable, "-c", codigo], env=env, capture_output=True, text=True).stdout
    assert "secure" in saida.lower()
    assert config.COOKIE_SEGURO is False  # desligado por padrão (teste e desenvolvimento em http)
