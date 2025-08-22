import streamlit as st
import gspread
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import streamlit_authenticator as stauth
import re

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


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Histórico Financeiro", page_icon="📈", layout="wide")
st.title("📈 Histórico Financeiro")
st.markdown("---")

# --- CONEXÃO COM A PLANILHA (USANDO SECRETS) ---
@st.cache_resource
def get_connection():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return gc.open("Controle de Aluguéis")

sh = get_connection()
financeiro_ws = sh.worksheet("Lancamentos_Financeiros")

# --- FUNÇÃO DE CACHE PARA CARREGAR DADOS ---
@st.cache_data(ttl=600)
def load_data(worksheet_name):
    worksheet = sh.worksheet(worksheet_name)
    data = worksheet.get_all_values()
    if not data or len(data) < 2:
        return pd.DataFrame()
    headers = data[0]
    df = pd.DataFrame(data[1:], columns=headers)
    # Padroniza os tipos de dados
    if 'Valor_Total_Pago' in df.columns:
        df['Valor_Total_Pago'] = pd.to_numeric(df['Valor_Total_Pago'], errors='coerce').fillna(0)
    if 'Data_Pagamento' in df.columns:
        df['Data_Pagamento'] = pd.to_datetime(df['Data_Pagamento'], errors='coerce')
    if 'ID_Contrato' in df.columns:
        df['ID_Contrato'] = df['ID_Contrato'].astype(str)
    if 'ID_Imovel' in df.columns:
        df['ID_Imovel'] = df['ID_Imovel'].astype(str)
    return df

# --- LÓGICA DE CANCELAMENTO ---
def cancelar_lancamento(id_lancamento):
    try:
        cell = financeiro_ws.find(str(id_lancamento))
        financeiro_ws.update_cell(cell.row, 10, "Cancelado")
        st.cache_data.clear()
        st.success(f"Lançamento {id_lancamento} cancelado com sucesso!")
        st.rerun()
    except Exception as e:
        st.error(f"Ocorreu um erro ao cancelar o lançamento: {e}")

# --- CARREGAMENTO DOS DADOS ---
df_financeiro = load_data("Lancamentos_Financeiros")
df_contratos = load_data("Contratos")
df_imoveis = load_data("Imoveis")

# --- EXIBIÇÃO DA PÁGINA ---
if not df_financeiro.empty and not df_contratos.empty and not df_imoveis.empty:
    df_contratos_com_grupo = pd.merge(df_contratos, df_imoveis[['ID_Imovel', 'Grupo']], on='ID_Imovel', how='left')
    st.sidebar.header("Filtros Avançados")
    filtrar_por_data = st.sidebar.checkbox("Filtrar por Período", value=False)
    data_inicial = st.sidebar.date_input("De:", value=datetime.now() - timedelta(days=30), disabled=not filtrar_por_data)
    data_final = st.sidebar.date_input("Até:", value=datetime.now(), disabled=not filtrar_por_data)
    gestores = ["Todos"] + sorted(list(df_contratos_com_grupo['Gestor_Responsavel'].unique()))
    gestor_selecionado = st.sidebar.selectbox("Filtrar por Gestor", gestores)
    grupos = ["Todos"] + sorted(list(df_contratos_com_grupo['Grupo'].dropna().unique()))
    grupo_selecionado = st.sidebar.selectbox("Filtrar por Grupo de Imóvel", grupos)
    df_contratos_filtrado = df_contratos_com_grupo.copy()
    if gestor_selecionado != "Todos":
        df_contratos_filtrado = df_contratos_filtrado[df_contratos_filtrado['Gestor_Responsavel'] == gestor_selecionado]
    if grupo_selecionado != "Todos":
        df_contratos_filtrado = df_contratos_filtrado[df_contratos_filtrado['Grupo'] == grupo_selecionado]
    contratos_options = ["Todos"] + [f"{nome} ({id_contrato})" for nome, id_contrato in zip(df_contratos_filtrado['Nome_Locatario'], df_contratos_filtrado['ID_Contrato'])]
    contrato_selecionado_str = st.sidebar.selectbox("Filtrar por Contrato", contratos_options)
    df_filtrado = df_financeiro.copy()
    if filtrar_por_data and df_filtrado['Data_Pagamento'].notna().any():
        df_filtrado = df_filtrado.dropna(subset=['Data_Pagamento'])
        df_filtrado = df_filtrado[(df_filtrado['Data_Pagamento'].dt.date >= data_inicial) & (df_filtrado['Data_Pagamento'].dt.date <= data_final)]
    ids_contratos_filtrados = df_contratos_filtrado['ID_Contrato'].tolist()
    df_filtrado = df_filtrado[df_filtrado['ID_Contrato'].isin(ids_contratos_filtrados)]
    if contrato_selecionado_str != "Todos":
        id_contrato_selecionado = contrato_selecionado_str.split(" (")[-1][:-1]
        df_filtrado = df_filtrado[df_filtrado['ID_Contrato'] == id_contrato_selecionado]
    lancamentos_validos = df_filtrado[df_filtrado['Status_Lancamento'] == 'Válido']
    total_recebido = lancamentos_validos['Valor_Total_Pago'].sum()
    st.header(f"Resumo dos Filtros Aplicados")
    st.metric("Total Recebido (Válido)", f"R$ {total_recebido:,.2f}")
    st.markdown("---")
    st.subheader(f"Exibindo {len(df_filtrado)} Lançamentos")
    col1, col2, col3, col4, col5, col6 = st.columns([1, 3, 2, 2, 2, 2])
    col1.write("**ID**"); col2.write("**Contrato**"); col3.write("**Referência**"); col4.write("**Data Pgto.**"); col5.write("**Valor Pago**"); col6.write("**Ação**")
    for index, row in df_filtrado.iterrows():
        is_valido = row['Status_Lancamento'] == 'Válido'
        def format_text(text): return f"~{text}~" if not is_valido else str(text)
        data_pgto_str = row['Data_Pagamento'].strftime('%Y-%m-%d') if pd.notna(row['Data_Pagamento']) else 'N/A'
        col1, col2, col3, col4, col5, col6 = st.columns([1, 3, 2, 2, 2, 2])
        col1.write(format_text(row['ID_Lancamento'])); col2.write(format_text(row['ID_Contrato'])); col3.write(format_text(row['Mes_Referencia'])); col4.write(format_text(data_pgto_str)); col5.write(format_text(f"R$ {row['Valor_Total_Pago']:.2f}"))
        with col6:
            if is_valido:
                st.button("Cancelar", key=f"cancel_{row['ID_Lancamento']}", on_click=cancelar_lancamento, args=(row['ID_Lancamento'],))
            else:
                st.error("Cancelado")
else:
    st.warning("Não foi possível carregar os dados. Verifique se as abas 'Lancamentos_Financeiros', 'Contratos' e 'Imoveis' contêm dados além do cabeçalho.")