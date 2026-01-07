import streamlit as st
import pandas as pd
import backend_fiscal as motor

# --- CONFIGURAÇÃO VISUAL ---
st.set_page_config(page_title="Auditor Fiscal - LC 214", page_icon="⚖️", layout="wide")

# CSS para dar um visual de "Sistema Profissional"
st.markdown("""
    <style>
    .stAlert { border-radius: 8px; }
    .metric-container { background-color: #f8f9fa; padding: 10px; border-radius: 8px; border: 1px solid #dee2e6; }
    </style>
""", unsafe_allow_html=True)

# --- CARREGAMENTO DOS DADOS ---
# Usamos o backend que já criamos para trazer as 3 bases
df, df_indop, df_regras = motor.carregar_dados()

if df is None:
    st.error("Erro crítico: Arquivos de dados não encontrados.")
    st.stop()

# --- BARRA LATERAL (CONTROLES) ---
st.sidebar.title("🎛️ Painel de Controle")
modo_operacao = st.sidebar.radio("Modo de Visualização:", ["🔍 Auditoria & Resumo", "🧮 Simulador de Cálculo"])
st.sidebar.markdown("---")

# --- MOTOR DE BUSCA OTIMIZADO ---
st.sidebar.subheader("🔎 Filtros de Pesquisa")
termo = st.sidebar.text_input("Palavra-chave ou Código:", placeholder="Ex: Software, 1.01, Manutenção...").lower()

# Lógica de Filtragem (Corrige o problema da busca falhar)
df_view = df.copy()
if termo:
    # Cria uma máscara que procura em TODAS as colunas relevantes ao mesmo tempo
    # O .fillna('') evita que linhas vazias quebrem a busca
    mask = (
        df_view['NBS'].astype(str).str.lower().str.contains(termo, na=False) | 
        df_view['DESCRIÇÃO NBS'].astype(str).str.lower().str.contains(termo, na=False) |
        df_view['Descrição Item'].astype(str).str.lower().str.contains(termo, na=False) |
        df_view['nome cClassTrib'].astype(str).str.lower().str.contains(termo, na=False)
    )
    df_view = df_view[mask]

# Filtro extra por tributação
lista_tributacao = df['nome cClassTrib'].unique()
filtro_trib = st.sidebar.multiselect("Filtrar por Tipo de Tributação:", options=lista_tributacao)
if filtro_trib:
    df_view = df_view[df_view['nome cClassTrib'].isin(filtro_trib)]

