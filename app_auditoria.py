import streamlit as st
import pandas as pd
import backend_fiscal as motor
import re

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Auditor Fiscal - LC 214", 
    page_icon="⚖️", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- ESTILIZAÇÃO CSS (VISUAL NFE) ---
st.markdown("""
    <style>
        /* Ajuste do topo para não cortar com a barra do Streamlit */
        .block-container { padding-top: 3rem; padding-bottom: 3rem; }
        
        /* CARD PRINCIPAL (Efeito Sombra) */
        .css-card {
            background-color: white; 
            padding: 20px; 
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); 
            border: 1px solid #f0f2f6;
            margin-bottom: 20px;
        }

        /* HEADER DA EMPRESA (Estilo Dashboard Azul) */
        .empresa-header {
            background: linear-gradient(90deg, #0052cc 0%, #007bff 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 25px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.15);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .empresa-header h3 { color: white; margin: 0; font-size: 1.5rem; font-weight: 600; }
        .empresa-header p { color: #e0eeff; margin: 0; font-size: 1rem; }
        
        /* CONTAINER DE ANÁLISE (Onde fica o simulador) */
        .analise-container {
            background-color: #ffffff;
            padding: 25px;
            border-radius: 12px;
            border-left: 6px solid #007bff;
            box-shadow: 0 2px 10px rgba(0,0,0,0.08);
            margin-top: 20px;
        }

        /* BADGES PERSONALIZADOS */
        .badge-verde { 
            background-color: #d1fae5; color: #065f46; 
            padding: 4px 10px; border-radius: 20px; 
            font-weight: 600; font-size: 0.85rem; border: 1px solid #a7f3d0;
        }
        .badge-cinza { 
            background-color: #f3f4f6; color: #374151; 
            padding: 4px 10px; border-radius: 20px; 
            font-weight: 600; font-size: 0.85rem; border: 1px solid #e5e7eb;
        }

        /* AJUSTE DE MÉTRICAS */
        div[data-testid="stMetric"] {
            background-color: #f8f9fa;
            border: 1px solid #e9ecef;
            padding: 15px;
            border-radius: 8px;
        }
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZAÇÃO DO ESTADO ---
if 'empresa_selecionada' not in st.session_state: st.session_state['empresa_selecionada'] = None
if 'filtro_servicos_cnpj' not in st.session_state: st.session_state['filtro_servicos_cnpj'] = None

# --- CARREGAMENTO DOS DADOS ---
df, df_indop, df_regras, df_cnae = motor.carregar_dados()

if df is None:
    st.error("⚠️ Base de dados não encontrada. Verifique os arquivos JSON.")
    st.stop()

# ==========================================================
# SIDEBAR (NAVEGAÇÃO E FILTROS)
# ==========================================================
with st.sidebar:
    # 1. BOTÃO DE VOLTAR AO PORTAL (Seu Menu Externo)
    st.markdown("### 🌐 Navegação")
    # Substitua pelo link real se mudar
    st.link_button("⬅️ Voltar ao Menu Principal", "https://auditoria-fiscal.streamlit.app/", use_container_width=True)
    st.markdown("---")

    # 2. FILTROS DA AUDITORIA
    st.header("🎛️ Filtros Avançados")
    
    # Filtro Dinâmico de CNPJ
    if st.session_state['filtro_servicos_cnpj'] is not None:
        st.success("🏢 Filtro: Empresa Ativa")
        st.caption("Vendo apenas serviços do CNPJ consultado.")
        if st.button("🔄 Limpar Filtro CNPJ", use_container_width=True):
            st.session_state['filtro_servicos_cnpj'] = None
            st.rerun()
    else:
        # Se tem empresa mas não está filtrando, oferece o filtro
        if st.session_state['empresa_selecionada']:
            if st.button("🎯 Filtrar p/ Empresa Selecionada", use_container_width=True):
                st.rerun()

    st.write("") # Espaço
    termo = st.text_input("🔎 Pesquisar Serviço:", placeholder="Ex: Construção, 7.02...").lower()
    
    lista_trib = df['nome cClassTrib'].unique() if 'nome cClassTrib' in df.columns else []
    filtro_trib = st.multiselect("⚖️ Filtrar por Regra (CST):", options=lista_trib)
    
    st.info("💡 Dica: Na aba Auditoria, selecione uma linha da tabela para ver o simulador de cálculo.")

# ==========================================================
# ÁREA PRINCIPAL
# ==========================================================

st.title("⚖️ Auditoria e Consulta Fiscal")
st.markdown("Análise de NBS, CNAE e Impacto da Reforma Tributária (LC 214)")

# --- HEADER DA EMPRESA (LAYOUT NOVO) ---
if st.session_state['empresa_selecionada']:
    emp = st.session_state['empresa_selecionada']
    nome = emp.get('razao_social') or emp.get('nome') or "Empresa Desconhecida"
    doc = emp.get('cnpj') or "CNPJ Não informado"
    
    # HTML Personalizado para o Header
    st.markdown(f"""
    <div class="empresa-header">
        <div>
            <p style="opacity: 0.8; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px;">Cliente em Análise</p>
            <h3>{nome}</h3>
            <p>🆔 {doc}</p>
        </div>
        <div style="text-align: right;">
            <span style="background: rgba(255,255,255,0.2); padding: 5px 10px; border-radius: 5px;">Status: Ativo</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Botão discreto para remover empresa
    col_close = st.columns([6, 1])[1]
    if col_close.button("Fechar Empresa", type="secondary", key="close_company"):
        st.session_state['empresa_selecionada'] = None
        st.session_state['filtro_servicos_cnpj'] = None
        st.rerun()

# --- ABAS DE NAVEGAÇÃO ---
tab_auditoria, tab_cnae_manual, tab_cnpj = st.tabs([
    "📊 Auditoria & Simulador", 
    "📋 Consulta Manual",
    "🏢 Buscar CNPJ"
])

# ==========================================================
# ABA 1: AUDITORIA VERTICAL (DASHBOARD)
# ==========================================================
with tab_auditoria:
    
    df_view = df.copy()
    
    # Lógica de Filtros
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

    # Métrica de Resultados
    st.caption(f"Encontrados: {len(df_view)} serviços correspondentes.")
    
    # Tabela Principal
    event = st.dataframe(
        df_view, 
        use_container_width=True, 
        hide_index=True, 
        selection_mode="single-row", 
        on_select="rerun", 
        height=450,
        column_config={
            "Item LC 116": st.column_config.TextColumn("LC", width="small"),
            "NBS": st.column_config.TextColumn("NBS", width="small"),
            "DESCRIÇÃO NBS": st.column_config.TextColumn("Descrição Detalhada", width="large"),
            "cClassTrib": st.column_config.TextColumn("CST", width="small"),
            "PS ONEROSA? (S/N)": None, "ADQ EXTERIOR? (S/N)": None, "INDOP": None, "nome cClassTrib": None
        }
    )

    # Painel de Detalhes (On Click)
    if len(event.selection.rows) > 0:
        idx = event.selection.rows[0]
        row = df_view.iloc[idx]
        
        cod_trib_raw = int(row['cClassTrib']) if pd.notnull(row['cClassTrib']) else 0
        cst_formatado = f"{cod_trib_raw:06d}"
        
        regra_detalhe = pd.Series()
        if not df_regras.empty and 'CHAVE' in df_regras.columns:
            res = df_regras[df_regras['CHAVE'] == cst_formatado]
            if not res.empty: regra_detalhe = res.iloc[0]

        # ÁREA DE ANÁLISE ESTILIZADA
        st.markdown("<div class='analise-container'>", unsafe_allow_html=True)
        
        # Título do Card
        c_tit, c_bdg = st.columns([3, 1])
        with c_tit:
            st.markdown(f"### 🔎 NBS {row['NBS']} - LC {row['Item LC 116']}")
            st.markdown(f"*{row['DESCRIÇÃO NBS']}*")
        
        st.markdown("---")
        
        col_detalhes, col_calc = st.columns([1, 1.2], gap="large")
        
        # Coluna Esquerda: Dados Fiscais
        with col_detalhes:
            st.subheader("📜 Regras Tributárias")
            
            red_ibs = float(regra_detalhe.get('Percentual Redução IBS', 0)) if not regra_detalhe.empty else 0
            
            # Badge Dinâmico
            if red_ibs > 0:
                st.markdown(f'<span class="badge-verde">✅ COM BENEFÍCIO FISCAL</span>', unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-cinza">ℹ️ TRIBUTAÇÃO PADRÃO</span>', unsafe_allow_html=True)
            
            st.write("")
            
            # Cards de Informação
            st.info(f"**Regra (CST):** {cst_formatado}\n\n{row.get('nome cClassTrib', '-')}")
            
            c_red1, c_red2 = st.columns(2)
            c_red1.metric("Redução IBS", f"{red_ibs}%")
            c_red2.metric("Redução CBS", f"{regra_detalhe.get('Percentual Redução CBS', 0)}%")
            
            if not df_indop.empty:
                res_ind = df_indop[df_indop['CODIGO'] == str(row['INDOP'])]
                local_op = res_ind.iloc[0].get('LOCAL_OPERACAO', '-') if not res_ind.empty else "-"
                st.write(f"📍 **Local Incidência:** {local_op}")

        # Coluna Direita: Calculadora
        with col_calc:
            st.subheader("🧮 Simulador de Impacto")
            
            with st.container(border=True):
                val_base = st.number_input("Valor do Serviço (R$)", value=10000.0, step=500.0)
                
                t1, t2, t3 = st.tabs(["Carga Atual", "Reforma", "Resultado"])
                
                with t1:
                    c1, c2, c3 = st.columns(3)
                    aliq_iss = c1.number_input("ISS (%)", value=5.0)
                    aliq_pis = c2.number_input("PIS (%)", value=0.65)
                    aliq_cof = c3.number_input("COFINS (%)", value=3.0)
                
                with t2:
                    c1, c2 = st.columns(2)
                    aliq_ibs_r = c1.number_input("Ref. IBS (%)", value=17.7)
                    aliq_cbs_r = c2.number_input("Ref. CBS (%)", value=8.8)
                
                with t3:
                    if st.button("Calcular Agora", type="primary", use_container_width=True):
                        res = motor.calcular_comparativo(
                            val_base, aliq_iss, aliq_pis, aliq_cof, 
                            aliq_ibs_r, aliq_cbs_r, 
                            row['cClassTrib'], df_regras
                        )
                        
                        rA, rB = st.columns(2)
                        rA.metric("Carga Atual", f"R$ {res['valor_atual']:,.2f}", delta=f"{res['aliq_total_atual']:.2f}% (Aliq)")
                        rB.metric("Reforma", f"R$ {res['valor_novo']:,.2f}", delta=f"{res['aliq_total_nova']:.2f}% (Aliq)", delta_color="off")
                        
                        dif = res['diferenca']
                        if dif > 0:
                            st.error(f"⚠️ Aumento de Carga: R$ {dif:,.2f}")
                        else:
                            st.success(f"📉 Economia Estimada: R$ {abs(dif):,.2f}")
                        
                        # PDF
                        st.markdown("---")
                        pdf_bytes = motor.gerar_relatorio_pdf(st.session_state['empresa_selecionada'], res, row)
                        st.download_button("📄 Baixar Relatório PDF", pdf_bytes, "simulacao.pdf", "application/pdf", use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

# ==========================================================
# ABA 2: CONSULTA MANUAL
# ==========================================================
with tab_cnae_manual:
    st.markdown("### 📋 Consulta Rápida: CNAE x Serviços")
    st.caption("Pesquise por código CNAE ou descrição da atividade para encontrar os vínculos com a LC 116.")
    
    col_search, col_res = st.columns([1, 2])
    
    if not df_cnae.empty:
        with col_search:
            termo_cnae = st.text_input("Digite o CNAE ou Nome:", placeholder="Ex: 6920...")
        
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
                st.warning("Nenhum CNAE correspondente encontrado.")
    else:
        st.error("Erro: Arquivo de CNAEs não carregado.")

# ==========================================================
# ABA 3: CONSULTA POR CNPJ
# ==========================================================
with tab_cnpj:
    st.markdown("### 🏢 Consulta Inteligente por CNPJ")
    st.caption("Busque os dados na Receita Federal e cruze automaticamente com a lista de serviços.")

    with st.container(border=True):
        c_input, c_btn = st.columns([4, 1])
        with c_input:
            cnpj_digitado = st.text_input("CNPJ (apenas números):", max_chars=18, placeholder="00.000.000/0000-00", label_visibility="collapsed")
        with c_btn:
            buscar_cnpj = st.button("🔍 Consultar", type="primary", use_container_width=True)

    if buscar_cnpj and cnpj_digitado:
        with st.spinner("Conectando às bases públicas..."):
            dados_empresa = motor.consultar_cnpj_api(cnpj_digitado)
        
        if "erro" in dados_empresa:
            st.error(f"❌ {dados_empresa['erro']}")
        else:
            st.success("✅ Empresa localizada com sucesso!")
            st.session_state['empresa_selecionada'] = dados_empresa
            
            # LÓGICA DE FILTRO AUTOMÁTICO (Mantida igual para garantir integridade)
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

# EXIBIÇÃO DE DETALHES (ABA 3) - SÓ APARECE SE TIVER EMPRESA
if st.session_state['empresa_selecionada']:
    with tab_cnpj:
        dados_empresa = st.session_state['empresa_selecionada']
        
        # Reaproveita lógica de lista para visualização
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
        
        st.markdown("### 🛠️ Cruzamento: CNAE x Serviços")
        
        if lista_codigos_numericos:
            if not df_cnae.empty and 'cnae_numeros' in df_cnae.columns:
                resultado = df_cnae[df_cnae['cnae_numeros'].isin(lista_codigos_numericos)]
                
                if not resultado.empty:
                    st.dataframe(resultado, use_container_width=True, hide_index=True, column_config={"cnae": "CNAE", "descricao_cnae": "Atividade", "item_lista_servico": "LC 116", "descricao_item": "Serviço", "cnae_numeros_raw": None, "cnae_numeros": None})
                    
                    st.success(f"Foram identificados {len(resultado)} vínculos de serviços possíveis.")
                    
                    # PREPARAÇÃO PARA EXPORTAÇÃO
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

                            # BOTÕES DE EXPORTAÇÃO
                            st.markdown("### 📥 Exportar Relatórios")
                            c1, c2 = st.columns(2)
                            with c1:
                                excel_data = motor.gerar_excel_completo(dados_empresa, df_rel)
                                st.download_button("📊 Excel Completo (.xlsx)", excel_data, f"analise_{dados_empresa.get('cnpj')}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                            with c2:
                                pdf_data = motor.gerar_pdf_paisagem(dados_empresa, df_rel)
                                st.download_button("📄 Relatório Oficial (.pdf)", pdf_data, f"relatorio_{dados_empresa.get('cnpj')}.pdf", "application/pdf", use_container_width=True)
                else:
                    st.warning("⚠️ Os CNAEs desta empresa não possuem vínculo direto com a Lista de Serviços (LC 116).")
        else:
            st.error("Não foi possível ler os CNAEs da empresa.")
