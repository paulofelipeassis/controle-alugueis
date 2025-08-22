import streamlit as st
import streamlit_authenticator as stauth
import gspread
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import re
import plotly.express as px
from copy import deepcopy # <-- ADICIONADO AQUI

# --- CABEÇALHO UNIVERSAL PARA A NUVEM ---
try:
    # Copia PROFUNDA dos segredos para um dict normal
    credentials = deepcopy(st.secrets['credentials']) # <-- ALTERADO AQUI
    cookie = dict(st.secrets['cookie'])

    authenticator = stauth.Authenticate(
        credentials,
        cookie['name'],
        cookie['key'],
        cookie['expiry_days']
    )
except KeyError:
    st.error("Erro na configuração de autenticação (Secrets). Por favor, faça login novamente.")
    st.stop()

# Verifica se o usuário está logado
if not st.session_state.get("authentication_status"):
    st.warning("Você precisa fazer login para acessar esta página.")
    st.stop()

# Mostra o nome do usuário e o botão de logout na barra lateral
st.sidebar.title(f"Bem-vindo, *{st.session_state['name']}* 👋")
authenticator.logout(location='sidebar')
# --- FIM DO CABEÇALHO ---

# O resto do seu código original da página vem DEPOIS disso...


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Consulta de Contratos", page_icon="📝", layout="wide")
st.title("📝 Consulta de Contratos de Locação")
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