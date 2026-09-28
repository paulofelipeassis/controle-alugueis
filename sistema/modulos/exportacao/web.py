"""Páginas do módulo exportação: os dois downloads de planilha."""
from fastapi import APIRouter
from fastapi.responses import Response

from sistema.modulos import exportacao
from sistema.web_comum import int_ou_none

router = APIRouter()


def _planilha(conteudo, nome):
    return Response(conteudo.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/exportar/pagamentos.csv")
def pagamentos(data_de: str = "", data_ate: str = "", grupo: str = "", locatario_id: str = "", cancelados: str = ""):
    return _planilha(exportacao.pagamentos_csv(data_de or None, data_ate or None, grupo or None,
                                               int_ou_none(locatario_id), incluir_cancelados=cancelados == "on"),
                     "pagamentos.csv")


@router.get("/exportar/recebimentos.csv")
def recebimentos(ano: str = ""):
    return _planilha(exportacao.recebimentos_do_ano_csv(ano), f"recebimentos-{int(ano)}.csv")
