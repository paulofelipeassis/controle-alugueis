"""Página do módulo proporcional: a decisão sobre o primeiro período, na página do contrato."""
from fastapi import APIRouter, Request

from sistema.modulos import proporcional
from sistema.regras import ErroDeNegocio
from sistema.web_comum import acao, ler_form, quem, templates

router = APIRouter()
templates.env.globals.update(sugestao_proporcional=proporcional.sugerir)


@router.post("/contratos/{contrato_id}/primeiro-periodo")
async def decidir(request: Request, contrato_id: int):
    form = await ler_form(request)

    def registrar():
        if form.get("escolha") not in ("proporcional", "cheio"):
            raise ErroDeNegocio("Escolha o valor proporcional ou o aluguel cheio.")
        return proporcional.decidir(quem(request), contrato_id, form["escolha"] == "proporcional")

    return acao(request, f"/contratos/{contrato_id}", registrar,
                lambda r: "Valor proporcional aplicado na primeira cobrança." if r["decisao"] == "proporcional"
                else "Mantido o aluguel cheio na primeira cobrança.")
