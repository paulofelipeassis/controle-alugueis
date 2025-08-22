import streamlit as st
import gspread
import pandas as pd
from datetime import datetime
import streamlit_authenticator as stauth
import re
from copy import deepcopy
from auth_utils import page_guard

page_guard()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Editar Contrato", page_icon="✏️", layout="wide")
st.title("✏️ Editar Contrato de Locação")
st.markdown("---")

# --- CONEXÃO COM A PLANILHA (USANDO SECRETS) ---
@st.cache_resource
def get_connection():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return gc.open("Controle de Aluguéis")

sh = get_connection()
contratos_ws = sh.worksheet("Contratos")

# --- FUNÇÃO DE CACHE PARA CARREGAR DADOS ---
@st.cache_data(ttl=30)
def load_contratos():
    data = contratos_ws.get_all_values()
    if len(data) < 2: return pd.DataFrame()
    headers = data[0]
    df = pd.DataFrame(data[1:], columns=headers)
    for col in ['Valor_Aluguel_Base', 'Dia_Vencimento', 'Valor_da_Garantia']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    return df

df_contratos_todos = load_contratos()

# --- PASSO 1: SELECIONAR O CONTRATO PARA EDITAR ---
st.subheader("Passo 1: Selecione o Contrato que Deseja Editar")

mostrar_todos = st.checkbox("Mostrar também contratos encerrados/renovados")
if mostrar_todos:
    df_contratos_filtrado = df_contratos_todos
else:
    df_contratos_filtrado = df_contratos_todos[df_contratos_todos['Status_Contrato'] == 'Ativo']

if not df_contratos_filtrado.empty:
    contratos_options = ["Selecione..."] + [f"{nome} ({id_contrato})" for nome, id_contrato in zip(df_contratos_filtrado['Nome_Locatario'], df_contratos_filtrado['ID_Contrato'])]
    contrato_selecionado_str = st.selectbox("Contratos para Edição", options=contratos_options)

    # --- PASSO 2: EXIBIR O FORMULÁRIO PREENCHIDO ---
    if contrato_selecionado_str != "Selecione...":
        id_contrato_selecionado = contrato_selecionado_str.split(" (")[-1][:-1]
        dados_contrato = df_contratos_todos[df_contratos_todos['ID_Contrato'] == id_contrato_selecionado].iloc[0]
        st.markdown("---")
        st.subheader("Passo 2: Edite as Informações Abaixo")
        with st.form("form_editar_contrato"):
            st.info(f"Editando o Contrato: **{dados_contrato['ID_Contrato']}**")
            gestor = st.text_input("Gestor Responsável", value=dados_contrato['Gestor_Responsavel'])
            st.subheader("Dados do Locatário")
            nome = st.text_input("Nome Completo", value=dados_contrato['Nome_Locatario'])
            cpf = st.text_input("CPF", value=dados_contrato['CPF_Locatario'])
            tel = st.text_input("Telefone", value=dados_contrato['Telefone_Locatario'])
            email = st.text_input("E-mail", value=dados_contrato['Email_Locatario'])
            st.subheader("Datas e Valores")
            col1, col2 = st.columns(2)
            with col1:
                data_inicio = st.date_input("Data de Início", value=pd.to_datetime(dados_contrato['Data_Inicio']))
                valor_aluguel = st.number_input("Valor do Aluguel", value=float(dados_contrato['Valor_Aluguel_Base']))
            with col2:
                data_fim = st.date_input("Data de Fim", value=pd.to_datetime(dados_contrato['Data_Fim']))
                dia_vencimento = st.number_input("Dia do Vencimento", value=int(dados_contrato['Dia_Vencimento']))
            st.subheader("Outras Informações")
            status_options = ["Ativo", "Encerrado", "Renovado"]
            if dados_contrato['Status_Contrato'] not in status_options:
                status_options.append(dados_contrato['Status_Contrato'])
            status = st.selectbox("Status do Contrato", options=status_options, index=status_options.index(dados_contrato['Status_Contrato']))
            obs = st.text_area("Observações", value=dados_contrato['Observacoes_do_Contrato'])
            submitted = st.form_submit_button("Salvar Alterações")
            if submitted:
                with st.spinner("Salvando..."):
                    cell = contratos_ws.find(id_contrato_selecionado)
                    novos_valores = [dados_contrato['ID_Contrato'], dados_contrato['ID_Imovel'], gestor, nome, cpf, tel, email, str(data_inicio.date()), str(data_fim.date()), valor_aluguel, dia_vencimento, dados_contrato['Tipo_Garantia'], dados_contrato['Valor_da_Garantia'], dados_contrato['Indice_Reajuste'], status, obs]
                    # O range P cobre 16 colunas, o que pode ser um erro se a sua planilha tiver menos. Verifique a quantidade de colunas.
                    # Vamos assumir 16 colunas (A até P) por enquanto.
                    contratos_ws.update(f'A{cell.row}:P{cell.row}', [novos_valores])
                    st.cache_data.clear()
                    st.success("Contrato atualizado com sucesso!")
                    st.balloons()
else:
    st.info("Nenhum contrato ativo para editar. Marque a caixa acima para ver todos os contratos.")