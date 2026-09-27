import streamlit as st
import re
from auth_utils import page_guard
from data_access import load_data_uncached, append_row

page_guard()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Cadastrar Novo Imóvel", page_icon="🏢")
st.title("🏢 Cadastrar Novo Imóvel")
st.markdown("---")


# --- FUNÇÃO PARA GERAR ID DO IMÓVEL ---
def gerar_id_imovel(grupo, unidade):
    prefixo_grupo = re.sub(r'[^A-Z\s]', '', str(grupo).upper()).replace(' ', '')[:4]
    unidade_limpa = re.sub(r'[^0-9A-Z]', '', str(unidade).upper())
    return f"{prefixo_grupo}-{unidade_limpa}"


# --- PASSO 1: SELEÇÃO DO GRUPO (FORA DO FORMULÁRIO) ---
st.subheader("Passo 1: Defina o Grupo do Imóvel")

# Sem cache: precisa sempre da lista de grupos mais atual, sem esperar o TTL.
df_imoveis = load_data_uncached("Imoveis")
if not df_imoveis.empty:
    grupos_existentes = sorted(list(df_imoveis['Grupo'].unique()))
else:
    grupos_existentes = []

opcoes_grupo = grupos_existentes + ["--- Adicionar Novo Grupo ---"]
grupo_selecionado = st.selectbox("Grupo do Imóvel", options=opcoes_grupo, key="grupo_selector")

novo_grupo = ""
if grupo_selecionado == "--- Adicionar Novo Grupo ---":
    novo_grupo = st.text_input("Digite o nome do Novo Grupo", key="novo_grupo_input")

grupo_final = novo_grupo.strip() if grupo_selecionado == "--- Adicionar Novo Grupo ---" else grupo_selecionado

# O formulário só aparece se um grupo válido for definido
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

                    # Recarrega os dados (sem cache) para a verificação de duplicidade
                    df_imoveis_atualizado = load_data_uncached("Imoveis")

                    if not df_imoveis_atualizado.empty and id_imovel in df_imoveis_atualizado['ID_Imovel'].values:
                        st.error(f"Erro: Um imóvel com o ID '{id_imovel}' já existe.")
                    else:
                        nova_linha = [id_imovel, grupo_final, unidade_final, endereco, "Vago", iptu_anual, medidor_agua,
                                      medidor_energia]
                        try:
                            append_row("Imoveis", nova_linha)
                            st.success(
                                f"Imóvel '{unidade_final}' cadastrado com sucesso no grupo '{grupo_final}'! ID gerado: **{id_imovel}**")
                            st.balloons()
                        except Exception as e:
                            st.error(f"Ocorreu um erro ao cadastrar o imóvel: {e}")
else:
    st.info("Selecione um grupo ou adicione um novo para continuar.")