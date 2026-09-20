import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import plotly.express as px
from auth_utils import page_guard
from data_access import load_data

page_guard()

# --- O CÓDIGO DO SEU DASHBOARD COMEÇA AQUI ---
st.set_page_config(page_title="Visão Geral", page_icon="🏠", layout="wide")

# --- CARREGAMENTO DOS DADOS ---
df_imoveis = load_data("Imoveis")
df_contratos = load_data("Contratos")
df_financeiro = load_data("Lancamentos_Financeiros")

# --- APLICAÇÃO PRINCIPAL ---
st.title("🏠 Visão Geral")
st.markdown("---")

if not df_imoveis.empty and not df_contratos.empty:
    df_contratos_ativos = df_contratos[df_contratos['Status_Contrato'] == 'Ativo'].copy()
    df_financeiro_valido = df_financeiro[df_financeiro['Status_Lancamento'] == 'Válido'].copy()
    hoje = datetime.now()
    mes_ano_atual = hoje.strftime("%m/%Y")

    st.header("Visão Geral do Portfólio")
    imoveis_alugados = len(df_imoveis[df_imoveis["Status"] == "Alugado"])
    total_imoveis = len(df_imoveis)
    taxa_ocupacao = (imoveis_alugados / total_imoveis * 100) if total_imoveis > 0 else 0
    st.subheader("Taxa de Ocupação")
    st.progress(int(taxa_ocupacao))
    st.write(f"**{imoveis_alugados}** de **{total_imoveis}** imóveis estão alugados ({taxa_ocupacao:.1f}%)")

    st.markdown("<br>", unsafe_allow_html=True)
    st.subheader(f"Meta de Recebimento para {hoje.strftime('%B/%Y')}")
    total_esperado = pd.to_numeric(df_contratos_ativos['Valor_Aluguel_Base'], errors='coerce').sum()
    total_realizado = pd.to_numeric(
        df_financeiro_valido[df_financeiro_valido['Mes_Referencia'] == mes_ano_atual]['Valor_Total_Pago'],
        errors='coerce').sum()
    percentual_atingido = (total_realizado / total_esperado * 100) if total_esperado > 0 else 0
    st.progress(int(percentual_atingido))
    texto_html = f"""<p style="font-size: 1.1em;"><strong>Recebido:</strong> R$ {total_realizado:,.2f} de <strong>R$ {total_esperado:,.2f}</strong> ({percentual_atingido:.1f}%)</p>"""
    st.markdown(texto_html, unsafe_allow_html=True)

    st.markdown("---")
    st.header("Painel de Ações Urgentes")
    contratos_ativos_count = len(df_contratos_ativos)
    if imoveis_alugados != contratos_ativos_count:
        st.warning(
            f"""**Atenção: Divergência de dados encontrada!** - **Imóveis marcados como "Alugado":** {imoveis_alugados} - **Contratos com status "Ativo":** {contratos_ativos_count} *É necessário corrigir o status de um imóvel ou contrato para reconciliar os dados.*""")
    st.subheader("⚠️ Aluguéis em Atraso")
    df_contratos_ativos['Dia_Vencimento'] = pd.to_numeric(df_contratos_ativos['Dia_Vencimento'], errors='coerce')
    pagamentos_mes_atual = df_financeiro_valido[df_financeiro_valido['Mes_Referencia'] == mes_ano_atual][
        'ID_Contrato'].tolist()
    contratos_em_atraso = [row for index, row in df_contratos_ativos.iterrows() if
                           hoje.day > row['Dia_Vencimento'] and row['ID_Contrato'] not in pagamentos_mes_atual]
    if contratos_em_atraso:
        st.dataframe(
            pd.DataFrame(contratos_em_atraso)[['ID_Imovel', 'Nome_Locatario', 'Gestor_Responsavel', 'Dia_Vencimento']],
            use_container_width=True)
    else:
        st.success("Nenhum aluguel em atraso! 🎉")
    st.markdown("---")
    st.subheader("🔔 Contratos a Vencer")
    contratos_a_vencer = df_contratos[
        (df_contratos['Data_Fim'] > hoje) & (df_contratos['Data_Fim'] <= (hoje + pd.Timedelta(days=60))) & (
                    df_contratos['Status_Contrato'] == 'Ativo')].copy()
    if not contratos_a_vencer.empty:
        contratos_a_vencer['Dias_Restantes'] = (contratos_a_vencer['Data_Fim'] - hoje).dt.days
        st.dataframe(
            contratos_a_vencer[['ID_Imovel', 'Nome_Locatario', 'Gestor_Responsavel', 'Data_Fim', 'Dias_Restantes']],
            use_container_width=True)
    else:
        st.info("Nenhum contrato vencendo em breve.")
    st.markdown("---")
    st.subheader("🔄 Próximos Reajustes")
    contratos_para_reajuste = []
    for index, row in df_contratos_ativos.iterrows():
        anos_de_contrato = relativedelta(hoje, row['Data_Inicio']).years
        proximo_aniversario = row['Data_Inicio'] + relativedelta(years=anos_de_contrato + 1)
        if hoje < proximo_aniversario <= (hoje + pd.Timedelta(days=30)): contratos_para_reajuste.append(row)
    if contratos_para_reajuste:
        st.dataframe(
            pd.DataFrame(contratos_para_reajuste)[['ID_Imovel', 'Nome_Locatario', 'Gestor_Responsavel', 'Data_Inicio']],
            use_container_width=True)
    else:
        st.info("Nenhum reajuste previsto.")

    st.markdown("---")
    st.header("Análises Gráficas")
    col_graf1, col_graf2 = st.columns(2)
    with col_graf1:
        st.subheader("Ocupação por Grupo")
        df_ocupacao = df_imoveis.groupby(['Grupo', 'Status']).size().unstack(fill_value=0)
        fig_ocupacao = px.bar(df_ocupacao, barmode='stack', title="Alugados vs. Vagos por Grupo",
                              labels={'value': 'Qtd. Imóveis'}, color_discrete_map={'Alugado': 'green', 'Vago': 'red'})
        st.plotly_chart(fig_ocupacao, use_container_width=True)
    with col_graf2:
        st.subheader(f"Financeiro por Grupo ({mes_ano_atual})")
        df_contratos_com_grupo = pd.merge(df_contratos_ativos, df_imoveis[['ID_Imovel', 'Grupo']], on='ID_Imovel',
                                          how='left')
        esperado_por_grupo = df_contratos_com_grupo.groupby('Grupo')['Valor_Aluguel_Base'].sum().reset_index()
        df_financeiro_mes_atual = df_financeiro_valido[df_financeiro_valido['Mes_Referencia'] == mes_ano_atual]
        df_financeiro_com_grupo = pd.merge(df_financeiro_mes_atual, df_contratos_com_grupo[['ID_Contrato', 'Grupo']],
                                           on='ID_Contrato', how='left')
        recebido_por_grupo = df_financeiro_com_grupo.groupby('Grupo')['Valor_Total_Pago'].sum().reset_index()
        df_performance = pd.merge(esperado_por_grupo, recebido_por_grupo, on='Grupo', how='outer').fillna(0)
        df_performance['A Receber'] = df_performance['Valor_Aluguel_Base'] - df_performance['Valor_Total_Pago']
        df_performance.rename(columns={'Valor_Total_Pago': 'Recebido'}, inplace=True)
        df_plot = df_performance.melt(id_vars='Grupo', value_vars=['Recebido', 'A Receber'], var_name='Status',
                                      value_name='Valor')
        fig_performance = px.bar(df_plot, x='Grupo', y='Valor', color='Status', barmode='stack',
                                 title="Recebido vs. A Receber por Grupo", labels={'Valor': 'Valor (R$)'},
                                 color_discrete_map={'Recebido': 'royalblue', 'A Receber': 'lightgrey'})
        st.plotly_chart(fig_performance, use_container_width=True)
    col_graf3, col_graf4 = st.columns(2)
    with col_graf3:
        st.subheader("Receita Mensal (12 Meses)")
        df_receita = df_financeiro_valido[df_financeiro_valido['Data_Pagamento'] > (hoje - pd.DateOffset(months=12))]
        df_receita['AnoMes'] = df_receita['Data_Pagamento'].dt.to_period('M').astype(str)
        receita_mensal = df_receita.groupby('AnoMes')['Valor_Total_Pago'].sum().reset_index().sort_values('AnoMes')
        fig_receita = px.bar(receita_mensal, x='AnoMes', y='Valor_Total_Pago', title='Total Recebido por Mês',
                             labels={'AnoMes': 'Mês', 'Valor_Total_Pago': 'Total (R$)'}, text_auto='.2s')
        st.plotly_chart(fig_receita, use_container_width=True)
    with col_graf4:
        st.subheader("Receita Total por Grupo")
        df_c_c_g = pd.merge(df_contratos, df_imoveis[['ID_Imovel', 'Grupo']], on='ID_Imovel', how='left')
        df_f_c_g = pd.merge(df_financeiro_valido, df_c_c_g[['ID_Contrato', 'Grupo']], on='ID_Contrato', how='left')
        receita_por_grupo = df_f_c_g.groupby('Grupo')['Valor_Total_Pago'].sum().reset_index()
        fig_receita_grupo = px.bar(receita_por_grupo, x='Grupo', y='Valor_Total_Pago',
                                   title="Receita Histórica Total por Grupo",
                                   labels={'Valor_Total_Pago': 'Receita Total (R$)'}, text_auto='.2s')
        st.plotly_chart(fig_receita_grupo, use_container_width=True)
else:
    st.warning("Não foi possível carregar os dados das abas 'Imoveis', 'Contratos' ou 'Lancamentos_Financeiros'.")