import streamlit as st
import pandas as pd
import backend_fiscal as motor

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Auditor Fiscal - LC 214", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
    .stAlert { border-radius: 8px; }
    .metric-container { background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #dee2e6; }
    </style>
""", unsafe_allow_html=True)

# --- CARREGAMENTO DOS DADOS ---
df, df_indop, df_regras = motor.carregar_dados()

if df is None:
    st.error("Erro crítico: Arquivos de dados não encontrados.")
    st.stop()

# --- BARRA LATERAL (CONTROLES) ---
st.sidebar.title("🎛️ Painel de Controle")
modo_operacao = st.sidebar.radio("Modo de Visualização:", ["🔍 Auditoria & Resumo", "🧮 Simulador de Cálculo"])
st.sidebar.markdown("---")

# --- MOTOR DE BUSCA OTIMIZADO (CORRIGIDO) ---
st.sidebar.subheader("🔎 Filtros de Pesquisa")
st.sidebar.info("Dica: Pesquise pelo código exato (ex: 1.05) ou nome.")
termo = st.sidebar.text_input("Palavra-chave ou Código LC:", placeholder="Ex: 1.05, Software...").lower()

# Filtro extra por tributação
lista_tributacao = df['nome cClassTrib'].unique() if 'nome cClassTrib' in df.columns else []
filtro_trib = st.sidebar.multiselect("Filtrar por Tipo de Tributação:", options=lista_tributacao)

# --- LÓGICA DE FILTRAGEM ---
df_view = df.copy()

# 1. Aplica filtro de texto
if termo:
    # AQUI ESTAVA O PROBLEMA: Adicionamos explicitamente a coluna 'Item LC 116' na busca
    mask = (
        df_view['Item LC 116'].astype(str).str.contains(termo, na=False) |  # Busca no Código LC (ex: 1.05)
        df_view['NBS'].astype(str).str.lower().str.contains(termo, na=False) | # Busca na NBS
        df_view['DESCRIÇÃO NBS'].astype(str).str.lower().str.contains(termo, na=False) | # Busca na Descrição NBS
        df_view['Descrição Item'].astype(str).str.lower().str.contains(termo, na=False) | # Busca na Descrição da LC
        df_view['nome cClassTrib'].astype(str).str.lower().str.contains(termo, na=False) # Busca na Tributação
    )
    df_view = df_view[mask]

# 2. Aplica filtro de selectbox (Tributação)
if filtro_trib:
    df_view = df_view[df_view['nome cClassTrib'].isin(filtro_trib)]

# --- ABA 1: AUDITORIA & RESUMO ---
if modo_operacao == "🔍 Auditoria & Resumo":
    st.title("🔍 Auditoria de Classificação Fiscal")
    
    c1, c2 = st.columns(2)
    c1.metric("Itens Encontrados", len(df_view))
    c2.metric("Total na Base", len(df))

    st.info("💡 Clique em uma linha da tabela para ver o Resumo Executivo.")

    # TABELA INTERATIVA
    # Reorganizei as colunas para a LC aparecer primeiro
    event = st.dataframe(
        df_view,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        height=300,
        column_config={
            "Item LC 116": st.column_config.TextColumn("Cód. LC", width="small"),
            "Descrição Item": st.column_config.TextColumn("Descrição LC", width="medium"),
            "NBS": st.column_config.TextColumn("NBS", width="small"),
            "DESCRIÇÃO NBS": st.column_config.TextColumn("Descrição NBS", width="large"),
        }
    )

    # --- O RESUMO EXECUTIVO ---
    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        row = df_view.iloc[idx]
        
        # Prepara chaves de busca
        cod_trib = str(int(row['cClassTrib'])) if pd.notnull(row['cClassTrib']) else "0"
        chave_regra = f"{int(cod_trib):06d}"
        cod_indop = str(row['INDOP'])
        
        # Buscas nos arquivos auxiliares
        regra_detalhe = pd.Series()
        if not df_regras.empty and 'CHAVE' in df_regras.columns:
            res = df_regras[df_regras['CHAVE'] == chave_regra]
            if not res.empty: regra_detalhe = res.iloc[0]

        indop_detalhe = pd.Series()
        if not df_indop.empty:
            res = df_indop[df_indop['CODIGO'] == cod_indop]
            if not res.empty: indop_detalhe = res.iloc[0]

        st.markdown("---")
        st.subheader(f"📑 Resumo: {row['NBS']}")
        
        col_res1, col_res2, col_res3 = st.columns(3)

        # CARD 1: SERVIÇO
        with col_res1:
            with st.container(border=True):
                st.markdown("### 📦 Serviço (LC 116)")
                st.write(f"**Código:** {row['Item LC 116']}")
                st.info(f"{row['Descrição Item']}")
                st.caption(f"NBS: {row['DESCRIÇÃO NBS']}")

        # CARD 2: TRIBUTAÇÃO
        with col_res2:
            with st.container(border=True):
                st.markdown("### 💰 Regra Fiscal")
                red_ibs = float(regra_detalhe.get('Percentual Redução IBS', 0)) if not regra_detalhe.empty else 0
                
                if red_ibs > 0:
                    st.success(f"**COM BENEFÍCIO**")
                    st.write(f"📉 Red. IBS: **{red_ibs}%**")
                    st.write(f"📉 Red. CBS: **{regra_detalhe.get('Percentual Redução CBS', 0)}%**")
                else:
                    st.warning("**TRIBUTAÇÃO PADRÃO**")
                    st.write("Sem redução de alíquota.")
                
                st.caption(f"CST/Regra: {row['nome cClassTrib']}")

        # CARD 3: OPERACIONAL
        with col_res3:
            with st.container(border=True):
                st.markdown("### 📝 DFe (Nota Fiscal)")
                if not indop_detalhe.empty:
                    st.write(f"**IndOp:** {cod_indop}")
                    if 'LOCAL_DFE' in indop_detalhe:
                        st.error(f"📍 **Local:** {indop_detalhe['LOCAL_DFE']}")
                    else:
                        st.write(f"Local: {indop_detalhe.get('LOCAL_OPERACAO', '-')}")
                else:
                    st.markdown("Sem dados IndOp.")

# --- ABA 2: SIMULADOR ---
elif modo_operacao == "🧮 Simulador de Cálculo":
    st.title("🧮 Simulador Financeiro (LC 214)")
    
    col_input, col_result = st.columns([1, 1.5])
    
    with col_input:
        st.subheader("Parâmetros")
        
        # Selectbox melhorado: Mostra LC + NBS
        opcoes_servicos = df_view.apply(lambda x: f"LC {x['Item LC 116']} | NBS {x['NBS']} - {x['DESCRIÇÃO NBS'][:40]}...", axis=1)
        
        escolha = st.selectbox("Selecione o Serviço (da lista filtrada):", options=opcoes_servicos, index=0 if len(df_view)>0 else None)
        
        if escolha:
            # Recupera NBS da string para achar a linha original
            try:
                # Extrai a parte da NBS da string "LC 1.01 | NBS 1.1501... - Descrição"
                # Estratégia: Split por '| NBS ' e pegar o começo da segunda parte
                nbs_part = escolha.split("| NBS ")[1].split(" - ")[0].strip()
                item = df_view[df_view['NBS'].astype(str) == nbs_part].iloc[0]
                
                val = st.number_input("Valor Serviço (R$):", value=1000.0, step=100.0)
                
                c1, c2 = st.columns(2)
                ibs_ref = c1.number_input("IBS Ref (%):", value=17.7)
                cbs_ref = c2.number_input("CBS Ref (%):", value=8.8)
                
                calcular = st.button("Calcular Tributos", type="primary", use_container_width=True)
            except:
                st.warning("Erro ao selecionar item. Tente mudar o filtro.")
                calcular = False

    with col_result:
        if escolha and calcular:
            res = motor.calcular_tributos(val, ibs_ref, cbs_ref, item['cClassTrib'], df_regras)
            
            st.subheader("Previsão de Impostos")
            k1, k2, k3 = st.columns(3)
            k1.metric("IBS", f"R$ {res['valor_ibs']:,.2f}", f"{res['ibs_efetivo']:.2f}%")
            k2.metric("CBS", f"R$ {res['valor_cbs']:,.2f}", f"{res['cbs_efetivo']:.2f}%")
            k3.metric("Total", f"R$ {res['total_tributos']:,.2f}", f"{res['carga_total_perc']:.2f}%")
            
            with st.container(border=True):
                st.markdown(f"**Regra:** {res['descricao_regra']}")
