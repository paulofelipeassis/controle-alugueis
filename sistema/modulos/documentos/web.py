"""Páginas do módulo documentos: envio de arquivo e o bloco 'Documentos' das fichas."""
from fastapi import APIRouter, Request

from sistema.modulos import documentos
from sistema.regras import ErroDeNegocio
from sistema.web_comum import acao, ler_form, local, quem, templates

router = APIRouter()
templates.env.globals.update(documentos_de=documentos.listar, TIPOS_DOCUMENTO=documentos.TIPOS)


@router.post("/documentos")
async def enviar(request: Request):
    form = await ler_form(request)
    arquivo = form.get("arquivo")

    def salvar():
        if arquivo is None or not getattr(arquivo, "filename", ""):
            raise ErroDeNegocio("Escolha um arquivo.")
        documentos.salvar(quem(request), form.get("entidade"), int(form.get("entidade_id")), form.get("tipo"),
                          arquivo.filename, arquivo.file.read(), form.get("descricao"))

    return acao(request, local(form.get("voltar")), salvar, "Documento enviado.")
