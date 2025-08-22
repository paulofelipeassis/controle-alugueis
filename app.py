import streamlit as st
import streamlit_authenticator as stauth
from copy import deepcopy

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Login - Controle de Aluguéis", page_icon="🔑", layout="centered")

st.success("VERSÃO CORRIGIDA COM DEEPCOPY - v2") # <--- MARCA DE VERSÃO PARA TESTE

# --- LÓGICA DE LOGIN ---
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

    st.title("Sistema de Controle de Aluguéis")
    st.header("Por favor, faça o login para continuar")
    authenticator.login()

    if st.session_state["authentication_status"]:
        st.switch_page("pages/1_Visão_Geral.py")
    elif st.session_state["authentication_status"] is False:
        st.error('Usuário ou senha incorretos')
    elif st.session_state["authentication_status"] is None:
        st.warning('Por favor, digite seu usuário e senha')

except KeyError:
    st.error("A configuração de autenticação (Secrets) não foi encontrada ou está incompleta.")
    st.stop()
except Exception as e:
    st.error(f"Ocorreu um erro inesperado: {e}")
    st.stop()