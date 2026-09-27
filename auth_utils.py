# auth_utils.py
import streamlit as st
import streamlit_authenticator as stauth

from data_access import logger


def page_guard():
    """
    Função "guardiã" que centraliza toda a lógica de segurança.
    """
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

        # Verifica se o usuário está logado
        if not st.session_state.get("authentication_status"):
            st.warning("Você precisa fazer login para acessar esta página.")
            st.stop()

        # Mostra o nome do usuário e o botão de logout na barra lateral
        st.sidebar.title(f"Bem-vindo, *{st.session_state['name']}* 👋")
        authenticator.logout(location='sidebar')

    except KeyError:
        logger.exception("Secrets de autenticação ausentes ou incompletos")
        st.error(
            "A configuração de autenticação (Secrets) não foi encontrada ou está incompleta. Por favor, faça login novamente.")
        st.stop()
    except Exception as e:
        logger.exception("Erro inesperado durante a autenticação")
        st.error(f"Ocorreu um erro inesperado durante a autenticação: {e}")
        st.stop()