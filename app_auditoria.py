import streamlit as st
import pandas as pd
import backend_fiscal as motor

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Auditor Fiscal - LC 214", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        .css-card {
            background-color: white; padding: 20px; border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #e0e0e0; margin-bottom: 15px;
        }
        .badge-verde { background-color: #d4edda; color: #155724; padding: 5px 10px; border-radius: 15px; font-weight: bold; font-size: 12px; }
        .badge-cinza { background-color: #f8f9fa; color: #6c757d; padding: 5px 10px; border-radius: 15px; font-weight: bold; font-size: 12px; }
        .badge-cst { background-color: #004085; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 13px; margin-left: 10px; vertical-align: middle; }
        
        /* Estilo para métricas de comparação */
        .metric-box { border: 1px solid #eee; padding: 10px; border-radius: 8px; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# --- CARREGAMENTO ---
df, df_indop, df_regras, df_cnae = motor.carregar_dados()

if df is None:
    st.error("Base de dados não encontrada.")
    st.stop()

st.title("🔎 Auditoria e Consulta Fiscal")

tab_auditoria, tab_cnae = st.tabs(["📊 Auditoria NBS & LC 116", "📋 Consulta CNAE x Serviço"])

# ==========================================================
# ABA 1: AUDITORIA E SIMULADOR
# ==========================================================
with tab_auditoria:
    with st.sidebar:
        st.header("🎛️ Filtros NBS")
        termo = st.text_input("🔍 Pesquisar (NBS/LC):", placeholder="LC, NBS ou Nome...").lower()
        lista_trib = df['nome cClassTrib'].unique() if 'nome cClassTrib' in df.columns else []
        filtro_trib = st.multiselect("Filtrar CST:", options=lista_trib)
    
    # Filtros
    df_view = df.copy()
    if termo:
        mask = (
            df_view['Item LC 116'].astype(str).str.contains(termo, na=False) |
            df_view['NBS'].astype(str).str.lower().str.contains(termo, na=False) |
            df_view['DESCRIÇÃO NBS'].astype(str).str.lower().str.contains(termo, na=False) |
            df_view['Descrição Item'].astype(str).str.lower().str.contains(termo, na=False)
        )
        df_view = df_view[mask]
    if filtro_trib:
        df_view = df_view[df_view['nome cClassTrib'].isin(filtro_trib)]

    col_nav, col_painel = st.columns([1.2, 2], gap="medium")

    # Coluna Esquerda: Lista
    with col_nav:
        st.subheader(f"📋 Resultados ({len(df_view)})")
        event = st.dataframe(
            df_view, use_container_width=True, hide_index=True, selection_mode="single-row", on_select="rerun", height=650,
            column_config={
                "Item LC 116": st.column_config.TextColumn("LC", width="small"),
                "NBS": st.column_config.TextColumn("NBS", width="small"),
                "DESCRIÇÃO NBS": st.column_config.TextColumn("Descrição", width="medium"),
                "cClassTrib": st.column_config.TextColumn("CST", width="small"), 
            }
        )

    # Coluna Direita: Detalhes e Calculadora
    with col_painel:
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            row = df_view.iloc[idx]
            
            cod_trib_raw = int(row['cClassTrib']) if pd.notnull(row['cClassTrib']) else 0
            cst_formatado = f"{cod_trib_raw:06d}"
            
            # Recupera dados da regra para exibir badges
            regra_detalhe = pd.Series()
            if not df_regras.empty and 'CHAVE' in df_regras.columns:
                res = df_regras[df_regras['CHAVE'] == cst_formatado]
                if not res.empty: regra_detalhe = res.iloc[0]

            # HEADER
            st.markdown(f"""
            <div class="css-card" style="border-left: 5px solid #007bff;">
                <div style="margin-bottom: 8px;">
                    <span style="color: #007bff; font-weight: bold; font-size: 14px;">LC {row['Item LC 116']} | NBS {row['NBS']}</span>
                    <span class="badge-cst">CST {cst_formatado}</span>
                </div>
                <h2 style="margin: 5px 0 10px 0; font-size: 22px;">{row['DESCRIÇÃO NBS']}</h2>
                <p style="color: gray; margin: 0;">{row['Descrição Item']}</p>
            </div>
            """, unsafe_allow_html=True)
            
            aba_dados, aba_calc = st.tabs(["📊 Detalhes da Regra", "🧮 Simulador Comparativo"])

            # --- ABA DETALHES ---
            with aba_dados:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("### 💰 Regra Aplicável")
                    with st.container(border=True):
                        red_ibs = float(regra_detalhe.get('Percentual Redução IBS', 0)) if not regra_detalhe.empty else 0
                        if red_ibs > 0:
                            st.markdown('<span class="badge-verde">COM REDUÇÃO</span>', unsafe_allow_html=True)
                            st.write(f"**Benefício:** {row.get('nome cClassTrib', '-')}")
                            st.write(f"📉 Redução IBS: **{red_ibs}%**")
                            st.write(f"📉 Redução CBS: **{regra_detalhe.get('Percentual Redução CBS', 0)}%**")
                        else:
                            st.markdown('<span class="badge-cinza">TRIBUTAÇÃO PADRÃO</span>', unsafe_allow_html=True)
                            st.write("Sem redução de alíquota para este item.")
                with c2:
                    st.markdown("### 📝 Operação")
                    with st.container(border=True):
                        st.write(f"**Cód. IndOp:** {row['INDOP']}")
                        if not df_indop.empty:
                            res_ind = df_indop[df_indop['CODIGO'] == str(row['INDOP'])]
                            if not res_ind.empty:
                                st.write(f"**Local:** {res_ind.iloc[0].get('LOCAL_OPERACAO', '-')}")

            # --- ABA SIMULADOR (AQUI ESTÁ A MÁGICA) ---
            with aba_calc:
                st.subheader("Simulação: Atual vs Reforma Tributária")
                
                with st.container(border=True):
                    # Linha 1: Valor Base
                    val_base = st.number_input("Valor do Serviço (Base de Cálculo) R$", value=10000.0, step=500.0)
                    
                    st.markdown("---")
                    
                    # Linha 2: Colunas de Input Lado a Lado
                    c_atual, c_novo = st.columns(2)
                    
                    with c_atual:
                        st.markdown("#### 1. Sistema Atual")
                        st.caption("Informe as alíquotas que você paga hoje.")
                        aliq_iss = st.number_input("ISS (%)", value=5.0, step=0.1)
                        aliq_pis = st.number_input("PIS (%)", value=0.65, step=0.1)
                        aliq_cofins = st.number_input("COFINS (%)", value=3.0, step=0.1)
                        
                    with c_novo:
                        st.markdown("#### 2. Reforma (IBS/CBS)")
                        st.caption("Alíquotas de referência (o sistema aplicará as reduções automaticamente).")
                        aliq_ibs_ref = st.number_input("IBS Referência (%)", value=17.7, step=0.1)
                        aliq_cbs_ref = st.number_input("CBS Referência (%)", value=8.8, step=0.1)
                    
                    st.markdown("---")
                    
                    # Botão de Calcular
                    if st.button("Calcular Comparativo", type="primary", use_container_width=True):
                        # Chama a nova função do backend
                        res = motor.calcular_comparativo(
                            val_base, aliq_iss, aliq_pis, aliq_cofins, 
                            aliq_ibs_ref, aliq_cbs_ref, 
                            row['cClassTrib'], df_regras
                        )
                        
                        # EXIBIÇÃO DOS RESULTADOS
                        r1, r2, r3 = st.columns([1, 1, 1])
                        
                        # Coluna 1: Resultado Atual
                        with r1:
                            st.markdown("##### 🏛️ Carga Atual")
                            st.metric("Total a Pagar", f"R$ {res['valor_atual']:,.2f}")
                            st.caption(f"Alíquota Efetiva: {res['aliq_total_atual']:.2f}%")
                            
                        # Coluna 2: Resultado Novo
                        with r2:
                            st.markdown("##### 🚀 Reforma (IBS+CBS)")
                            st.metric("Total a Pagar", f"R$ {res['valor_novo']:,.2f}")
                            st.caption(f"Alíquota Efetiva: {res['aliq_total_nova']:.2f}% (Redução aplicada)")
                            
                            # Detalhe das alíquotas novas
                            with st.expander("Ver composição"):
                                st.write(f"IBS Ef.: {res['ibs_efetivo']:.2f}%")
                                st.write(f"CBS Ef.: {res['cbs_efetivo']:.2f}%")
                                if res['reducao_ibs'] > 0:
                                    st.success(f"Benefício: -{res['reducao_ibs']}% Redução")
                        
                        # Coluna 3: Veredito
                        with r3:
                            st.markdown("##### ⚖️ Impacto")
                            dif = res['diferenca']
                            if dif > 0:
                                st.metric("Aumento de Carga", f"R$ {dif:,.2f}", delta="- Aumento", delta_color="inverse")
                            elif dif < 0:
                                st.metric("Economia Estimada", f"R$ {abs(dif):,.2f}", delta="+ Economia")
                            else:
                                st.metric("Sem alteração", "R$ 0,00")

        else:
            st.info("👈 Selecione um serviço na lista para abrir o simulador.")

# ==========================================================
# ABA 2: CONSULTA CNAE
# ==========================================================
with tab_cnae:
    st.header("Vínculo CNAE x Lista de Serviços")
    if not df_cnae.empty:
        termo_cnae = st.text_input("Pesquisar CNAE ou Descrição:", placeholder="Ex: 6920...")
        if termo_cnae:
            resultado = motor.buscar_cnae(df_cnae, termo_cnae)
            if len(resultado) > 0:
                st.dataframe(resultado, use_container_width=True, hide_index=True)
            else:
                st.warning("Nada encontrado.")
    else:
        st.error("Arquivo CNAE não carregado.")