# --- ABA 1: AUDITORIA & RESUMO ---
if modo_operacao == "🔍 Auditoria & Resumo":
    st.title("🔍 Auditoria de Classificação Fiscal")
    
    # Métricas de topo
    c1, c2 = st.columns(2)
    c1.metric("Itens Encontrados", len(df_view))
    c2.metric("Total na Base", len(df))

    st.info("💡 Clique em uma linha da tabela para gerar o **Resumo Executivo** abaixo.")

    # TABELA INTERATIVA
    event = st.dataframe(
        df_view,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row", # Permite selecionar 1 linha
        on_select="rerun", # Atualiza a tela ao clicar
        height=300,
        column_config={
            "Item LC 116": st.column_config.TextColumn("Item LC"),
            "cClassTrib": st.column_config.TextColumn("Cód. Trib."),
            "DESCRIÇÃO NBS": st.column_config.TextColumn("Descrição NBS", width="medium"),
        }
    )

    # --- O RESUMO EXECUTIVO (AQUI ESTÁ A NOVIDADE) ---
    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        row = df_view.iloc[idx]
        
        # Prepara dados para o resumo
        cod_trib = str(int(row['cClassTrib'])) if pd.notnull(row['cClassTrib']) else "0"
        chave_regra = f"{int(cod_trib):06d}" # Formata para 000001
        
        # Busca a regra no arquivo de classificação
        regra_detalhe = pd.Series()
        if not df_regras.empty and 'CHAVE' in df_regras.columns:
            res_regra = df_regras[df_regras['CHAVE'] == chave_regra]
            if not res_regra.empty:
                regra_detalhe = res_regra.iloc[0]

        # Busca IndOp
        cod_indop = str(row['INDOP'])
        indop_detalhe = pd.Series()
        if not df_indop.empty:
            res_indop = df_indop[df_indop['CODIGO'] == cod_indop]
            if not res_indop.empty:
                indop_detalhe = res_indop.iloc[0]

        st.markdown("---")
        st.subheader(f"📑 Resumo Executivo: {row['NBS']}")
        
        # Layout do Resumo em 3 Colunas
        col_res1, col_res2, col_res3 = st.columns(3)

        # COLUNA 1: IDENTIFICAÇÃO
        with col_res1:
            with st.container(border=True):
                st.markdown("### 📦 O Serviço")
                st.write(f"**{row['DESCRIÇÃO NBS']}**")
                st.caption("Classificação na LC 116:")
                st.info(f"{row['Item LC 116']} - {row['Descrição Item']}")

        # COLUNA 2: TRIBUTAÇÃO (INTELIGENTE)
        with col_res2:
            with st.container(border=True):
                st.markdown("### 💰 Tributação")
                
                # Lógica de cor baseada na redução
                red_ibs = float(regra_detalhe.get('Percentual Redução IBS', 0)) if not regra_detalhe.empty else 0
                
                if red_ibs > 0:
                    st.success(f"**COM BENEFÍCIO FISCAL**")
                    st.markdown(f"📉 Redução IBS: **{red_ibs}%**")
                    st.markdown(f"📉 Redução CBS: **{regra_detalhe.get('Percentual Redução CBS', 0)}%**")
                else:
                    st.warning("**TRIBUTAÇÃO PADRÃO**")
                    st.markdown("Sem redução de alíquota identificada.")
                
                st.caption("Regra Aplicada:")
                st.write(f"_{row['nome cClassTrib']}_")

        # COLUNA 3: OPERACIONAL (DFe)
        with col_res3:
            with st.container(border=True):
                st.markdown("### 📝 Emissão (DFe)")
                if not indop_detalhe.empty:
                    st.write(f"**IndOp:** {cod_indop}")
                    st.markdown(f"**Local:** {indop_detalhe.get('LOCAL_OPERACAO', '-')}")
                    
                    if 'LOCAL_DFE' in indop_detalhe:
                        st.error(f"📍 **Destaque na Nota:**\n{indop_detalhe['LOCAL_DFE']}")
                else:
                    st.markdown("Sem dados operacionais específicos.")

# --- ABA 2: SIMULADOR ---
elif modo_operacao == "🧮 Simulador de Cálculo":
    st.title("🧮 Simulador Financeiro (LC 214)")
    
    col_input, col_result = st.columns([1, 1.5])
    
    with col_input:
        st.subheader("Parâmetros")
        # Selectbox inteligente: Mostra NBS + Descrição
        opcoes_servicos = df_view.apply(lambda x: f"{x['NBS']} - {x['DESCRIÇÃO NBS'][:60]}...", axis=1)
        
        escolha = st.selectbox("Selecione o Serviço:", options=opcoes_servicos, index=0 if len(df_view)>0 else None)
        
        if escolha:
            # Recupera a linha original baseada na string escolhida
            nbs_escolhido = escolha.split(" - ")[0]
            item = df_view[df_view['NBS'] == nbs_escolhido].iloc[0]
            
            val = st.number_input("Valor da Prestação (R$):", value=1000.0, step=100.0)
            
            st.markdown("**Alíquotas de Referência (%):**")
            c_aliq1, c_aliq2 = st.columns(2)
            ibs_ref = c_aliq1.number_input("IBS:", value=17.7)
            cbs_ref = c_aliq2.number_input("CBS:", value=8.8)
            
            calcular = st.button("Simular Impacto", type="primary", use_container_width=True)

    with col_result:
        if escolha and calcular:
            st.subheader("Resultado da Simulação")
            
            # Chama o Backend
            res = motor.calcular_tributos(val, ibs_ref, cbs_ref, item['cClassTrib'], df_regras)
            
            # Cards de Resultado
            k1, k2, k3 = st.columns(3)
            k1.metric("IBS Devido", f"R$ {res['valor_ibs']:,.2f}", f"{res['ibs_efetivo']:.2f}% Ef.")
            k2.metric("CBS Devido", f"R$ {res['valor_cbs']:,.2f}", f"{res['cbs_efetivo']:.2f}% Ef.")
            k3.metric("Carga Total", f"R$ {res['total_tributos']:,.2f}", f"{res['carga_total_perc']:.2f}%")
            
            # Detalhes da Regra
            with st.container(border=True):
                st.markdown(f"**Regra:** {res['descricao_regra']}")
                if res['reducao_ibs'] > 0:
                     st.success(f"Este cálculo considerou uma redução de **{res['reducao_ibs']}%** na base de cálculo.")
