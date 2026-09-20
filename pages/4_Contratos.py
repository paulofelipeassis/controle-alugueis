import streamlit as st
from auth_utils import page_guard
from data_access import load_data

page_guard()


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Consulta de Contratos", page_icon="📝", layout="wide")
st.title("📝 Consulta de Contratos de Locação")
st.markdown("---")


# --- CARREGAMENTO DOS DADOS ---
df_contratos = load_data("Contratos")

# --- EXIBIÇÃO DA PÁGINA ---
if not df_contratos.empty:
    st.header("Lista de Todos os Contratos")

    # --- FILTROS ---
    st.sidebar.header("Filtros")

    gestores = ["Todos"] + sorted(list(df_contratos['Gestor_Responsavel'].unique()))
    status_list = ["Todos"] + sorted(list(df_contratos['Status_Contrato'].unique()))

    gestor_selecionado = st.sidebar.selectbox("Filtrar por Gestor", gestores)
    status_selecionado = st.sidebar.selectbox("Filtrar por Status do Contrato", status_list)

    # Aplica os filtros ao DataFrame
    df_filtrado = df_contratos.copy()
    if gestor_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Gestor_Responsavel'] == gestor_selecionado]

    if status_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Status_Contrato'] == status_selecionado]

    # Mostra a tabela de contratos com os filtros aplicados
    st.dataframe(df_filtrado, use_container_width=True)

    st.info(f"Mostrando **{len(df_filtrado)}** de **{len(df_contratos)}** contratos.")

else:
    st.warning("Nenhum dado de contrato encontrado na planilha.")