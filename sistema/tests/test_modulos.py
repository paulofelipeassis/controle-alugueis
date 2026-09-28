"""O núcleo descobre os módulos sozinho e um módulo com defeito não derruba o painel."""
from types import SimpleNamespace

from sistema import consultas, modulos


def test_modulos_sao_descobertos_pelas_pastas():
    """Cada pasta com __init__.py dentro de sistema/modulos é um módulo; nenhum deles é obrigatório."""
    em_disco = sorted(p.name for p in modulos.PASTA.iterdir() if (p / "__init__.py").is_file())
    assert modulos.nomes() == em_disco
    for nome in modulos.nomes():
        assert modulos.carregar(nome, "nao_existe") is None  # parte que o módulo não tem: ignorada, sem erro


def test_avisos_dos_modulos_entram_nos_alertas(monkeypatch, cenario):
    fake = SimpleNamespace(alertas=lambda hoje: [
        {"tipo": "aviso_do_modulo", "contrato_id": cenario["contrato"], "mensagem": f"olá {hoje}"}])
    monkeypatch.setattr(modulos, "nomes", lambda: ["fake"])
    monkeypatch.setattr(modulos, "carregar", lambda nome, parte: fake if parte == "alertas" else None)
    tipos = [a["tipo"] for a in consultas.alertas(hoje="2026-10-01")]
    assert "aviso_do_modulo" in tipos
    assert any(a["tipo"] == "aviso_do_modulo" for a in consultas.painel(hoje="2026-10-01")["alertas"])


def test_modulo_com_defeito_nao_derruba_o_painel(monkeypatch, cenario):
    def quebra(hoje):
        raise RuntimeError("bug no módulo")

    monkeypatch.setattr(modulos, "nomes", lambda: ["quebrado"])
    monkeypatch.setattr(modulos, "carregar", lambda nome, parte: SimpleNamespace(alertas=quebra))
    alertas = consultas.alertas(hoje="2026-10-01")
    erro = [a for a in alertas if a["tipo"] == "erro_de_modulo"]
    assert len(erro) == 1 and "'quebrado'" in erro[0]["mensagem"] and "bug no módulo" not in erro[0]["mensagem"]
    assert consultas.painel(hoje="2026-10-01")["imoveis_total"] == 1  # o resto do painel segue normal
