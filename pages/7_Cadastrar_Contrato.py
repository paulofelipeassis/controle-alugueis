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
st.set_page_config(page_title="Cadastrar Novo Contrato", page_icon="✍️", layout="wide")
st.title("✍️ Cadastrar Novo Contrato de Locação")
st.markdown("---")


# --- CONEXÃO COM A PLANILHA (USANDO SECRETS) ---
@st.cache_resource
def get_connection():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return gc.open("Controle de Aluguéis")


sh = get_connection()
imoveis_ws = sh.worksheet("Imoveis")
contratos_ws = sh.worksheet("Contratos")
gestores_ws = sh.worksheet("Gestores")


# --- FUNÇÃO DE CACHE PARA CARREGAR DADOS ---
@st.cache_data(ttl=600)
def load_data_from_name(worksheet_name):
    worksheet = sh.worksheet(worksheet_name)
    data = worksheet.get_all_values()
    if len(data) < 2: return pd.DataFrame()
    headers = data[0]
    return pd.DataFrame(data[1:], columns=headers)


df_imoveis = load_data_from_name("Imoveis")
df_gestores = load_data_from_name("Gestores")

# --- PASSO 1: SELEÇÃO DO IMÓVEL COM MENUS DEPENDENTES ---
st.subheader("Passo 1: Selecione um Imóvel Vago")
if not df_imoveis.empty:
    imoveis_vagos = df_imoveis[df_imoveis['Status'] == 'Vago']
    if not imoveis_vagos.empty:
        grupos_vagos = ["Selecione..."] + sorted(list(imoveis_vagos['Grupo'].unique()))
        grupo_selecionado = st.selectbox("Selecione o Grupo", grupos_vagos)
        id_imovel_selecionado = None
        if grupo_selecionado != "Selecione...":
            lista_unidades = imoveis_vagos[imoveis_vagos['Grupo'] == grupo_selecionado]['Unidade'].astype(str).unique()
            unidades_vagas = ["Selecione..."] + sorted(list(lista_unidades))
            unidade_selecionada = st.selectbox("Selecione a Unidade", unidades_vagas)
            if unidade_selecionada != "Selecione...":
                imovel_final = imoveis_vagos[
                    (imoveis_vagos['Grupo'] == grupo_selecionado) & (imoveis_vagos['Unidade'] == unidade_selecionada)]
                id_imovel_selecionado = imovel_final['ID_Imovel'].iloc[0]
                st.success(f"Você selecionou o imóvel: **{id_imovel_selecionado}**")

        if id_imovel_selecionado:
            st.markdown("---")
            st.subheader("Passo 2: Preencha os Dados do Contrato")
            with st.form("form_cadastrar_contrato", clear_on_submit=True):
                opcoes_gestores = list(df_gestores['Nome_Gestor'].unique())
                gestor_selecionado = st.selectbox("Selecione o Gestor Responsável", options=opcoes_gestores)
                col1, col2 = st.columns(2)
                with col1:
                    data_inicio = st.date_input("Data de Início do Contrato")
                    valor_aluguel = st.number_input("Valor do Aluguel (Base)", step=50.0, format="%.2f")
                    tipo_garantia = st.selectbox("Tipo de Garantia", ["Caução", "Fiador", "Seguro-fiança"])
                with col2:
                    data_fim = st.date_input("Data de Fim do Contrato")
                    dia_vencimento = st.number_input("Dia do Vencimento", min_value=1, max_value=31, step=1)
                    valor_garantia = st.number_input("Valor da Garantia (se aplicável)", step=100.0, format="%.2f")
                indice_reajuste = st.selectbox("Índice de Reajuste", ["IGP-M", "IPCA", "Outro"])
                st.subheader("Dados do Locatário")
                nome_locatario = st.text_input("Nome Completo")
                cpf_locatario = st.text_input("CPF")
                tel_locatario = st.text_input("Telefone")
                email_locatario = st.text_input("E-mail")
                obs_contrato = st.text_area("Observações do Contrato")
                submitted = st.form_submit_button("Cadastrar Contrato")
                if submitted:
                    with st.spinner("Processando..."):
                        data_inicio_str_id = data_inicio.strftime('%Y%m%d')
                        id_contrato = f"{id_imovel_selecionado}-{data_inicio_str_id}"
                        nova_linha_contrato = [id_contrato, id_imovel_selecionado, gestor_selecionado, nome_locatario,
                                               cpf_locatario, tel_locatario, email_locatario,
                                               data_inicio.strftime('%Y-%m-%d'), data_fim.strftime('%Y-%m-%d'),
                                               valor_aluguel, dia_vencimento, tipo_garantia, valor_garantia,
                                               indice_reajuste, "Ativo", obs_contrato]
                        contratos_ws.append_row(nova_linha_contrato)

                        # Encontra a célula na coluna A (col=1)
                        cell = imoveis_ws.find(id_imovel_selecionado, in_column=1)
                        # Atualiza a célula na mesma linha, mas na coluna 5 (E)
                        imoveis_ws.update_cell(cell.row, 5, "Alugado")

                        st.cache_data.clear()
                        st.success(f"Contrato '{id_contrato}' criado com sucesso!")
                        st.info("O status do imóvel foi atualizado para 'Alugado'.")
                        st.balloons()
    else:
        st.warning("Nenhum imóvel vago encontrado para criar um novo contrato.")
else:
    st.warning("Não foi possível carregar os dados da aba Imóveis.")