import streamlit as st
import streamlit_authenticator as stauth

st.set_page_config(page_title="Login - Controle de Aluguéis", page_icon="🔑", layout="centered")

try:
    # --- CORREÇÃO ESSENCIAL AQUI ---
    # Copiamos os segredos para um dicionário normal antes de usar
    credentials = dict(st.secrets['credentials'])
    cookie = dict(st.secrets['cookie'])

    authenticator = stauth.Authenticate(
        credentials,
        cookie['name'],
        cookie['key'],
        cookie['expiry_days']
    )

except KeyError:
    st.error("A configuração de autenticação (Secrets) não foi encontrada ou está incompleta. Verifique o 'Manage app'.")
    st.stop()

st.title("Sistema de Controle de Aluguéis")
st.header("Por favor, faça o login para continuar")
authenticator.login()

if st.session_state.get("authentication_status"):
    st.switch_page("pages/1_Visão_Geral.py")
elif st.session_state.get("authentication_status") is False:
    st.error('Usuário ou senha incorretos')
elif st.session_state.get("authentication_status") is None:
    st.warning('Por favor, digite seu usuário e senha')