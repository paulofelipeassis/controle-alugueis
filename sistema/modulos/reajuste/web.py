"""Página do módulo reajuste: calcula a sugestão e mostra o formulário já preenchido."""
from fastapi import APIRouter, Request

from sistema.modulos import reajuste
from sistema.web_comum import pagina

router = APIRouter()


@router.get("/contratos/{contrato_id}/reajuste")
def calcular(request: Request, contrato_id: int):
    # O formulário envia para POST /contratos/{id}/reajuste, que é do núcleo (registrar_reajuste).
    return pagina(request, "reajuste/calcular.html", s=reajuste.sugerir(contrato_id))
