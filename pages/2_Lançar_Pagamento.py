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
st.set_page_config(page_title="Lançar Pagamento", page_icon="💰")
st.title("💰 Lançar Novo Pagamento")
st.markdown("---")


# --- CONEXÃO COM A PLANILHA (USANDO SECRETS) ---
@st.cache_resource
def get_connection():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return gc.open("Controle de Aluguéis")


sh = get_connection()
contratos_ws = sh.worksheet("Contratos")
financeiro_ws = sh.worksheet("Lancamentos_Financeiros")


# --- CARREGAMENTO DOS DADOS ---
@st.cache_data(ttl=600)
def load_contratos():
    data = contratos_ws.get_all_values()
    if len(data) < 2: return pd.DataFrame()
    headers = data[0]
    df = pd.DataFrame(data[1:], columns=headers)
    return df


df_contratos = load_contratos()

# --- FORMULÁRIO DE LANÇAMENTO ---
if not df_contratos.empty:
    contratos_ativos = df_contratos[df_contratos['Status_Contrato'] == 'Ativo']
    opcoes_contratos = ["Selecione um contrato..."] + [f"{nome} (Imóvel {imovel})" for nome, imovel in
                                                       zip(contratos_ativos['Nome_Locatario'],
                                                           contratos_ativos['ID_Imovel'])]

    contrato_selecionado_str = st.selectbox("Para qual contrato você deseja lançar o pagamento?",
                                            options=opcoes_contratos)

    if contrato_selecionado_str != "Selecione um contrato...":
        nome_locatario_selecionado = contrato_selecionado_str.split(" (Imóvel ")[0]

        # Converte a coluna para numérico antes de usar .iloc
        contratos_ativos['Valor_Aluguel_Base'] = pd.to_numeric(contratos_ativos['Valor_Aluguel_Base'],
                                                               errors='coerce').fillna(0)
        dados_contrato = contratos_ativos[contratos_ativos['Nome_Locatario'] == nome_locatario_selecionado].iloc[0]

        id_contrato = dados_contrato['ID_Contrato']
        valor_aluguel_base = dados_contrato['Valor_Aluguel_Base']

        st.info(
            f"Lançando pagamento para o contrato **{id_contrato}** no valor base de **R$ {valor_aluguel_base:,.2f}**.")

        with st.form("form_lancamento_pagamento", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                mes_referencia = st.text_input("Mês de Referência (formato MM/AAAA)",
                                               value=datetime.now().strftime("%m/%Y"))
                data_pagamento = st.date_input("Data do Pagamento", value=datetime.now())
                forma_pagamento = st.selectbox("Forma de Pagamento", ["PIX", "Boleto", "Transferência", "Dinheiro"])
            with col2:
                valor_aluguel_pago = st.number_input("Valor do Aluguel Pago", value=float(valor_aluguel_base),
                                                     step=100.0)
                multa_juros = st.number_input("Multa / Juros Pagos", value=0.0, step=10.0)
                valor_total_pago = valor_aluguel_pago + multa_juros
                st.metric("Valor Total a ser Lançado", f"R$ {valor_total_pago:,.2f}")

            submitted = st.form_submit_button("Lançar Pagamento")

            if submitted:
                with st.spinner("Lançando..."):
                    # Pega todos os valores para determinar o próximo ID de forma segura
                    all_values = financeiro_ws.get_all_values()
                    proximo_id = len(all_values)  # O ID será o número da próxima linha (já que o cabeçalho é a linha 1)

                    data_pagamento_str = data_pagamento.strftime("%Y-%m-%d")

                    nova_linha = [proximo_id, id_contrato, mes_referencia, data_pagamento_str, valor_aluguel_pago,
                                  multa_juros, valor_total_pago, forma_pagamento, "Pago", "Válido"]

                    financeiro_ws.append_row(nova_linha)
                    st.cache_data.clear()  # Limpa o cache para atualizar o dashboard
                    st.success("Pagamento lançado com sucesso na planilha!")
                    st.balloons()
else:
    st.warning("Não foi possível carregar os dados de contratos para iniciar o lançamento.")