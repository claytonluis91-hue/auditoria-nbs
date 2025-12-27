import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditor Fiscal - Consulta NBS",
    page_icon="📊",
    layout="wide"
)

# Título e Subtítulo
st.title("📊 Painel de Correlação: Reforma Tributária (IBS/CBS)")
st.markdown("---")

# --- 2. CARREGAMENTO DOS DADOS ---
@st.cache_data # Isso faz o app ficar rápido, carregando os dados apenas uma vez
def carregar_dados():
    arquivo_json = "AnexoVIII_Convertido.json"
    
    # Verifica se o arquivo existe antes de tentar ler
    if not os.path.exists(arquivo_json):
        return None
    
    # Lê o JSON
    df = pd.read_json(arquivo_json)
    return df

df = carregar_dados()

if df is None:
    st.error("❌ Arquivo 'AnexoVIII_Convertido.json' não encontrado na pasta.")
    st.warning("Certifique-se de que o arquivo JSON gerado no passo anterior está na mesma pasta deste script.")
    st.stop() # Para a execução aqui

# --- 3. BARRA LATERAL (FILTROS) ---
st.sidebar.header("🔍 Filtros de Busca")

# Filtro 1: Busca por Texto (NBS ou Descrição)
termo_busca = st.sidebar.text_input("Buscar por NBS ou Descrição do Item:")

# Filtro 2: Selecionar o Tipo de Tributação (cClassTrib)
# Pegamos os valores únicos da coluna 'nome cClassTrib', ignorando vazios
opcoes_tributacao = df['nome cClassTrib'].dropna().unique()
filtro_tributacao = st.sidebar.multiselect(
    "Filtrar por Situação Tributária:",
    options=opcoes_tributacao
)

# Filtro 3: Filtrar por Item LC 116 (Opcional)
# Convertendo para string para facilitar a busca
itens_lc = df['Item LC 116'].dropna().astype(str).unique()
filtro_lc = st.sidebar.selectbox(
    "Filtrar por Item LC 116 (Opcional):",
    options=["Todos"] + list(itens_lc)
)

# --- 4. LÓGICA DE FILTRAGEM ---
df_filtrado = df.copy()

# Aplica filtro de texto (busca inteligente em duas colunas)
if termo_busca:
    termo = termo_busca.lower()
    # Busca tanto no código NBS quanto na descrição
    df_filtrado = df_filtrado[
        df_filtrado['NBS'].astype(str).str.lower().str.contains(termo, na=False) | 
        df_filtrado['DESCRIÇÃO NBS'].str.lower().str.contains(termo, na=False) |
        df_filtrado['Descrição Item'].str.lower().str.contains(termo, na=False)
    ]

# Aplica filtro de Tributação
if filtro_tributacao:
    df_filtrado = df_filtrado[df_filtrado['nome cClassTrib'].isin(filtro_tributacao)]

# Aplica filtro de LC 116
if filtro_lc != "Todos":
    # Converte coluna para string para comparar com o selectbox
    df_filtrado = df_filtrado[df_filtrado['Item LC 116'].astype(str) == filtro_lc]

# --- 5. EXIBIÇÃO DOS RESULTADOS ---

# Métricas no topo
col1, col2 = st.columns(2)
col1.metric("Registros Encontrados", len(df_filtrado))
col2.metric("Total na Base Original", len(df))

# Abas para visualização
aba1, aba2 = st.tabs(["📋 Tabela Detalhada", "📈 Análise Gráfica"])

with aba1:
    st.write("Visualização dos dados filtrados:")
    # Dataframe interativo do Streamlit
    st.dataframe(
        df_filtrado, 
        use_container_width=True,
        hide_index=True,
        column_config={
            "Item LC 116": st.column_config.NumberColumn("Item LC", format="%.2f"),
            "INDOP": st.column_config.NumberColumn("INDOP", format="%d"),
        }
    )

with aba2:
    if not df_filtrado.empty:
        st.subheader("Distribuição por Situação Tributária")
        # Conta quantos itens existem para cada tipo de tributação
        contagem_trib = df_filtrado['nome cClassTrib'].value_counts()
        st.bar_chart(contagem_trib)
    else:
        st.info("Sem dados para gerar gráficos com os filtros atuais.")

# Rodapé
st.markdown("---")
st.caption("Sistema de Auditoria Fiscal - Desenvolvido em Python com Streamlit")