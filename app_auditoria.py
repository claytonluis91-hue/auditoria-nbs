import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditor Fiscal - Consulta Avançada",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# --- 2. CARREGAMENTO DE DADOS ---
@st.cache_data
def carregar_dados():
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    
    path_main = os.path.join(pasta_atual, "AnexoVIII_Convertido.json")
    path_indop = os.path.join(pasta_atual, "IndOp_Descricoes.json")
    
    if not os.path.exists(path_main):
        st.error("❌ ERRO CRÍTICO: Arquivo 'AnexoVIII_Convertido.json' não encontrado.")
        return None, None
        
    df_main = pd.read_json(path_main, dtype={'INDOP': str})
    
    if os.path.exists(path_indop):
        df_indop = pd.read_json(path_indop, dtype={'CODIGO': str})
    else:
        df_indop = pd.DataFrame()
        
    return df_main, df_indop

df, df_indop = carregar_dados()

if df is None:
    st.stop()

# --- 3. FILTROS ---
st.sidebar.header("🔍 Filtros de Auditoria")
termo_busca = st.sidebar.text_input("Buscar (Código, Descrição, LC 116):").lower()

opcoes_trib = df['nome cClassTrib'].unique() if 'nome cClassTrib' in df.columns else []
filtro_trib = st.sidebar.multiselect("Situação Tributária:", options=opcoes_trib)

# --- 4. FILTRAGEM ---
df_view = df.copy()

if termo_busca:
    df_view = df_view[
        df_view['NBS'].astype(str).str.lower().str.contains(termo_busca, na=False) | 
        df_view['DESCRIÇÃO NBS'].str.lower().str.contains(termo_busca, na=False) |
        df_view['Descrição Item'].str.lower().str.contains(termo_busca, na=False)
    ]

if filtro_trib:
    df_view = df_view[df_view['nome cClassTrib'].isin(filtro_trib)]

# --- 5. INTERFACE ---
st.title("🕵️‍♂️ Consultor Fiscal: Reforma Tributária")
col1, col2 = st.columns(2)
col1.metric("Itens Listados", len(df_view))
col2.metric("Total Base", len(df))

st.info("💡 Clique na tabela para ver detalhes da Operação e DFe.")

event = st.dataframe(
    df_view,
    use_container_width=True,
    hide_index=True,
    selection_mode="single-row",
    on_select="rerun",
    column_config={
        "Item LC 116": st.column_config.TextColumn("Item LC"),
        "cClassTrib": st.column_config.TextColumn("Cód. Trib."),
        "INDOP": st.column_config.TextColumn("IndOp"),
    }
)

# --- 6. DETALHES (DRILL-DOWN) ---
if len(event.selection.rows) > 0:
    idx = event.selection.rows[0]
    row = df_view.iloc[idx]
    cod_indop = str(row['INDOP'])

    st.markdown("---")
    st.subheader(f"🔎 Análise: NBS {row['NBS']}")
    
    c1, c2, c3 = st.columns([1, 1.5, 1.5])
    
    with c1:
        st.markdown("### 📦 Serviço")
        st.write(f"**{row['DESCRIÇÃO NBS']}**")
        st.caption(f"LC 116: {row['Item LC 116']}")
        st.info(f"**Trib:** {row['nome cClassTrib']}")

    # Busca IndOp
    detalhe = None
    if not df_indop.empty:
        res = df_indop[df_indop['CODIGO'] == cod_indop]
        if not res.empty:
            detalhe = res.iloc[0]

    with c2:
        st.markdown(f"### 📖 Operação (IndOp {cod_indop})")
        if detalhe is not None:
            with st.container(border=True):
                st.write(f"**{detalhe['DESCRICAO']}**")
                st.markdown(f"**📍 Local:** {detalhe['LOCAL_OPERACAO']}")
                if 'BASE_LEGAL' in detalhe:
                    st.caption(f"⚖️ {detalhe['BASE_LEGAL']}")
        else:
            st.warning("Sem descrição para este IndOp.")

    with c3:
        st.markdown("### 📄 Info. Documento Fiscal")
        if detalhe is not None and 'LOCAL_DFE' in detalhe:
            with st.container(border=True):
                st.success(f"**No DFe:** {detalhe['LOCAL_DFE']}")
                st.caption("Local do fornecimento a ser identificado no documento fiscal.")
        else:
            st.markdown("*Informação não disponível.*")

else:
    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Selecione um item acima.")