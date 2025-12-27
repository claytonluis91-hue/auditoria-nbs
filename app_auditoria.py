import streamlit as st
import pandas as pd
import backend_fiscal as motor

st.set_page_config(page_title="Auditor Fiscal - LC 214", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
    .big-font { font-size:20px !important; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- CARREGAMENTO (AGORA COM 3 DATAFRAMES) ---
df, df_indop, df_regras = motor.carregar_dados()

if df is None:
    st.error("Erro crítico: Arquivo principal não encontrado.")
    st.stop()

# --- SIDEBAR ---
st.sidebar.title("🎛️ Painel Fiscal")
st.sidebar.info("Base de Conhecimento Carregada:\n\n✅ Anexo VIII (Serviços)\n✅ Anexo VII (IndOp)\n✅ Classificação Tributária (Regras)")
st.sidebar.markdown("---")

modo = st.sidebar.radio("Modo:", ["🔍 Consulta", "🧮 Simulador Real"])

termo = st.sidebar.text_input("Buscar:", placeholder="Digite NBS ou Descrição...").lower()

# Filtro Global
df_view = df.copy()
if termo:
    df_view = df_view[
        df_view['NBS'].astype(str).str.lower().str.contains(termo, na=False) | 
        df_view['DESCRIÇÃO NBS'].str.lower().str.contains(termo, na=False)
    ]

# --- ABA CONSULTA ---
if modo == "🔍 Consulta":
    st.title("🔍 Auditoria de Classificação")
    
    event = st.dataframe(
        df_view, 
        use_container_width=True, 
        hide_index=True, 
        selection_mode="single-row",
        on_select="rerun",
        column_config={"Item LC 116": st.column_config.TextColumn("LC 116")}
    )

    if len(event.selection.rows) > 0:
        row = df_view.iloc[event.selection.rows[0]]
        st.markdown("---")
        st.info(f"**Item Selecionado:** {row['DESCRIÇÃO NBS']} (NBS: {row['NBS']})")
        
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**Tributação (Anexo VIII):** {row['nome cClassTrib']}")
            st.caption(f"Cód: {row['cClassTrib']}")
        
        with c2:
            # Mostra detalhes da Regra se existir no arquivo novo
            chave = f"{int(row['cClassTrib']):06d}" if pd.notnull(row['cClassTrib']) else "000000"
            if not df_regras.empty and 'CHAVE' in df_regras.columns:
                regra = df_regras[df_regras['CHAVE'] == chave]
                if not regra.empty:
                    r = regra.iloc[0]
                    with st.container(border=True):
                        st.markdown(f"**Regra Aplicável:** {r['Descrição da Situação Tributária']}")
                        st.write(f"📉 Redução IBS: **{r['Percentual Redução IBS']}%**")
                        st.write(f"📉 Redução CBS: **{r['Percentual Redução CBS']}%**")
                else:
                    st.warning("Regra não encontrada no arquivo de classificação.")

# --- ABA SIMULADOR ---
elif modo == "🧮 Simulador Real":
    st.title("🧮 Simulador com Regras Reais (LC 214)")
    
    c_input, c_res = st.columns([1, 1.5])
    
    with c_input:
        st.subheader("Parâmetros")
        
        servico = st.selectbox(
            "Serviço:", 
            options=df_view['DESCRIÇÃO NBS'].unique(),
            index=0 if len(df_view) > 0 else None
        )
        
        if servico:
            item = df_view[df_view['DESCRIÇÃO NBS'] == servico].iloc[0]
            st.caption(f"Cód. Tributação: {item['cClassTrib']}")
            
            val = st.number_input("Valor Nota (R$):", value=1000.0, step=100.0)
            
            st.markdown("**Alíquotas Base (%):**")
            col_a, col_b = st.columns(2)
            ibs_base = col_a.number_input("IBS:", value=17.7)
            cbs_base = col_b.number_input("CBS:", value=8.8)
            
            btn_calc = st.button("Calcular", type="primary", use_container_width=True)

    with c_res:
        st.subheader("Resultado")
        if servico and btn_calc:
            # Chama o cálculo passando o arquivo de regras
            res = motor.calcular_tributos(val, ibs_base, cbs_base, item['cClassTrib'], df_regras)
            
            # Cards
            k1, k2, k3 = st.columns(3)
            k1.metric("IBS a Pagar", f"R$ {res['valor_ibs']:,.2f}", f"{res['ibs_efetivo']:.2f}% Ef.")
            k2.metric("CBS a Pagar", f"R$ {res['valor_cbs']:,.2f}", f"{res['cbs_efetivo']:.2f}% Ef.")
            k3.metric("Total", f"R$ {res['total_tributos']:,.2f}", f"{res['carga_total_perc']:.2f}% Carga")
            
            with st.container(border=True):
                st.markdown(f"**Regra Aplicada:** {res['descricao_regra']}")
                
                if res['reducao_ibs'] > 0 or res['reducao_cbs'] > 0:
                    st.success(f"✅ Benefício Identificado: Redução de **{res['reducao_ibs']}%** no IBS e **{res['reducao_cbs']}%** na CBS.")
                else:
                    st.info("ℹ️ Tributação padrão sem reduções identificadas para este código.")