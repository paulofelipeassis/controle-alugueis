import streamlit as st
import gspread
import pandas as pd
import re
import streamlit_authenticator as stauth

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

st.set_page_config(page_title="Cadastrar Novo Imóvel", page_icon="🏢")
st.title("🏢 Cadastrar Novo Imóvel")
st.markdown("---")

@st.cache_resource
def get_connection():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return gc.open("Controle de Aluguéis")
sh = get_connection()
imoveis_ws = sh.worksheet("Imoveis")

def gerar_id_imovel(grupo, unidade):
    prefixo_grupo = re.sub(r'[^A-Z\s]', '', str(grupo).upper()).replace(' ', '')[:4]
    unidade_limpa = re.sub(r'[^0-9A-Z]', '', str(unidade).upper())
    return f"{prefixo_grupo}-{unidade_limpa}"

st.subheader("Passo 1: Defina o Grupo do Imóvel")
imoveis_data = imoveis_ws.get_all_values()
if len(imoveis_data) > 1:
    df_imoveis = pd.DataFrame(imoveis_data[1:], columns=imoveis_data[0])
    grupos_existentes = sorted(list(df_imoveis['Grupo'].unique()))
else:
    grupos_existentes = []
opcoes_grupo = grupos_existentes + ["--- Adicionar Novo Grupo ---"]
grupo_selecionado = st.selectbox("Grupo do Imóvel", options=opcoes_grupo, key="grupo_selector")
novo_grupo = ""
if grupo_selecionado == "--- Adicionar Novo Grupo ---":
    novo_grupo = st.text_input("Digite o nome do Novo Grupo", key="novo_grupo_input")
grupo_final = novo_grupo.strip() if grupo_selecionado == "--- Adicionar Novo Grupo ---" else grupo_selecionado

if grupo_final:
    st.markdown("---")
    st.subheader(f"Passo 2: Preencha os Dados do Imóvel para o Grupo '{grupo_final}'")
    with st.form("form_cadastrar_imovel", clear_on_submit=True):
        col_unidade1, col_unidade2 = st.columns(2)
        with col_unidade1:
            tipo_unidade = st.selectbox("Tipo de Unidade", ["Apto", "Casa", "Sala", "Loja"])
        with col_unidade2:
            numero_unidade = st.text_input("Número / Identificador da Unidade", help="Ex: 101, 203B, Térreo")
        endereco = st.text_area("Endereço Completo")
        st.subheader("Dados Adicionais")
        col1, col2, col3 = st.columns(3)
        with col1:
            iptu_anual = st.number_input("Valor do IPTU Anual", value=0.0, step=100.0, format="%.2f")
        with col2:
            medidor_agua = st.text_input("Nº Medidor Saneago")
        with col3:
            medidor_energia = st.text_input("Nº Medidor Enel")
        submitted = st.form_submit_button("Cadastrar Imóvel")
        if submitted:
            unidade_final = f"{tipo_unidade} {numero_unidade.strip()}"
            if not all([numero_unidade.strip(), endereco.strip()]):
                st.warning("Por favor, preencha todos os campos obrigatórios: Número da Unidade e Endereço.")
            else:
                with st.spinner("Cadastrando e verificando..."):
                    id_imovel = gerar_id_imovel(grupo_final, unidade_final)
                    imoveis_data_check = imoveis_ws.get_all_values()
                    if len(imoveis_data_check) > 1:
                        df_imoveis