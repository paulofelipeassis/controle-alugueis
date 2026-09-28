"""Páginas do módulo caução: registrar a devolução e o bloco da página do contrato."""
from fastapi import APIRouter, Request

from sistema.modulos import caucao
from sistema.web_comum import acao, centavos, ler_form, quem, templates

router = APIRouter()
templates.env.globals.update(caucao_de=caucao.situacao)


@router.post("/contratos/{contrato_id}/caucao")
async def devolver(request: Request, contrato_id: int):
    form = await ler_form(request)
    return acao(request, f"/contratos/{contrato_id}", lambda: caucao.registrar_devolucao(
        quem(request), contrato_id, form.get("data_devolucao"), centavos(form.get("valor_devolvido"), "valor devolvido"),
        centavos(form.get("descontos"), "descontos") or 0, form.get("motivo_descontos"), form.get("observacao")),
        "Devolução da caução registrada.")
