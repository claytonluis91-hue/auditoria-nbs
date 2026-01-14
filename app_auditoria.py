import streamlit as st
import pandas as pd
import backend_fiscal as motor
import re

# --- CONFIGURAÇÃO ---
st.set_page_config(page_title="Auditor Fiscal - LC 214", page_icon="⚖️", layout="wide")

st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 3rem; }
        .analise-container {
            background-color: #f8f9fa; padding: 20px; border-radius: 12px;
            border: 1px solid #dee2e6; margin-top: 20px;
        }
        .empresa-header {
            background-color: #eef5ff; padding: 15px; border-radius: 10px; border-left: 5px solid #007bff;
            margin-bottom: 20px;
        }
        .badge-verde { background-color: #d4edda; color: #155724; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 14px; }
        .badge-cinza { background-color: #e2e3e5; color: #383d41; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 14px; }
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZAÇÃO ---
if 'empresa_selecionada' not in st.session_state: st.session_state['empresa_selecionada'] = None
if 'filtro_servicos_cnpj' not in st.session_state: st.session_state['filtro_servicos_cnpj'] = None

# --- CARREGAMENTO ---
df, df_indop, df_regras, df_cnae = motor.carregar_dados()

if df is None:
    st.error("Base de dados não encontrada.")
    st.stop()

# --- HEADER DA EMPRESA ---
if st.session_state['empresa_selecionada']:
    emp = st.session_state['empresa_selecionada']
    nome = emp.get('razao_social') or emp.get('nome') or "Empresa"
    doc = emp.get('cnpj') or ""
    
    c_head1, c_head2 = st.columns([4, 1])
    with c_head1:
        st.markdown(f"""
        <div class="empresa-header">
            <h4 style="margin:0">🏢 {nome}</h4>
            <p style="margin:0; color:#555">CNPJ: {doc}</p>
        </div>
        """, unsafe_allow_html=True)
    with c_head2:
        st.write("")
        if st.button("❌ Limpar Empresa", type="secondary", use_container_width=True):
            st.session_state['empresa_selecionada'] = None
            st.session_state['filtro_servicos_cnpj'] = None
            st.rerun()

# --- ABAS ---
tab_auditoria, tab_cnae_manual, tab_cnpj = st.tabs([
    "📊 Auditoria & Simulador", 
    "📋 Consulta Manual CNAE",
    "🏢 Consulta por CNPJ"
])

# ==========================================================
# ABA 1: AUDITORIA VERTICAL
# ==========================================================
with tab_auditoria:
    with st.sidebar:
        st.header("🎛️ Filtros de Auditoria")
        st.divider()
        
        if st.session_state['filtro_servicos_cnpj'] is not None:
            st.success("✅ Filtro por CNPJ Ativo")
            if st.button("Mostrar Todos os Serviços"):
                st.session_state['filtro_servicos_cnpj'] = None
                st.rerun()
        else:
            if st.session_state['empresa_selecionada']:
                if st.button("Filtrar Serviços da Empresa"):
                    st.rerun() 

        st.write("---")
        termo = st.text_input("Pesquisar (Texto):", placeholder="Ex: Construção, 7.02...").lower()
        lista_trib = df['nome cClassTrib'].unique() if 'nome cClassTrib' in df.columns else []
        filtro_trib = st.multiselect("Filtrar por Regra (CST):", options=lista_trib)
        
    df_view = df.copy()
    if st.session_state['filtro_servicos_cnpj'] is not None:
        lista_servicos_cnpj = st.session_state['filtro_servicos_cnpj']
        lista_servicos_clean = [str(s).strip() for s in lista_servicos_cnpj]
        mask_cnpj = df_view['Item LC 116'].astype(str).str.strip().isin(lista_servicos_clean)
        df_view = df_view[mask_cnpj]

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

    st.subheader(f"📋 Lista de Serviços ({len(df_view)})")
    
    event = st.dataframe(
        df_view, 
        use_container_width=True, 
        hide_index=True, 
        selection_mode="single-row", 
        on_select="rerun", 
        height=400,
        column_config={
            "Item LC 116": st.column_config.TextColumn("LC", width="small"),
            "NBS": st.column_config.TextColumn("NBS", width="small"),
            "DESCRIÇÃO NBS": st.column_config.TextColumn("Descrição Detalhada", width="large"),
            "cClassTrib": st.column_config.TextColumn("CST", width="small"),
            "PS ONEROSA? (S/N)": None, "ADQ EXTERIOR? (S/N)": None, "INDOP": None, "nome cClassTrib": None
        }
    )

    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        row = df_view.iloc[idx]
        
        cod_trib_raw = int(row['cClassTrib']) if pd.notnull(row['cClassTrib']) else 0
        cst_formatado = f"{cod_trib_raw:06d}"
        
        regra_detalhe = pd.Series()
        if not df_regras.empty and 'CHAVE' in df_regras.columns:
            res = df_regras[df_regras['CHAVE'] == cst_formatado]
            if not res.empty: regra_detalhe = res.iloc[0]

        with st.container():
            st.markdown("<div class='analise-container'>", unsafe_allow_html=True)
            st.markdown(f"### 🔎 Análise: NBS {row['NBS']} - LC {row['Item LC 116']}")
            st.caption(row['DESCRIÇÃO NBS'])
            
            col_detalhes, col_calc = st.columns([1, 1.2], gap="large")
            
            with col_detalhes:
                st.markdown("#### 📜 Regras Tributárias")
                red_ibs = float(regra_detalhe.get('Percentual Redução IBS', 0)) if not regra_detalhe.empty else 0
                if red_ibs > 0:
                    st.markdown(f'<span class="badge-verde">COM BENEFÍCIO FISCAL</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span class="badge-cinza">TRIBUTAÇÃO PADRÃO</span>', unsafe_allow_html=True)
                
                st.write("") 
                st.markdown(f"""
                | Parâmetro | Valor |
                | :--- | :--- |
                | **CST (Regra)** | `{cst_formatado}` |
                | **Descrição Regra** | {row.get('nome cClassTrib', '-')} |
                | **Redução IBS** | **{red_ibs}%** |
                | **Redução CBS** | **{regra_detalhe.get('Percentual Redução CBS', 0)}%** |
                | **Cód. Local (IndOp)** | `{row['INDOP']}` |
                """)
                if not df_indop.empty:
                    res_ind = df_indop[df_indop['CODIGO'] == str(row['INDOP'])]
                    local_op = res_ind.iloc[0].get('LOCAL_OPERACAO', '-') if not res_ind.empty else "-"
                    st.info(f"📍 **Local Incidência:** {local_op}")

            with col_calc:
                st.markdown("#### 🧮 Simulador de Impacto")
                with st.container(border=True):
                    val_base = st.number_input("Valor do Serviço (R$)", value=10000.0, step=500.0)
                    
                    c1, c2 = st.columns(2)
                    aliq_iss = c1.number_input("ISS Atual (%)", value=5.0)
                    aliq_pis = c1.number_input("PIS Atual (%)", value=0.65)
                    aliq_cof = c1.number_input("COFINS Atual (%)", value=3.0)
                    
                    aliq_ibs_r = c2.number_input("Ref. IBS (%)", value=17.7)
                    aliq_cbs_r = c2.number_input("Ref. CBS (%)", value=8.8)
                    
                    if st.button("Calcular Agora", type="primary", use_container_width=True):
                        res = motor.calcular_comparativo(
                            val_base, aliq_iss, aliq_pis, aliq_cof, 
                            aliq_ibs_r, aliq_cbs_r, 
                            row['cClassTrib'], df_regras
                        )
                        rA, rB = st.columns(2)
                        rA.metric("Hoje (Total)", f"R$ {res['valor_atual']:,.2f}", f"{res['aliq_total_atual']:.2f}%")
                        rB.metric("Reforma (Total)", f"R$ {res['valor_novo']:,.2f}", f"{res['aliq_total_nova']:.2f}%")
                        
                        dif = res['diferenca']
                        if dif > 0: st.error(f"Aumento de: R$ {dif:,.2f}")
                        else: st.success(f"Economia de: R$ {abs(dif):,.2f}")
                            
                        pdf_bytes = motor.gerar_relatorio_pdf(st.session_state['empresa_selecionada'], res, row)
                        st.download_button("📄 Baixar Simulação (PDF)", pdf_bytes, "simulacao_item.pdf", "application/pdf", use_container_width=True)

            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("👆 Selecione um serviço na tabela acima para ver a análise detalhada e o simulador.")

# ==========================================================
# ABA 2: CONSULTA MANUAL
# ==========================================================
with tab_cnae_manual:
    st.header("Consulta Manual: CNAE x Serviços")
    st.markdown("Pesquise manualmente pelo código CNAE ou nome da atividade.")
    if not df_cnae.empty:
        termo_cnae = st.text_input("Pesquisar:", placeholder="Ex: 6920 ou Contabilidade", key="search_manual")
        if termo_cnae:
            resultado = motor.buscar_cnae(df_cnae, termo_cnae)
            if len(resultado) > 0:
                st.dataframe(
                    resultado, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "cnae": "CNAE", "descricao_cnae": "Descrição Atividade",
                        "item_lista_servico": "Cód. Serviço", "descricao_item": "Descrição Serviço LC",
                        "cnae_numeros_raw": None, "cnae_numeros": None
                    }
                )
            else:
                st.warning("Nada encontrado.")
    else:
        st.error("Arquivo CNAE não carregado.")

# ==========================================================
# ABA 3: CONSULTA POR CNPJ
# ==========================================================
with tab_cnpj:
    st.header("🏢 Consulta Automatizada por CNPJ")
    
    col_input, col_btn = st.columns([3, 1])
    with col_input:
        cnpj_digitado = st.text_input("CNPJ (somente números):", max_chars=18, placeholder="00.000.000/0000-00")
    with col_btn:
        st.write("") 
        st.write("") 
        buscar_cnpj = st.button("🔍 Buscar Dados", type="primary")

    if buscar_cnpj and cnpj_digitado:
        with st.spinner("Consultando Bases Públicas..."):
            dados_empresa = motor.consultar_cnpj_api(cnpj_digitado)
        
        if "erro" in dados_empresa:
            st.error(dados_empresa["erro"])
        else:
            st.success(f"Empresa localizada! (Fonte: {dados_empresa.get('fonte_dados', 'API')})")
            st.session_state['empresa_selecionada'] = dados_empresa
            
            # FILTRO AUTOMÁTICO (Unificado)
            lista_codigos_numericos = []
            
            cnae_p = None
            if 'cnae_fiscal' in dados_empresa: cnae_p = dados_empresa['cnae_fiscal']
            elif 'cnae_fiscal_principal' in dados_empresa:
                obj = dados_empresa['cnae_fiscal_principal']
                if isinstance(obj, dict): cnae_p = obj.get('codigo')
            elif 'atividade_principal' in dados_empresa:
                l = dados_empresa['atividade_principal']
                if isinstance(l, list) and len(l)>0: cnae_p = l[0].get('code')
            if cnae_p: lista_codigos_numericos.append(re.sub(r'\D', '', str(cnae_p)))

            cnaes_sec = dados_empresa.get('cnaes_secundarios') or dados_empresa.get('atividades_secundarias') or []
            if isinstance(cnaes_sec, list):
                for i in cnaes_sec:
                    if isinstance(i, dict):
                        c = i.get('codigo') or i.get('cnae_fiscal') or i.get('code')
                        if c: lista_codigos_numericos.append(re.sub(r'\D', '', str(c)))
            
            if lista_codigos_numericos and not df_cnae.empty and 'cnae_numeros' in df_cnae.columns:
                resultado_cruzamento = df_cnae[df_cnae['cnae_numeros'].isin(lista_codigos_numericos)]
                if not resultado_cruzamento.empty:
                    lista_servicos = resultado_cruzamento['item_lista_servico'].unique()
                    st.session_state['filtro_servicos_cnpj'] = lista_servicos
            st.rerun()

if st.session_state['empresa_selecionada']:
    with tab_cnpj:
        dados_empresa = st.session_state['empresa_selecionada']
        lista_codigos_numericos = []
        # (Lógica repetida para visualização estável)
        cnae_p = None
        if 'cnae_fiscal' in dados_empresa: cnae_p = dados_empresa['cnae_fiscal']
        elif 'cnae_fiscal_principal' in dados_empresa:
             obj = dados_empresa['cnae_fiscal_principal']
             if isinstance(obj, dict): cnae_p = obj.get('codigo')
        elif 'atividade_principal' in dados_empresa:
             l = dados_empresa['atividade_principal']
             if isinstance(l, list) and len(l)>0: cnae_p = l[0].get('code')
        if cnae_p: lista_codigos_numericos.append(re.sub(r'\D', '', str(cnae_p)))

        cnaes_sec = dados_empresa.get('cnaes_secundarios') or dados_empresa.get('atividades_secundarias') or []
        if isinstance(cnaes_sec, list):
            for i in cnaes_sec:
                if isinstance(i, dict):
                    c = i.get('codigo') or i.get('cnae_fiscal') or i.get('code')
                    if c: lista_codigos_numericos.append(re.sub(r'\D', '', str(c)))
        
        if lista_codigos_numericos:
            if not df_cnae.empty and 'cnae_numeros' in df_cnae.columns:
                resultado = df_cnae[df_cnae['cnae_numeros'].isin(lista_codigos_numericos)]
                
                if not resultado.empty:
                    st.subheader("🛠️ Serviços Identificados")
                    st.dataframe(resultado, use_container_width=True, hide_index=True, column_config={"cnae": "CNAE", "descricao_cnae": "Descrição Atividade", "item_lista_servico": "LC 116", "descricao_item": "Serviço", "cnae_numeros_raw": None, "cnae_numeros": None})
                    
                    st.markdown("---")
                    st.subheader("📚 Detalhamento NBS & Local")
                    srvs = resultado['item_lista_servico'].unique()
                    df_rel = pd.DataFrame()
                    
                    if df is not None:
                        srvs_clean = [str(s).strip() for s in srvs]
                        mask = df['Item LC 116'].astype(str).str.strip().isin(srvs_clean)
                        df_rel = df[mask].copy()
                        
                        if not df_rel.empty:
                            if not df_indop.empty:
                                df_rel['INDOP'] = df_rel['INDOP'].astype(str)
                                df_indop['CODIGO'] = df_indop['CODIGO'].astype(str)
                                df_rel = df_rel.merge(df_indop[['CODIGO', 'LOCAL_OPERACAO']], left_on='INDOP', right_on='CODIGO', how='left')
                            else:
                                df_rel['LOCAL_OPERACAO'] = "-"

                            st.dataframe(
                                df_rel,
                                column_config={
                                    "Item LC 116": st.column_config.TextColumn("LC", width="small"),
                                    "NBS": st.column_config.TextColumn("NBS", width="small"),
                                    "DESCRIÇÃO NBS": st.column_config.TextColumn("Descrição", width="large"),
                                    "cClassTrib": st.column_config.TextColumn("CST", width="small"), 
                                    "INDOP": st.column_config.TextColumn("Cód. Local", width="small"),
                                    "LOCAL_OPERACAO": st.column_config.TextColumn("Local Incidência", width="medium"),
                                    "CODIGO": None, "nome cClassTrib": None, "PS ONEROSA? (S/N)": None, "ADQ EXTERIOR? (S/N)": None
                                },
                                use_container_width=True, hide_index=True
                            )
                            
                            # --- BOTÕES DE EXPORTAÇÃO (AQUI É A NOVIDADE!) ---
                            st.write("")
                            c_down1, c_down2, c_null = st.columns([1, 1, 3])
                            
                            with c_down1:
                                excel_data = motor.gerar_excel_completo(dados_empresa, df_rel)
                                st.download_button(
                                    label="📥 Baixar Excel Completo",
                                    data=excel_data,
                                    file_name=f"analise_{dados_empresa.get('cnpj')}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    use_container_width=True
                                )
                            
                            with c_down2:
                                pdf_data = motor.gerar_pdf_paisagem(dados_empresa, df_rel)
                                st.download_button(
                                    label="📄 Baixar PDF (Paisagem)",
                                    data=pdf_data,
                                    file_name=f"relatorio_{dados_empresa.get('cnpj')}.pdf",
                                    mime="application/pdf",
                                    use_container_width=True
                                )

                else:
                    st.warning("CNAEs sem correspondência na lista.")
            else:
                st.error("Erro dados CNAE.")
