import streamlit as st
import gspread
import pandas as pd
import streamlit_authenticator as stauth
import re
from datetime import datetime

# --- CABEÇALHO CORRIGIDO PARA A NUVEM ---
try:
    credentials = dict(st.secrets['credentials'])
    cookie = dict(st.secrets['cookie'])
    authenticator = stauth.Authenticate(credentials, cookie['name'], cookie['key'], cookie['expiry_days'])
except KeyError:
    st.error("Erro na configuração de autenticação (Secrets). Por favor, faça login novamente.")
    st.stop()
if not st.session_state.get("authentication_status"):
    st.warning("Você precisa fazer login para acessar esta página.")
    st.stop()
st.sidebar.title(f"Bem-vindo, *{st.session_state['name']}* 👋")
authenticator.logout(location='sidebar')
# --- FIM DO CABEÇALHO ---


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Consulta de Imóveis", page_icon="🏘️", layout="wide")
st.title("🏘️ Consulta de Imóveis")
st.markdown("---")


# --- FUNÇÃO DE CACHE PARA CARREGAR DADOS (CORRIGIDA PARA A NUVEM) ---
@st.cache_data(ttl=600)
def load_data(worksheet_name):
    """Função para carregar uma aba da planilha como um DataFrame do Pandas."""
    try:
        # Lê as credenciais do Google a partir dos "Secrets"
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open("Controle de Aluguéis")
        worksheet = sh.worksheet(worksheet_name)

        data = worksheet.get_all_values()
        if not data or len(data) < 2: return pd.DataFrame()
        headers = data[0]
        return pd.DataFrame(data[1:], columns=headers)

    except Exception as e:
        st.error(f"Erro ao carregar a aba '{worksheet_name}': {e}")
        return pd.DataFrame()


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