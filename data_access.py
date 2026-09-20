# data_access.py
"""
Ponto único de acesso à planilha "Controle de Aluguéis" no Google Sheets.

Antes desse módulo, cada página em pages/ reimplementava sua própria versão
de "abrir conexão" e "carregar aba como DataFrame", com pequenas diferenças
(algumas tratavam erro, outras não; algumas convertiam tipos de coluna,
outras não). Este módulo centraliza isso, junto com as operações de escrita
e a sincronização entre Imoveis.Status e Contratos.Status_Contrato.
"""
import logging

import gspread
import numpy as np
import pandas as pd
import streamlit as st

SHEET_NAME = "Controle de Aluguéis"

# Colunas conhecidas em mais de uma aba, coeridas para um tipo consistente
# sempre que presentes.
ID_COLUMNS = {"ID_Contrato", "ID_Imovel"}
NUMERIC_COLUMNS = {
    "Valor_Aluguel_Base", "Dia_Vencimento", "Valor_Total_Pago",
    "Valor_da_Garantia", "Valor_IPTU_Anual",
}
DATE_COLUMNS = {"Data_Inicio", "Data_Fim", "Data_Pagamento"}

# Coluna "Status" na aba Imoveis (índice 1-based usado pelo gspread).
IMOVEIS_STATUS_COLUMN = 5

logger = logging.getLogger("controle_alugueis")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# --- CONEXÃO ---
@st.cache_resource
def get_connection():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return gc.open(SHEET_NAME)


# --- LEITURA ---
def _parse_locale_number(value):
    """get_all_values() devolve o valor *formatado* da célula, não o número
    bruto — numa planilha com locale pt-BR, uma célula numérica com casas
    decimais volta como string com vírgula ('1234,56'), que pd.to_numeric não
    entende (vira NaN -> 0 depois do fillna, apagando o valor em silêncio).
    Normaliza pro formato com ponto antes de converter.
    """
    if isinstance(value, str):
        s = value.strip()
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        return s
    return value


def _coerce_types(df):
    for col in ID_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype(str)
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].apply(_parse_locale_number), errors="coerce").fillna(0)
    for col in DATE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _fetch_worksheet_df(worksheet_name):
    try:
        worksheet = get_connection().worksheet(worksheet_name)
        data = worksheet.get_all_values()
    except Exception:
        logger.exception("Erro ao carregar a aba '%s'", worksheet_name)
        return pd.DataFrame()

    if not data:
        return pd.DataFrame()

    headers = data[0]
    # Aba só com cabeçalho (nenhum lançamento ainda, por exemplo): mantém as
    # colunas certas com 0 linhas, em vez de devolver um DataFrame sem nenhuma
    # coluna — senão qualquer acesso por nome de coluna (`df['Status_Lancamento']`)
    # explode com KeyError mesmo a aba existindo e tendo cabeçalho válido.
    df = pd.DataFrame(data[1:], columns=headers) if len(data) > 1 else pd.DataFrame(columns=headers)
    return _coerce_types(df)


@st.cache_data(ttl=600)
def load_data(worksheet_name):
    """Carrega uma aba como DataFrame. Cache de 10 min — uso normal (dashboards, consultas)."""
    return _fetch_worksheet_df(worksheet_name)


@st.cache_data(ttl=30)
def load_data_fresh(worksheet_name):
    """Mesma coisa, cache de 30s — para páginas de edição, que precisam de dado mais recente antes de sobrescrever uma linha."""
    return _fetch_worksheet_df(worksheet_name)


def load_data_uncached(worksheet_name):
    """Sem cache algum — para checagens que precisam do estado atual garantido (ex: checar duplicidade de ID antes de cadastrar)."""
    return _fetch_worksheet_df(worksheet_name)


# --- ESCRITA ---
def _col_letter(n):
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _to_native(value):
    """Converte escalares do NumPy (int64/float64/bool_) para tipos nativos do
    Python. Valores de colunas coeridas por _coerce_types (ex: dados_contrato['Valor_da_Garantia'])
    chegam como numpy.int64/float64 — o gspread real serializa a requisição em
    JSON pra falar com a API do Google, e json.dumps não sabe lidar com esses
    tipos (`TypeError: Object of type int64 is not JSON serializable`). Isso só
    aparece contra a API de verdade, não contra um mock ingênuo.
    """
    if isinstance(value, np.generic):
        return value.item()
    return value


