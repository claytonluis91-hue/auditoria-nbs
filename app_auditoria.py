import streamlit as st
import pandas as pd
import backend_fiscal as motor
import re

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
    </style>
""", unsafe_allow_html=True)

# --- CARREGAMENTO ---
df, df_indop, df_regras, df_cnae = motor.carregar_dados()

if df is None:
    st.error("Base de dados não encontrada.")
    st.stop()

st.title("🔎 Auditoria e Consulta Fiscal")

# --- ABAS ---
tab_auditoria, tab_cnae_manual, tab_cnpj = st.tabs([
    "📊 Auditoria NBS & Simulador", 
    "📋 Consulta Manual CNAE",
    "🏢 Consulta por CNPJ"
])

# ==========================================================
# ABA 1: AUDITORIA E SIMULADOR (MANTIDA)
# ==========================================================
with tab_auditoria:
    with st.sidebar:
        st.header("🎛️ Filtros NBS")
        termo = st.text_input("🔍 Pesquisar (NBS/LC):", placeholder="LC, NBS ou Nome...").lower()
        lista_trib = df['nome cClassTrib'].unique() if 'nome cClassTrib' in df.columns else []
        filtro_trib = st.multiselect("Filtrar CST:", options=lista_trib)
    
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

    with col_painel:
        if len(event.selection.rows) > 0:
            idx = event.selection.rows[0]
            row = df_view.iloc[idx]
            cod_trib_raw = int(row['cClassTrib']) if pd.notnull(row['cClassTrib']) else 0
            cst_formatado = f"{cod_trib_raw:06d}"
            
            regra_detalhe = pd.Series()
            if not df_regras.empty and 'CHAVE' in df_regras.columns:
                res = df_regras[df_regras['CHAVE'] == cst_formatado]
                if not res.empty: regra_detalhe = res.iloc[0]

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

            with aba_calc:
                st.subheader("Simulação: Atual vs Reforma Tributária")
                with st.container(border=True):
                    val_base = st.number_input("Valor do Serviço (Base de Cálculo) R$", value=10000.0, step=500.0)
                    st.markdown("---")
                    c_atual, c_novo = st.columns(2)
                    with c_atual:
                        st.markdown("#### 1. Sistema Atual")
                        aliq_iss = st.number_input("ISS (%)", value=5.0, step=0.1)
                        aliq_pis = st.number_input("PIS (%)", value=0.65, step=0.1)
                        aliq_cofins = st.number_input("COFINS (%)", value=3.0, step=0.1)
                    with c_novo:
                        st.markdown("#### 2. Reforma (IBS/CBS)")
                        aliq_ibs_ref = st.number_input("IBS Referência (%)", value=17.7, step=0.1)
                        aliq_cbs_ref = st.number_input("CBS Referência (%)", value=8.8, step=0.1)
                    st.markdown("---")
                    
                    if st.button("Calcular Comparativo", type="primary", use_container_width=True):
                        res = motor.calcular_comparativo(
                            val_base, aliq_iss, aliq_pis, aliq_cofins, 
                            aliq_ibs_ref, aliq_cbs_ref, 
                            row['cClassTrib'], df_regras
                        )
                        r1, r2, r3 = st.columns([1, 1, 1])
                        with r1:
                            st.markdown("##### 🏛️ Carga Atual")
                            st.metric("Total a Pagar", f"R$ {res['valor_atual']:,.2f}")
                            st.caption(f"Alíquota Efetiva: {res['aliq_total_atual']:.2f}%")
                        with r2:
                            st.markdown("##### 🚀 Reforma (IBS+CBS)")
                            st.metric("Total a Pagar", f"R$ {res['valor_novo']:,.2f}")
                            st.caption(f"Alíquota Efetiva: {res['aliq_total_nova']:.2f}%")
                            if res['reducao_ibs'] > 0:
                                st.success(f"Benefício: -{res['reducao_ibs']}% Redução")
                        with r3:
                            st.markdown("##### ⚖️ Impacto")
                            dif = res['diferenca']
                            if dif > 0:
                                st.metric("Aumento", f"R$ {dif:,.2f}", delta="- Aumento", delta_color="inverse")
                            elif dif < 0:
                                st.metric("Economia", f"R$ {abs(dif):,.2f}", delta="+ Economia")
                            else:
                                st.metric("Sem alteração", "R$ 0,00")
        else:
            st.info("👈 Selecione um serviço na lista para abrir o simulador.")

# ==========================================================
# ABA 2: CONSULTA MANUAL (CNAE)
# ==========================================================
with tab_cnae_manual:
    st.header("Consulta Manual: CNAE x Serviços")
    st.markdown("Pesquise manualmente pelo código CNAE ou nome da atividade.")
    if not df_cnae.empty:
        termo_cnae = st.text_input("Pesquisar:", placeholder="Ex: 6920 ou Contabilidade")
        if termo_cnae:
            resultado = motor.buscar_cnae(df_cnae, termo_cnae)
            if len(resultado) > 0:
                st.dataframe(resultado, use_container_width=True, hide_index=True)
            else:
                st.warning("Nada encontrado.")
    else:
        st.error("Arquivo CNAE não carregado.")

# ==========================================================
# ABA 3: CONSULTA POR CNPJ (ATUALIZADA: AGORA MOSTRA NBS/CST)
# ==========================================================
with tab_cnpj:
    st.header("🏢 Consulta Automatizada por CNPJ")
    st.markdown("Digite o CNPJ do cliente para buscar os CNAEs e ver os serviços e NBS compatíveis.")

    col_input, col_btn = st.columns([3, 1])
    with col_input:
        cnpj_digitado = st.text_input("CNPJ (somente números):", max_chars=18, placeholder="00.000.000/0000-00")
    with col_btn:
        st.write("") 
        st.write("") 
        buscar_cnpj = st.button("🔍 Buscar Dados", type="primary")

    if buscar_cnpj and cnpj_digitado:
        with st.spinner("Consultando Receita Federal..."):
            dados_empresa = motor.consultar_cnpj_api(cnpj_digitado)
        
        if "erro" in dados_empresa:
            st.error(dados_empresa["erro"])
        else:
            # SUCESSO NA API
            st.success("Empresa localizada!")
            
            with st.expander("📄 Dados Cadastrais", expanded=True):
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Razão Social:** {dados_empresa.get('razao_social')}")
                c2.write(f"**Fantasia:** {dados_empresa.get('nome_fantasia', '-')}")
                c3.write(f"**UF:** {dados_empresa.get('uf')}")
            
            # --- PROCESSAMENTO DOS CNAES ---
            cnae_principal_cod = dados_empresa.get('cnae_fiscal')
            if not cnae_principal_cod:
                cnae_principal_obj = dados_empresa.get('cnae_fiscal_principal', {})
                if isinstance(cnae_principal_obj, dict):
                    cnae_principal_cod = cnae_principal_obj.get('codigo')

            cnaes_secundarios = dados_empresa.get('cnaes_secundarios', [])
            
            lista_codigos_numericos = []
            if cnae_principal_cod:
                cod_limpo = re.sub(r'\D', '', str(cnae_principal_cod))
                lista_codigos_numericos.append(cod_limpo)
            
            for item in cnaes_secundarios:
                if 'codigo' in item:
                    cod_limpo = re.sub(r'\D', '', str(item['codigo']))
                    lista_codigos_numericos.append(cod_limpo)
            
            st.subheader("🛠️ Serviços Compatíveis (LC 116)")
            st.caption(f"Códigos CNAE encontrados na Receita: {', '.join(lista_codigos_numericos)}")
            
            # 1. BUSCA CNAE -> SERVIÇOS
            if not df_cnae.empty and 'cnae_numeros' in df_cnae.columns:
                resultado_cruzamento = df_cnae[df_cnae['cnae_numeros'].isin(lista_codigos_numericos)]
                
                if not resultado_cruzamento.empty:
                    st.info(f"Foram encontrados **{len(resultado_cruzamento)} serviços** vinculados aos CNAEs.")
                    st.dataframe(
                        resultado_cruzamento,
                        column_config={
                            "cnae": "CNAE",
                            "descricao_cnae": "Atividade CNAE",
                            "item_lista_servico": "Item LC 116",
                            "descricao_item": "Serviço Permitido",
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # 2. BUSCA SERVIÇOS -> NBS & CST (NOVA FUNCIONALIDADE)
                    st.markdown("---")
                    st.subheader("📚 Detalhamento Completo (NBS e CST)")
                    st.markdown("Abaixo estão as opções de NBS e Regras Tributárias compatíveis com os serviços identificados acima.")
                    
                    # Pega a lista única de serviços encontrados (Ex: ['7.02', '17.19'])
                    codigos_servicos_encontrados = resultado_cruzamento['item_lista_servico'].unique()
                    
                    # Filtra a base principal (df) onde o 'Item LC 116' bate com os encontrados
                    # Usamos .astype(str) e .strip() para garantir que espaços não atrapalhem
                    if df is not None and not df.empty:
                        # Limpa espaços em branco para garantir o match
                        servicos_limpos = [str(s).strip() for s in codigos_servicos_encontrados]
                        
                        mask_nbs = df['Item LC 116'].astype(str).str.strip().isin(servicos_limpos)
                        df_nbs_relacionados = df[mask_nbs]
                        
                        if not df_nbs_relacionados.empty:
                            st.dataframe(
                                df_nbs_relacionados,
                                column_config={
                                    "Item LC 116": st.column_config.TextColumn("LC", width="small"),
                                    "NBS": st.column_config.TextColumn("NBS", width="small"),
                                    "DESCRIÇÃO NBS": st.column_config.TextColumn("Descrição Detalhada NBS", width="large"),
                                    "cClassTrib": st.column_config.TextColumn("CST", width="small"), 
                                    "nome cClassTrib": st.column_config.TextColumn("Regra Tributária", width="medium"),
                                },
                                use_container_width=True,
                                hide_index=True
                            )
                        else:
                            st.warning("Não foram encontrados códigos NBS correspondentes na base principal para estes serviços.")
                    else:
                        st.error("Base principal NBS não carregada.")

                else:
                    st.warning("Os CNAEs dessa empresa não possuem serviços correspondentes no seu arquivo 'cnae_lista_servicos.json'.")
            else:
                st.error("Erro no arquivo de dados CNAE local (Coluna numérica não criada).")
                
            with st.expander("Ver dados brutos da API"):
                st.json(dados_empresa)
