import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="Auditor Fiscal - Consulta Avançada", page_icon="🕵️‍♂️", layout="wide")

# --- FUNÇÃO PARA CARREGAR OS DADOS ---
@st.cache_data
def carregar_dados():
    pasta = r"C:\Users\Clayton\Desktop\Auditoria_Fiscal\SERVIÇOS"
    
    # Arquivo Principal (Anexo VIII)
    path_main = os.path.join(pasta, "AnexoVIII_Convertido.json")
    # Arquivo de Detalhes (Anexo VII - IndOp)
    path_indop = os.path.join(pasta, "IndOp_Descricoes.json")
    
    if not os.path.exists(path_main):
        st.error("Arquivo principal não encontrado.")
        return None, None
        
    df_main = pd.read_json(path_main, dtype={'INDOP': str}) # Força INDOP como texto
    
    # Tenta carregar o IndOp
    if os.path.exists(path_indop):
        df_indop = pd.read_json(path_indop, dtype={'CODIGO': str})
    else:
        df_indop = pd.DataFrame() # Cria vazio se não achar
        
    return df_main, df_indop

# Carrega tudo
df, df_indop = carregar_dados()

if df is None:
    st.stop()

# --- BARRA LATERAL (FILTROS) ---
st.sidebar.header("🔍 Filtros")
termo = st.sidebar.text_input("Buscar (NBS, Descrição, LC 116):").lower()
filtro_trib = st.sidebar.multiselect("Situação Tributária:", options=df['nome cClassTrib'].unique())

# --- LÓGICA DE FILTRAGEM ---
df_view = df.copy()

if termo:
    df_view = df_view[
        df_view['NBS'].astype(str).str.lower().str.contains(termo, na=False) | 
        df_view['DESCRIÇÃO NBS'].str.lower().str.contains(termo, na=False) |
        df_view['Descrição Item'].str.lower().str.contains(termo, na=False)
    ]

if filtro_trib:
    df_view = df_view[df_view['nome cClassTrib'].isin(filtro_trib)]

# --- INTERFACE PRINCIPAL ---
st.title("🕵️‍♂️ Consultor Fiscal Inteligente")
st.caption(f"Exibindo {len(df_view)} registros")

# Exibe a tabela com opção de SELEÇÃO
st.info("💡 Dica: Clique em uma linha da tabela para ver os detalhes da Operação (IndOp).")

event = st.dataframe(
    df_view,
    use_container_width=True,
    hide_index=True,
    selection_mode="single-row", # Permite selecionar 1 linha
    on_select="rerun", # Recarrega a página ao clicar
    column_config={
        "Item LC 116": st.column_config.TextColumn("LC 116"),
        "cClassTrib": st.column_config.TextColumn("Cód. Trib."),
    }
)

# --- ÁREA DE DETALHES (APARECE AO CLICAR) ---
if len(event.selection.rows) > 0:
    # Pega o índice da linha selecionada
    indice_selecionado = event.selection.rows[0]
    # Pega os dados daquela linha no dataframe filtrado
    linha_dados = df_view.iloc[indice_selecionado]
    
    # Pega o código INDOP dessa linha
    codigo_indop = str(linha_dados['INDOP'])
    
    st.markdown("---")
    st.subheader(f"🔎 Detalhes da Seleção: NBS {linha_dados['NBS']}")
    
    col_a, col_b = st.columns([1, 2])
    
    with col_a:
        st.write("**Dados do Serviço:**")
        st.success(f"**NBS:** {linha_dados['DESCRIÇÃO NBS']}")
        st.write(f"**Tributação:** {linha_dados['nome cClassTrib']}")
        st.write(f"**INDOP Aplicado:** `{codigo_indop}`")
    
    with col_b:
        st.write("**Explicação da Operação (IndOp):**")
        
        # Cruzamento de dados (PROCV via código)
        if not df_indop.empty:
            info_extra = df_indop[df_indop['CODIGO'] == codigo_indop]
            
            if not info_extra.empty:
                detalhe = info_extra.iloc[0]
                with st.container(border=True):
                    st.markdown(f"### 📌 {detalhe['DESCRICAO']}")
                    st.markdown(f"**Local da Operação:** {detalhe['LOCAL_OPERACAO']}")
                    st.caption(f"Base Legal: {detalhe['BASE_LEGAL']}")
            else:
                st.warning(f"Não encontramos descrição detalhada para o código INDOP {codigo_indop} no arquivo anexo.")
        else:
            st.warning("Arquivo de definições IndOp não carregado.")

else:
    st.markdown("---")
    st.caption("Selecione um item acima para ver a interpretação fiscal detalhada.")