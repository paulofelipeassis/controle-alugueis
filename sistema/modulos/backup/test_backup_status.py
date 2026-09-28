"""Testes do módulo opcional backup (aviso no painel)."""
from datetime import datetime, timedelta

import pytest

from sistema import config, regras
from sistema.modulos import backup as aviso
from scripts import backup as script


@pytest.fixture(autouse=True)
def pasta_de_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(config, "RCLONE_DESTINO", "")
    monkeypatch.setattr(regras, "agora", lambda: "2026-09-28 10:00:00")


def _gravar_ha(horas, **dados):
    quando = (datetime(2026, 9, 28, 10) - timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S")
    original = regras.agora
    regras.agora = lambda: quando
    try:
        aviso.gravar(**dados)
    finally:
        regras.agora = original


def test_nunca_rodou_avisa():
    s = aviso.situacao()
    assert s["nivel"] == "aviso" and "ainda não rodou" in s["mensagem"]
    assert aviso.precisa_agora() is True


def test_so_local_avisa_que_falta_o_drive():
    _gravar_ha(2, ok=True, arquivo="a.tar.gz", drive=None)
    s = aviso.situacao()
    assert s["nivel"] == "aviso" and "Google Drive não configurado" in s["mensagem"]


def test_tudo_certo():
    _gravar_ha(7, ok=True, arquivo="a.tar.gz", drive=True)
    s = aviso.situacao()
    assert s == {"nivel": "ok", "mensagem": "Último backup: 28/09 às 03:00, copiado no Google Drive."}
    assert aviso.precisa_agora() is False


def test_backup_que_falhou_vira_alerta_e_lembra_o_ultimo_bom():
    _gravar_ha(30, ok=True, arquivo="a.tar.gz", drive=True)
    _gravar_ha(1, ok=False, arquivo="b.tar.gz", drive=False, erro="rclone: token expirado")
    s = aviso.situacao()
    assert s["nivel"] == "erro" and "rclone: token expirado" in s["mensagem"] and "27/09 às 04:00" in s["mensagem"]
    assert aviso.precisa_agora() is True


def test_backup_parado_ha_mais_de_36_horas():
    _gravar_ha(40, ok=True, arquivo="a.tar.gz", drive=True)
    s = aviso.situacao()
    assert s["nivel"] == "erro" and "parado" in s["mensagem"]


def test_script_grava_o_status(cenario, monkeypatch):
    monkeypatch.setattr(config, "RCLONE_DESTINO", "drive:Backup")
    monkeypatch.setattr(script, "_enviar", lambda arquivo: None)
    script.fazer_backup()
    dados = aviso.ler()
    assert dados["ok"] is True and dados["drive"] is True and dados["arquivo"].endswith(".tar.gz")

    def falha(arquivo):
        raise RuntimeError("Google Drive fora do ar")

    monkeypatch.setattr(script, "_enviar", falha)
    with pytest.raises(RuntimeError):
        script.fazer_backup()
    dados = aviso.ler()
    assert dados["ok"] is False and dados["drive"] is False and "Google Drive fora do ar" in dados["erro"]
    assert dados["ultimo_sucesso"] == "2026-09-28 10:00:00"  # o último completo continua registrado


def test_painel_mostra_o_aviso(cliente):
    assert "ainda não rodou" in cliente.get("/").text
    _gravar_ha(2, ok=False, arquivo=None, drive=None, erro="disco cheio")
    r = cliente.get("/")
    assert "Atenção:" in r.text and "disco cheio" in r.text
