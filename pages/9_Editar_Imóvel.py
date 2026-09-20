import streamlit as st
from auth_utils import page_guard
from data_access import load_data_fresh, update_row

page_guard()


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Editar Imóvel", page_icon="🏡", layout="wide")
st.title("🏡 Editar Imóvel")
st.markdown("---")


df_imoveis = load_data_fresh("Imoveis")

# --- PASSO 1: SELECIONAR O IMÓVEL PARA EDITAR ---
st.subheader("Passo 1: Selecione o Imóvel que Deseja Editar")

if not df_imoveis.empty:
    grupos = ["Todos"] + sorted(list(df_imoveis['Grupo'].unique()))
    grupo_selecionado = st.selectbox("Filtrar por Grupo", grupos)

    df_filtrado = df_imoveis.copy()
    if grupo_selecionado != "Todos":
        df_filtrado = df_filtrado[df_filtrado['Grupo'] == grupo_selecionado]

    imoveis_options = ["Selecione..."] + [f"{unidade} ({id_imovel})" for id_imovel, unidade in
                                          zip(df_filtrado['ID_Imovel'], df_filtrado['Unidade'])]
    imovel_selecionado_str = st.selectbox("Imóveis", options=imoveis_options)

    # --- PASSO 2: EXIBIR O FORMULÁRIO PREENCHIDO ---
    if imovel_selecionado_str != "Selecione...":
        id_imovel_selecionado = imovel_selecionado_str.split(" (")[-1][:-1]
        dados_imovel = df_imoveis[df_imoveis['ID_Imovel'] == id_imovel_selecionado].iloc[0]

        st.markdown("---")
        st.subheader("Passo 2: Edite as Informações Abaixo")

        with st.form("form_editar_imovel"):
            st.info(f"Editando o Imóvel: **{dados_imovel['ID_Imovel']}**")
            grupo = st.text_input("Grupo", value=dados_imovel['Grupo'])
            unidade = st.text_input("Unidade", value=dados_imovel['Unidade'])
            endereco = st.text_area("Endereço Completo", value=dados_imovel['Endereco_Completo'])
            status_options = ["Alugado", "Vago", "Em Manutenção", "Outro"]
            if dados_imovel['Status'] not in status_options:
                status_options.append(dados_imovel['Status'])
            status = st.selectbox("Status", options=status_options, index=status_options.index(dados_imovel['Status']))
            st.subheader("Dados Adicionais")
            col1, col2, col3 = st.columns(3)
            with col1:
                iptu_anual = st.number_input("Valor do IPTU Anual",
                                             value=float(dados_imovel.get('Valor_IPTU_Anual', 0)), step=100.0,
                                             format="%.2f")
            with col2:
                medidor_agua = st.text_input("Nº Medidor Saneago", value=dados_imovel.get('Num_Medidor_Saneago', ''))
            with col3:
                medidor_energia = st.text_input("Nº Medidor Enel", value=dados_imovel.get('Num_Medidor_Enel', ''))

            submitted = st.form_submit_button("Salvar Alterações")

            if submitted:
                with st.spinner("Salvando..."):
                    novos_valores = [dados_imovel['ID_Imovel'], grupo, unidade, endereco, status, iptu_anual,
                                     medidor_agua, medidor_energia]
                    try:
                        update_row("Imoveis", id_imovel_selecionado, novos_valores)
                        st.success("Imóvel atualizado com sucesso!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Ocorreu um erro ao salvar o imóvel: {e}")
else:
    st.warning("Nenhum dado de imóvel encontrado na planilha.")