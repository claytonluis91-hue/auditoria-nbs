import streamlit as st
import pandas as pd
import backend_fiscal as motor  # Importando com o alias que você já usava

# --- CONFIGURAÇÃO (WIDE LAYOUT) ---
st.set_page_config(page_title="Auditor Fiscal - LC 214", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        
        /* Estilo dos Cards (Caixas Brancas) */
        .css-card {
            background-color: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border: 1px solid #e0e0e0;
            margin-bottom: 15px;
        }
        
        /* Badges */
        .badge-verde { background-color: #d4edda; color: #155724; padding: 5px 10px; border-radius: 15px; font-weight: bold; font-size: 12px; }
        .badge-cinza { background-color: #f8f9fa; color: #6c757d; padding: 5px 10px; border-radius: 15px; font-weight: bold; font-size: 12px; }
        .badge-cst { background-color: #004085; color: white; padding: 4px 10px; border-radius: 6px; font-weight: bold; font-size: 13px; margin-left: 10px; vertical-align: middle; }
    </style>
""", unsafe_allow_html=True)

# --- CARREGAMENTO ---
# Agora carrega 4 variáveis
df, df_indop, df_regras, df_cnae = motor.carregar_dados()

if df is None:
    st.error("Base de dados (AnexoVIII) não encontrada.")
    st.stop()

st.title("🔎 Auditoria e Consulta Fiscal")

# --- CRIAÇÃO DAS ABAS ---
tab_auditoria, tab_cnae = st.tabs(["📊 Auditoria NBS & LC 116", "📋 Consulta CNAE x Serviço"])

# ==========================================================
# ABA 1: O SEU SISTEMA ORIGINAL (RESTAURADO)
# ==========================================================
with tab_auditoria:
    # --- BARRA LATERAL (Apenas visualmente dentro do contexto) ---
    with st.sidebar:
        st.header("🎛️ Filtros NBS")
        termo = st.text_input("🔍 Pesquisar (NBS/LC):", placeholder="LC, NBS ou Nome...").lower()
        
        lista_trib = df['nome cClassTrib'].unique() if 'nome cClassTrib' in df.columns else []
        filtro_trib = st.multiselect("Filtrar CST:", options=lista_trib)
        st.info("ℹ️ Selecione um item na lista para ver detalhes.")

    # --- FILTRAGEM ---
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

    # --- LAYOUT DUAS COLUNAS (Menu Esquerdo | Detalhes Direito) ---
    col_nav, col_painel = st.columns([1.2, 2], gap="medium")

    # Coluna Esquerda: Tabela de Seleção
    with col_nav:
        st.subheader(f"📋 Resultados ({len(df_view)})")
        event = st.dataframe(
            df_view,
            use_container_width=True,
            hide_index=True,
            selection_mode="single-row",
            on_select="rerun",
            height=650,
            column_config={
                "Item LC 116": st.column_config.TextColumn("LC", width="small"),
                "NBS": st.column_config.TextColumn("NBS", width="small"),
                "DESCRIÇÃO NBS": st.column_config.TextColumn("Descrição", width="medium"),
                "cClassTrib": st.column_config.TextColumn("CST", width="small"), 
            }
        )

    # Coluna Direita: Detalhes do Item Selecionado
    with col_painel:
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            row = df_view.iloc[idx]
            
            # Formata CST para buscar a regra
            cod_trib_raw = int(row['cClassTrib']) if pd.notnull(row['cClassTrib']) else 0
            cst_formatado = f"{cod_trib_raw:06d}"
            
            # Busca regra no DF de regras
            regra_detalhe = pd.Series()
            if not df_regras.empty and 'CHAVE' in df_regras.columns:
                res = df_regras[df_regras['CHAVE'] == cst_formatado]
                if not res.empty: regra_detalhe = res.iloc[0]

            # HEADER DO CARD (Com HTML personalizado igual ao seu original)
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
            
            # ABAS INTERNAS (Análise e Calculadora)
            aba_dados, aba_calc = st.tabs(["📊 Análise Fiscal", "🧮 Calculadora"])

            with aba_dados:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("### 💰 Tributação")
                    with st.container(border=True):
                        red_ibs = float(regra_detalhe.get('Percentual Redução IBS', 0)) if not regra_detalhe.empty else 0
                        if red_ibs > 0:
                            st.markdown('<span class="badge-verde">COM REDUÇÃO</span>', unsafe_allow_html=True)
                            st.markdown(f"**Regra:** {row.get('nome cClassTrib', '-')}")
                            st.markdown(f"📉 Redução IBS: **{red_ibs}%**")
                            st.markdown(f"📉 Redução CBS: **{regra_detalhe.get('Percentual Redução CBS', 0)}%**")
                        else:
                            st.markdown('<span class="badge-cinza">TRIBUTAÇÃO PADRÃO</span>', unsafe_allow_html=True)
                            st.markdown(f"**Regra:** {row.get('nome cClassTrib', '-')}")
                
                with c2:
                    st.markdown("### 📝 Operação (DFe)")
                    with st.container(border=True):
                        cod_indop = str(row['INDOP'])
                        st.write(f"**Cód. IndOp:** {cod_indop}")
                        if not df_indop.empty:
                            res_ind = df_indop[df_indop['CODIGO'] == cod_indop]
                            if not res_ind.empty:
                                d_ind = res_ind.iloc[0]
                                st.write(f"**Local:** {d_ind.get('LOCAL_OPERACAO', '-')}")
                                if 'LOCAL_DFE' in d_ind:
                                    st.error(f"📍 **NFe:** {d_ind['LOCAL_DFE']}")

            with aba_calc:
                st.markdown("### Simulador de Custo Tributário")
                with st.container(border=True):
                    col_in, col_out = st.columns([1, 1.5])
                    with col_in:
                        val_sim = st.number_input("Valor Serviço (R$):", value=1000.0, step=100.0)
                        ibs_ref = st.number_input("IBS Ref (%):", value=17.7)
                        cbs_ref = st.number_input("CBS Ref (%):", value=8.8)
                        btn_calc = st.button("Calcular", type="primary", use_container_width=True)
                    
                    with col_out:
                        if btn_calc:
                            res_calc = motor.calcular_tributos(val_sim, ibs_ref, cbs_ref, row['cClassTrib'], df_regras)
                            st.metric("Total Tributos", f"R$ {res_calc['total_tributos']:,.2f}", delta=f"{res_calc['carga_total_perc']:.2f}% Carga Real", delta_color="inverse")
                            k1, k2 = st.columns(2)
                            k1.metric("IBS", f"R$ {res_calc['valor_ibs']:,.2f}")
                            k2.metric("CBS", f"R$ {res_calc['valor_cbs']:,.2f}")
                            if res_calc['reducao_ibs'] > 0:
                                st.success(f"Economia de {res_calc['reducao_ibs']}% aplicada!")
                        else:
                            st.info("Clique em calcular.")
        else:
            st.markdown("<br><br><br>", unsafe_allow_html=True)
            st.markdown("""
            <div style="text-align: center; color: #6c757d;">
                <h1>👈 Selecione um Serviço</h1>
                <p>Navegue pela lista à esquerda para ver os detalhes completos.</p>
            </div>
            """, unsafe_allow_html=True)

# ==========================================================
# ABA 2: NOVA CONSULTA CNAE (SIMPLIFICADA)
# ==========================================================
with tab_cnae:
    st.header("Vínculo CNAE x Lista de Serviços (LC 116)")
    st.markdown("Pesquise qual item da LC 116 se aplica ao seu CNAE.")

    if not df_cnae.empty:
        termo_cnae = st.text_input("Pesquisar CNAE ou Descrição:", placeholder="Ex: 6920 ou Contabilidade")
        
        if termo_cnae:
            resultado = motor.buscar_cnae(df_cnae, termo_cnae)
            qtd = len(resultado)
            
            if qtd > 0:
                st.success(f"{qtd} registro(s) encontrado(s).")
                st.dataframe(
                    resultado,
                    column_config={
                        "cnae": "CNAE",
                        "descricao_cnae": "Descrição CNAE",
                        "item_lista_servico": "Item LC 116",
                        "descricao_item": "Descrição Serviço LC",
                        "observacoes": "Observações"
                    },
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.warning("Nenhum resultado encontrado.")
        else:
            st.info("Digite um código ou nome acima para começar.")
            st.dataframe(df_cnae.head(10), use_container_width=True, hide_index=True)
    else:
        st.error("Arquivo CNAE não carregado.")
