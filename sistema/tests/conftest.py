from datetime import date

import pytest

from sistema import config, regras, servicos

HOJE = date(2026, 9, 27)


@pytest.fixture(autouse=True)
def banco_temporario(tmp_path, monkeypatch):
    """Cada teste usa um banco e uma pasta de documentos novos."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "teste.db"))
    monkeypatch.setattr(config, "DOCS_DIR", str(tmp_path / "documentos"))
    monkeypatch.setattr(config, "INICIO_COBRANCAS", "2026-10")
    # Data fixa: os testes não podem mudar de resultado com a passagem do tempo.
    monkeypatch.setattr(regras, "hoje", lambda: HOJE)
    return tmp_path


@pytest.fixture
def cenario():
    """Um imóvel, um locatário e um contrato de R$ 1.500,00 com vencimento dia 10, desde 05/10/2026."""
    imovel = servicos.cadastrar_imovel("teste", "Anel Viário", "Apto 101", "Rua A, 1")
    locatario = servicos.cadastrar_locatario("teste", "Maria Souza", "123.456.789-00", "maria@exemplo.com")
    contrato = servicos.criar_contrato("teste", imovel, locatario, "2026-10-05", "2027-10-04", 10, 150000,
                                       indice_reajuste="IGP-M")
    return {"imovel": imovel, "locatario": locatario, "contrato": contrato}
