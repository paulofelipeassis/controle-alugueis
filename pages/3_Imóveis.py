import streamlit as st
from auth_utils import page_guard
from data_access import load_data

page_guard()


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Consulta de Imóveis", page_icon="🏘️", layout="wide")
st.title("🏘️ Consulta de Imóveis")
st.markdown("---")


# --- CARREGAMENTO DOS DADOS ---
df_imoveis = load_data("Imoveis")

# --- EXIBIÇÃO DA PÁGINA ---
if not df_imoveis.empty:
    st.header("Lista de Todos os Imóveis")

    # --- FILTROS ---
    st.sidebar.header("Filtros")

    grupos = ["Todos"] + sorted(list(df_imoveis['Grupo'].unique()))
    status_list = ["Todos"] + sorted(list(df_imoveis['Status'].unique()))

    grupo_selecionado = st.sidebar.selectbox("Filtrar por Grupo", grupos)
    status_selecionado = st.sidebar.selectbox("Filtrar por Status", status_list)

    # Aplica os filtros ao DataFrame
    df_filtrado = df_imoveis.copy()
    if grupo_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Grupo'] == grupo_selecionado]

    if status_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Status'] == status_selecionado]

    # Mostra a tabela de imóveis com os filtros aplicados
    st.dataframe(df_filtrado, use_container_width=True)

    st.info(f"Mostrando **{len(df_filtrado)}** de **{len(df_imoveis)}** imóveis.")

else:
    st.warning("Nenhum dado de imóvel encontrado na planilha.")