# app.py
import streamlit as st
import streamlit_authenticator as stauth
from copy import deepcopy

from data_access import logger

st.set_page_config(page_title="Login - Controle de Aluguéis", page_icon="🔑", layout="centered")

try:
    # Constrói o dicionário de credenciais manualmente a partir dos Secrets
    credentials = {'usernames': {}}
    for username, user_info in st.secrets['credentials']['usernames'].items():
        credentials['usernames'][username] = {
            'email': user_info['email'],
            'name': user_info['name'],
            'password': user_info['password']
        }

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
    logger.exception("Secrets de autenticação ausentes ou incompletos")
    st.error("A configuração de autenticação (Secrets) não foi encontrada ou está incompleta.")
    st.stop()
except Exception as e:
    logger.exception("Erro inesperado na página de login")
    st.error(f"Ocorreu um erro inesperado: {e}")
    st.stop()