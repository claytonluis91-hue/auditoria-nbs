import streamlit as st
import pandas as pd
import os

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditor Fiscal - Consulta Avançada",
    page_icon="🕵️‍♂️",
    layout="wide"
)

# --- 2. FUNÇÃO DE CARREGAMENTO (Compatível com GitHub/Cloud) ---
@st.cache_data
def carregar_dados():
    # Pega o diretório onde este script (app_auditoria.py) está salvo
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    
    # Monta os caminhos relativos para os arquivos JSON
    path_main = os.path.join(pasta_atual, "AnexoVIII_Convertido.json")
    path_indop = os.path.join(pasta_atual, "IndOp_Descricoes.json")
    
    # Verifica e carrega o arquivo principal
    if not os.path.exists(path_main):
        st.error("❌ ERRO CRÍTICO: Arquivo 'AnexoVIII_Convertido.json' não encontrado.")
        st.info(f"O sistema procurou em: {path_main}")
        st.warning("Certifique-se de que o arquivo .json e este script .py estão na mesma pasta.")
        return None, None
        
    # Lê o principal forçando INDOP como texto para evitar erros de comparação
    df_main = pd.read_json(path_main, dtype={'INDOP': str})
    
    # Tenta carregar o arquivo de detalhes (IndOp)
    if os.path.exists(path_indop):
        df_indop = pd.read_json(path_indop, dtype={'CODIGO': str})
    else:
        df_indop = pd.DataFrame() # Cria tabela vazia se não existir
        
    return df_main, df_indop

# Carrega os dados
df, df_indop = carregar_dados()

# Se falhar o carregamento, para o app aqui
if df is None:
    st.stop()

# --- 3. BARRA LATERAL (FILTROS) ---
st.sidebar.header("🔍 Filtros de Auditoria")

termo_busca = st.sidebar.text_input("Buscar (Código NBS, Descrição, LC 116):").lower()

# Filtro de Tributação (pega valores únicos da coluna)
opcoes_trib = df['nome cClassTrib'].unique() if 'nome cClassTrib' in df.columns else []
filtro_trib = st.sidebar.multiselect("Filtrar por Situação Tributária:", options=opcoes_trib)

# --- 4. LÓGICA DE FILTRAGEM ---
df_view = df.copy()

if termo_busca:
    # Busca textual ampla em várias colunas
    df_view = df_view[
        df_view['NBS'].astype(str).str.lower().str.contains(termo_busca, na=False) | 
        df_view['DESCRIÇÃO NBS'].str.lower().str.contains(termo_busca, na=False) |
        df_view['Descrição Item'].str.lower().str.contains(termo_busca, na=False)
    ]

if filtro_trib:
    df_view = df_view[df_view['nome cClassTrib'].isin(filtro_trib)]

# --- 5. INTERFACE PRINCIPAL ---
st.title("🕵️‍♂️ Consultor Fiscal: Reforma Tributária")
st.markdown("---")

# Métricas rápidas
col1, col2 = st.columns(2)
col1.metric("Itens Encontrados", len(df_view))
col2.metric("Base Total de Itens", len(df))

st.info("💡 **Dica:** Clique em uma linha da tabela abaixo para ver a explicação detalhada da Operação (IndOp).")

# Tabela Interativa
event = st.dataframe(
    df_view,
    use_container_width=True,
    hide_index=True,
    selection_mode="single-row", # Permite selecionar apenas 1 linha
    on_select="rerun", # Recarrega a página ao selecionar
    column_config={
        "Item LC 116": st.column_config.TextColumn("Item LC"),
        "cClassTrib": st.column_config.TextColumn("Cód. Trib."),
        "INDOP": st.column_config.TextColumn("Cód. IndOp"),
    }
)

# --- 6. PAINEL DE DETALHES (DRILL-DOWN) ---
# Se o usuário selecionou alguma linha, mostramos os detalhes
if len(event.selection.rows) > 0:
    indice_selecionado = event.selection.rows[0]
    linha_dados = df_view.iloc[indice_selecionado]
    
    # Captura o código INDOP da linha selecionada
    codigo_indop_selecionado = str(linha_dados['INDOP'])

    st.markdown("---")
    st.subheader(f"🔎 Detalhamento Fiscal: NBS {linha_dados['NBS']}")
    
    col_detalhe_1, col_detalhe_2 = st.columns([1, 2])
    
    with col_detalhe_1:
        st.markdown("### 📦 Dados do Produto/Serviço")
        st.caption("Informações do Anexo VIII")
        st.write(f"**Descrição:** {linha_dados['DESCRIÇÃO NBS']}")
        st.write(f"**Item LC 116:** {linha_dados['Item LC 116']} - {linha_dados['Descrição Item']}")
        
        # Destaque visual para a tributação
        st.info(f"**Tributação:**\n\n{linha_dados['nome cClassTrib']} (Cód: {linha_dados['cClassTrib']})")

    with col_detalhe_2:
        st.markdown(f"### 📖 Regra da Operação (IndOp: {codigo_indop_selecionado})")
        
        # Busca no segundo arquivo JSON (Anexo VII)
        if not df_indop.empty:
            registro_indop = df_indop[df_indop['CODIGO'] == codigo_indop_selecionado]
            
            if not registro_indop.empty:
                detalhe = registro_indop.iloc[0]
                
                with st.container(border=True):
                    st.markdown(f"**Característica:** {detalhe['DESCRICAO']}")
                    st.markdown(f"**📍 Local da Operação:** {detalhe['LOCAL_OPERACAO']}")
                    if 'BASE_LEGAL' in detalhe:
                        st.caption(f"⚖️ Base Legal: {detalhe['BASE_LEGAL']}")
            else:
                st.warning(f"⚠️ Não há descrição detalhada cadastrada para o código IndOp **{codigo_indop_selecionado}** no arquivo auxiliar.")
        else:
            st.error("O arquivo de descrições IndOp não foi carregado corretamente.")

else:
    # Mensagem de rodapé quando nada está selecionado
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.caption("Selecione um registro acima para visualizar o cruzamento de dados.")