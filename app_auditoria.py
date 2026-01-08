import streamlit as st
import pandas as pd
import backend_fiscal as motor

# --- 1. CONFIGURAÇÃO (WIDE LAYOUT) ---
st.set_page_config(page_title="Auditor Fiscal - LC 214", page_icon="⚖️", layout="wide")

# --- 2. CSS PARA VISUAL DE SISTEMA (DASHBOARD) ---
st.markdown("""
    <style>
    /* Remove padding excessivo do topo */
    .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    
    /* Estilo dos Cards (Caixas Brancas) */
    .css-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #e0e0e0;
        margin-bottom: 15px;
    }
    
    /* Destaque para Benefício Fiscal */
    .badge-verde {
        background-color: #d4edda; color: #155724; padding: 5px 10px; border-radius: 15px; font-weight: bold; font-size: 12px;
    }
    .badge-cinza {
        background-color: #f8f9fa; color: #6c757d; padding: 5px 10px; border-radius: 15px; font-weight: bold; font-size: 12px;
    }
    </style>
""", unsafe_allow_html=True)

# --- 3. CARREGAMENTO ---
df, df_indop, df_regras = motor.carregar_dados()

if df is None:
    st.error("Base de dados não encontrada.")
    st.stop()

# --- 4. BARRA LATERAL (FILTROS GLOBAIS) ---
with st.sidebar:
    st.header("🎛️ Filtros")
    termo = st.text_input("🔍 Pesquisar:", placeholder="LC, NBS ou Nome...").lower()
    
    # Filtro de Tributação
    lista_trib = df['nome cClassTrib'].unique() if 'nome cClassTrib' in df.columns else []
    filtro_trib = st.multiselect("Filtrar CST:", options=lista_trib)
    
    st.markdown("---")
    st.info("ℹ️ Selecione um item na lista principal para ver os detalhes no painel à direita.")

# Aplicação dos Filtros
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

# --- 5. LAYOUT PRINCIPAL (DIVISÃO DA TELA) ---

# Coluna 1 (Lista) | Coluna 2 (Detalhes)
col_nav, col_painel = st.columns([1.2, 2], gap="medium")

# === COLUNA DA ESQUERDA: LISTA DE NAVEGAÇÃO ===
with col_nav:
    st.subheader(f"📋 Resultados ({len(df_view)})")
    
    # Tabela simplificada para servir de "Menu"
    event = st.dataframe(
        df_view,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        height=650, # Altura fixa para dar sensação de menu lateral
        column_config={
            "Item LC 116": st.column_config.TextColumn("LC", width="small"),
            "NBS": st.column_config.TextColumn("NBS", width="small"),
            "DESCRIÇÃO NBS": st.column_config.TextColumn("Descrição", width="medium"),
            "cClassTrib": st.column_config.TextColumn("CST", width="small"), # Oculta visualmente se quiser
        }
    )

# === COLUNA DA DIREITA: PAINEL DE DETALHES ===
with col_painel:
    # Verifica se tem algo selecionado
    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        row = df_view.iloc[idx]
        
        # Recupera dados auxiliares
        cod_trib = str(int(row['cClassTrib'])) if pd.notnull(row['cClassTrib']) else "0"
        chave_regra = f"{int(cod_trib):06d}"
        
        regra_detalhe = pd.Series()
        if not df_regras.empty and 'CHAVE' in df_regras.columns:
            res = df_regras[df_regras['CHAVE'] == chave_regra]
            if not res.empty: regra_detalhe = res.iloc[0]

        # --- CABEÇALHO DO ITEM (HEADER) ---
        st.markdown(f"""
        <div class="css-card" style="border-left: 5px solid #007bff;">
            <span style="color: #007bff; font-weight: bold; font-size: 14px;">LC {row['Item LC 116']} | NBS {row['NBS']}</span>
            <h2 style="margin: 5px 0 10px 0;">{row['DESCRIÇÃO NBS']}</h2>
            <p style="color: gray; margin: 0;">{row['Descrição Item']}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # --- ÁREA DE CONTEÚDO (ABAS) ---
        aba_dados, aba_calc = st.tabs(["📊 Análise Fiscal", "🧮 Calculadora"])

        # >>> ABA 1: DADOS <<<
        with aba_dados:
            c1, c2 = st.columns(2)
            
            # Coluna Esquerda da Aba: TRIBUTAÇÃO
            with c1:
                st.markdown("### 💰 Tributação")
                with st.container(border=True):
                    # Verifica Benefício
                    red_ibs = float(regra_detalhe.get('Percentual Redução IBS', 0)) if not regra_detalhe.empty else 0
                    
                    if red_ibs > 0:
                        st.markdown('<span class="badge-verde">COM REDUÇÃO</span>', unsafe_allow_html=True)
                        st.markdown(f"**Regra:** {row['nome cClassTrib']}")
                        st.markdown(f"📉 Redução IBS: **{red_ibs}%**")
                        st.markdown(f"📉 Redução CBS: **{regra_detalhe.get('Percentual Redução CBS', 0)}%**")
                    else:
                        st.markdown('<span class="badge-cinza">TRIBUTAÇÃO PADRÃO</span>', unsafe_allow_html=True)
                        st.markdown(f"**Regra:** {row['nome cClassTrib']}")
                        st.caption("Alíquota cheia aplicável.")

            # Coluna Direita da Aba: OPERAÇÃO (IndOp)
            with c2:
                st.markdown("### 📝 Operação (DFe)")
                with st.container(border=True):
                    cod_indop = str(row['INDOP'])
                    st.write(f"**Cód. IndOp:** {cod_indop}")
                    
                    # Busca IndOp
                    if not df_indop.empty:
                        res_ind = df_indop[df_indop['CODIGO'] == cod_indop]
                        if not res_ind.empty:
                            d_ind = res_ind.iloc[0]
                            st.write(f"**Local:** {d_ind.get('LOCAL_OPERACAO', '-')}")
                            if 'LOCAL_DFE' in d_ind:
                                st.error(f"📍 **NFe:** {d_ind['LOCAL_DFE']}")
                        else:
                            st.warning("IndOp não detalhado.")
                    else:
                        st.caption("Sem dados.")

        # >>> ABA 2: CALCULADORA <<<
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
                        res = motor.calcular_tributos(val_sim, ibs_ref, cbs_ref, row['cClassTrib'], df_regras)
                        
                        st.metric("Total Tributos", f"R$ {res['total_tributos']:,.2f}", delta=f"{res['carga_total_perc']:.2f}% Carga Real", delta_color="inverse")
                        
                        k1, k2 = st.columns(2)
                        k1.metric("IBS", f"R$ {res['valor_ibs']:,.2f}")
                        k2.metric("CBS", f"R$ {res['valor_cbs']:,.2f}")
                        
                        if res['reducao_ibs'] > 0:
                            st.success(f"Economia aplicada pela redução de {res['reducao_ibs']}%")
                    else:
                        st.info("Clique em calcular.")

    else:
        # TELA DE "DESCANSO" (QUANDO ABRE O SISTEMA)
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        st.markdown("""
        <div style="text-align: center; color: #6c757d;">
            <h1>👈 Selecione um Serviço</h1>
            <p>Utilize a lista à esquerda para navegar pelos itens da NBS/LC 116.</p>
            <p>Os detalhes, regras tributárias e simulador aparecerão aqui.</p>
        </div>
        """, unsafe_allow_html=True)
