import streamlit as st
from datetime import datetime
from auth_utils import page_guard
from data_access import load_data, append_row, proximo_id_lancamento

page_guard()


# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Lançar Pagamento", page_icon="💰")
st.title("💰 Lançar Novo Pagamento")
st.markdown("---")


# --- CARREGAMENTO DOS DADOS ---
df_contratos = load_data("Contratos")

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
                    try:
                        proximo_id = proximo_id_lancamento()
                        data_pagamento_str = data_pagamento.strftime("%Y-%m-%d")
                        nova_linha = [proximo_id, id_contrato, mes_referencia, data_pagamento_str, valor_aluguel_pago,
                                      multa_juros, valor_total_pago, forma_pagamento, "Pago", "Válido"]
                        append_row("Lancamentos_Financeiros", nova_linha)
                        st.success("Pagamento lançado com sucesso na planilha!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Ocorreu um erro ao lançar o pagamento: {e}")
else:
    st.warning("Não foi possível carregar os dados de contratos para iniciar o lançamento.")