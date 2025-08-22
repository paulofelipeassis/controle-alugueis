import streamlit as st
import gspread
import pandas as pd
import streamlit_authenticator as stauth
import re
from datetime import datetime
from copy import deepcopy

# --- CABEÇALHO CORRIGIDO PARA A NUVEM (VERSÃO FINAL) ---
try:
    # Copia PROFUNDA dos segredos para um dict normal
    credentials = deepcopy(st.secrets['credentials'])
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


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Editar Imóvel", page_icon="🏡", layout="wide")
st.title("🏡 Editar Imóvel")
st.markdown("---")


# --- CONEXÃO COM A PLANILHA (USANDO SECRETS) ---
@st.cache_resource
def get_connection():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return gc.open("Controle de Aluguéis")


sh = get_connection()
imoveis_ws = sh.worksheet("Imoveis")


# --- FUNÇÃO DE CACHE PARA CARREGAR DADOS ---
@st.cache_data(ttl=30)
def load_imoveis():
    data = imoveis_ws.get_all_values()
    if len(data) < 2: return pd.DataFrame()
    headers = data[0]
    df = pd.DataFrame(data[1:], columns=headers)
    return df


df_imoveis = load_imoveis()

# --- PASSO 1: SELECIONAR O IMÓVEL PARA EDITAR ---
st.subheader("Passo 1: Selecione o Imóvel que Deseja Editar")

if not df_imoveis.empty:
    grupos = ["Todos"] + sorted(list(df_imoveis['Grupo'].unique()))
    grupo_selecionado = st.selectbox("Filtrar por Grupo", grupos)

    df_filtrado = df_imoveis.copy()
    if grupo_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Grupo'] == grupo_selecionado]

    imoveis_options = ["Selecione..."] + [f"{unidade} ({id_imovel})" for id_imovel, unidade in
                                          zip(df_filtrado['ID_Imovel'], df_filtrado['Unidade'])]
    imovel_selecionado_str = st.selectbox("Imóveis", options=imoveis_options)

    # --- PASSO 2: EXIBIR O FORMULÁRIO PREENCHIDO ---
    if imovel_selecionado_str != "Selecione...":
        id_imovel_selecionado = imovel_selecionado_str.split(" (")[-1][:-1]
        dados_imovel = df_imoveis[df_imoveis['ID_Imovel'] == id_imovel_selecionado].iloc[0]

        st.markdown("---")
        st.subheader("Passo 2: Edite as Informações Abaixo")

        with st.form("form_editar_imovel"):
            st.info(f"Editando o Imóvel: **{dados_imovel['ID_Imovel']}**")
            grupo = st.text_input("Grupo", value=dados_imovel['Grupo'])
            unidade = st.text_input("Unidade", value=dados_imovel['Unidade'])
            endereco = st.text_area("Endereço Completo", value=dados_imovel['Endereco_Completo'])
            status_options = ["Alugado", "Vago", "Em Manutenção", "Outro"]
            if dados_imovel['Status'] not in status_options:
                status_options.append(dados_imovel['Status'])
            status = st.selectbox("Status", options=status_options, index=status_options.index(dados_imovel['Status']))
            st.subheader("Dados Adicionais")
            col1, col2, col3 = st.columns(3)
            with col1:
                iptu_anual = st.number_input("Valor do IPTU Anual",
                                             value=float(dados_imovel.get('Valor_IPTU_Anual', 0)), step=100.0,
                                             format="%.2f")
            with col2:
                medidor_agua = st.text_input("Nº Medidor Saneago", value=dados_imovel.get('Num_Medidor_Saneago', ''))
            with col3:
                medidor_energia = st.text_input("Nº Medidor Enel", value=dados_imovel.get('Num_Medidor_Enel', ''))

            submitted = st.form_submit_button("Salvar Alterações")

            if submitted:
                with st.spinner("Salvando..."):
                    cell = imoveis_ws.find(id_imovel_selecionado)
                    novos_valores = [dados_imovel['ID_Imovel'], grupo, unidade, endereco, status, iptu_anual,
                                     medidor_agua, medidor_energia]
                    imoveis_ws.update(f'A{cell.row}:H{cell.row}', [novos_valores])
                    st.cache_data.clear()
                    st.success("Imóvel atualizado com sucesso!")
                    st.balloons()
else:
    st.warning("Nenhum dado de imóvel encontrado na planilha.")