def append_row(worksheet_name, row_values):
    try:
        get_connection().worksheet(worksheet_name).append_row([_to_native(v) for v in row_values])
        st.cache_data.clear()
    except Exception:
        logger.exception("Erro ao adicionar linha na aba '%s'", worksheet_name)
        raise


def update_row(worksheet_name, id_value, row_values):
    """Sobrescreve a linha inteira cujo ID (coluna A) é id_value, cobrindo len(row_values) colunas a partir de A."""
    try:
        worksheet = get_connection().worksheet(worksheet_name)
        cell = worksheet.find(str(id_value), in_column=1)
        if cell is None:
            raise ValueError(f"ID '{id_value}' não encontrado na aba '{worksheet_name}'.")
        last_col = _col_letter(len(row_values))
        worksheet.update(f"A{cell.row}:{last_col}{cell.row}", [[_to_native(v) for v in row_values]])
        st.cache_data.clear()
    except Exception:
        logger.exception("Erro ao atualizar linha (ID=%s) na aba '%s'", id_value, worksheet_name)
        raise


def update_cell(worksheet_name, id_value, column_index, new_value):
    """Atualiza uma única célula da linha cujo ID (coluna A) é id_value."""
    try:
        worksheet = get_connection().worksheet(worksheet_name)
        cell = worksheet.find(str(id_value))
        if cell is None:
            raise ValueError(f"ID '{id_value}' não encontrado na aba '{worksheet_name}'.")
        worksheet.update_cell(cell.row, column_index, _to_native(new_value))
        st.cache_data.clear()
    except Exception:
        logger.exception("Erro ao atualizar célula (ID=%s, coluna=%s) na aba '%s'", id_value, column_index, worksheet_name)
        raise


# --- OPERAÇÕES DE DOMÍNIO (mantêm Imoveis.Status e Contratos.Status_Contrato em sincronia) ---
def proximo_id_lancamento():
    """Reproduz o esquema de ID sequencial já usado: contagem de linhas (incluindo cabeçalho) da aba."""
    worksheet = get_connection().worksheet("Lancamentos_Financeiros")
    return len(worksheet.get_all_values())


def cancelar_lancamento(id_lancamento):
    update_cell("Lancamentos_Financeiros", id_lancamento, 10, "Cancelado")


def criar_contrato(nova_linha_contrato, id_imovel):
    """Cria o contrato e marca o imóvel vinculado como 'Alugado'.

    Se a segunda escrita falhar, o contrato já foi criado — loga um erro
    explícito em vez de deixar a divergência passar em silêncio (é
    exatamente o cenário que o dashboard da Visão Geral hoje só detecta
    depois do fato).
    """
    append_row("Contratos", nova_linha_contrato)
    try:
        update_cell("Imoveis", id_imovel, IMOVEIS_STATUS_COLUMN, "Alugado")
    except Exception:
        logger.error(
            "Contrato %s foi criado, mas falhou ao marcar o imóvel %s como 'Alugado'. "
            "Corrija manualmente em Editar Imóvel.",
            nova_linha_contrato[0], id_imovel,
        )
        raise


def atualizar_contrato(id_contrato, novos_valores, id_imovel, novo_status_contrato):
    """Atualiza um contrato e, se o novo status não for 'Ativo', libera o imóvel
    vinculado (marca como 'Vago') — a menos que exista outro contrato ativo
    para o mesmo imóvel.
    """
    update_row("Contratos", id_contrato, novos_valores)
    if novo_status_contrato == "Ativo":
        return
    try:
        _liberar_imovel_se_sem_outro_contrato_ativo(id_imovel, id_contrato)
    except Exception:
        logger.error(
            "Contrato %s foi salvo com status '%s', mas falhou ao verificar/atualizar "
            "o status do imóvel %s. Corrija manualmente em Editar Imóvel.",
            id_contrato, novo_status_contrato, id_imovel,
        )
        raise


def _liberar_imovel_se_sem_outro_contrato_ativo(id_imovel, id_contrato_atual):
    df_contratos = load_data_fresh("Contratos")
    if df_contratos.empty:
        return
    outros_ativos = df_contratos[
        (df_contratos["ID_Imovel"] == str(id_imovel))
        & (df_contratos["ID_Contrato"] != str(id_contrato_atual))
        & (df_contratos["Status_Contrato"] == "Ativo")
    ]
    if outros_ativos.empty:
        update_cell("Imoveis", id_imovel, IMOVEIS_STATUS_COLUMN, "Vago")
