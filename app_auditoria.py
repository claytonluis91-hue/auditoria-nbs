import streamlit as st
import pandas as pd
import backend_fiscal as motor # Importando nosso motor separado!

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Auditor Fiscal - LC 214/2025", page_icon="⚖️", layout="wide")

# Estilo CSS para deixar mais profissional
st.markdown("""
    <style>
    .big-font { font-size:20px !important; font-weight: bold; }
    .metric-box { background-color: #f0f2f6; padding: 10px; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)

# --- CARREGAMENTO ---
df, df_indop = motor.carregar_dados()

if df is None:
    st.error("Erro ao carregar dados. Verifique os arquivos JSON.")
    st.stop()

# --- SIDEBAR (FILTROS) ---
st.sidebar.title("🎛️ Painel de Controle")
st.sidebar.markdown("---")

modo_visualizacao = st.sidebar.radio("Modo de Operação:", ["🔍 Consulta & Auditoria", "🧮 Simulador de Cálculo"])

# --- LÓGICA DE FILTRAGEM (GLOBAL) ---
# Mantemos a busca aqui para usar em ambas as abas se precisar
termo_busca = st.sidebar.text_input("Buscar Item (NBS/Descrição):", placeholder="Ex: Software, 1.01...").lower()

df_view = df.copy()
if termo_busca:
    df_view = df_view[
        df_view['NBS'].astype(str).str.lower().str.contains(termo_busca, na=False) | 
        df_view['DESCRIÇÃO NBS'].str.lower().str.contains(termo_busca, na=False) |
        df_view['Descrição Item'].str.lower().str.contains(termo_busca, na=False)
    ]

# --- ABA 1: CONSULTA & AUDITORIA ---
if modo_visualizacao == "🔍 Consulta & Auditoria":
    st.title("🔍 Auditoria de Classificação Fiscal")
    st.caption("Base: Anexo VIII e VII - Reforma Tributária")
    
    event = st.dataframe(
        df_view,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        height=400,
        column_config={"Item LC 116": st.column_config.TextColumn("LC 116")}
    )

    if len(event.selection.rows) > 0:
        # Recupera dados selecionados
        idx = event.selection.rows[0]
        row = df_view.iloc[idx]
        cod_indop = str(row['INDOP'])
        
        st.markdown("---")
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.info(f"**NBS Selecionada:** {row['NBS']}")
            st.write(f"**Descrição:** {row['DESCRIÇÃO NBS']}")
            st.write(f"**Tributação:** {row['nome cClassTrib']}")
        
        with c2:
            # Busca no IndOp
            detalhe = df_indop[df_indop['CODIGO'] == cod_indop] if not df_indop.empty else pd.DataFrame()
            
            if not detalhe.empty:
                d = detalhe.iloc[0]
                with st.container(border=True):
                    st.markdown(f"### 📖 IndOp: {d['DESCRICAO']}")
                    st.write(f"📍 **Local:** {d['LOCAL_OPERACAO']}")
                    if 'LOCAL_DFE' in d:
                        st.success(f"📄 **Destaque no DFe:** {d['LOCAL_DFE']}")
            else:
                st.warning("Sem detalhes adicionais de IndOp.")

# --- ABA 2: SIMULADOR DE CÁLCULO (NOVA!) ---
elif modo_visualizacao == "🧮 Simulador de Cálculo":
    st.title("🧮 Simulador de Impacto Tributário (IBS/CBS)")
    st.markdown("**Metodologia:** Cálculo baseado na alíquota de referência e regras de redução por `cClassTrib`.")
    
    col_input, col_result = st.columns([1, 1.5])
    
    with col_input:
        st.subheader("1. Parâmetros da Simulação")
        
        # O usuário seleciona um serviço da lista filtrada
        servico_selecionado = st.selectbox(
            "Selecione o Serviço (baseado no filtro lateral):",
            options=df_view['DESCRIÇÃO NBS'].unique(),
            index=0 if len(df_view) > 0 else None
        )
        
        if servico_selecionado:
            # Pega os dados do serviço escolhido
            dados_servico = df_view[df_view['DESCRIÇÃO NBS'] == servico_selecionado].iloc[0]
            st.caption(f"Código Tributação: {dados_servico['cClassTrib']}")
            st.caption(f"Regra: {dados_servico['nome cClassTrib']}")
            
            st.markdown("---")
            val_servico = st.number_input("Valor do Serviço (R$):", min_value=0.0, value=1000.0, step=100.0)
            
            # Alíquotas de Referência (Editáveis, pois a lei define, mas o senado ajusta)
            st.markdown(" **Alíquotas de Referência (%):**")
            c_aliq1, c_aliq2 = st.columns(2)
            ibs_ref = c_aliq1.number_input("IBS (Ref):", value=17.7, step=0.1)
            cbs_ref = c_aliq2.number_input("CBS (Ref):", value=8.8, step=0.1)
            
            calcular = st.button("Calcular Tributos", type="primary", use_container_width=True)

    with col_result:
        st.subheader("2. Resultado da Simulação")
        
        if servico_selecionado and calcular:
            # CHAMA O BACKEND PARA CALCULAR
            resultado = motor.calcular_tributos(
                val_servico, ibs_ref, cbs_ref, dados_servico['cClassTrib']
            )
            
            # Exibe Cards de Resultado
            c_res1, c_res2, c_res3 = st.columns(3)
            c_res1.metric("Valor IBS", f"R$ {resultado['valor_ibs']:,.2f}")
            c_res2.metric("Valor CBS", f"R$ {resultado['valor_cbs']:,.2f}")
            c_res3.metric("Total Tributos", f"R$ {resultado['total_tributos']:,.2f}", delta=f"{resultado['carga_total_perc']:.2f}% Carga")
            
            # Detalhamento Visual
            with st.container(border=True):
                st.markdown(f"**Regime Identificado:** {resultado['regime']}")
                if resultado['reducao_aplicada'] != "0%":
                    st.success(f"✅ Redutor Aplicado: **{resultado['reducao_aplicada']}** de desconto na alíquota.")
                
                st.markdown("---")
                st.write("memória de cálculo:")
                st.code(f"""
Serviço: R$ {val_servico:,.2f}

IBS ({ibs_ref}%) -> Efetivo: {resultado['ibs_efetivo']:.2f}% = R$ {resultado['valor_ibs']:,.2f}
CBS ({cbs_ref}%)  -> Efetivo: {resultado['cbs_efetivo']:.2f}% = R$ {resultado['valor_cbs']:,.2f}

Total a Recolher: R$ {resultado['total_tributos']:,.2f}
                """)
        
        elif not servico_selecionado:
            st.info("Utilize os filtros na barra lateral para encontrar o serviço desejado.")
        else:
            st.write("Clique em 'Calcular' para ver os resultados.")