import streamlit as st
import backend_fiscal # Importa o seu arquivo motor

# --- CONFIGURAÇÃO INICIAL DA PÁGINA ---
st.set_page_config(layout="wide", page_title="Consultor Fiscal")

# CSS para ajuste do topo (padding)
st.markdown("""
    <style>
        .block-container {
            padding-top: 3rem;
            padding-bottom: 2rem;
        }
    </style>
""", unsafe_allow_html=True)

def main():
    # 1. Carrega todos os dados do backend
    df_main, df_indop, df_regras, df_cnae = backend_fiscal.carregar_dados()

    st.title("🔎 Auditoria e Consulta Fiscal")

    # Verificação de segurança: se o arquivo principal falhar, para tudo.
    if df_main is None:
        st.error("Erro crítico: Arquivo principal de dados (AnexoVIII) não encontrado.")
        return

    # 2. CRIAÇÃO DAS ABAS (Tabs)
    # Tab 1: O que você já tinha (Calculadora + Pesquisa NBS)
    # Tab 2: A novidade (Pesquisa CNAE)
    tab_calculadora, tab_cnae = st.tabs(["🧮 Calculadora & NBS", "📋 Consulta CNAE x Serviço"])

    # =========================================================================
    # ABA 1: CONSULTA NBS E CALCULADORA (RESTAURADA)
    # =========================================================================
    with tab_calculadora:
        col_esq, col_dir = st.columns([1, 1.5])

        with col_esq:
            st.subheader("Parâmetros do Serviço")
            
            # --- INPUTS DO USUÁRIO ---
            valor_servico = st.number_input("Valor do Serviço (R$)", min_value=0.0, value=1000.0, step=100.0)
            
            # Selectbox para escolher o serviço pelo NBS (usando o df_main)
            # Cria uma lista formatada "Código - Descrição" para facilitar a escolha
            opcoes_servicos = df_main['NBS_SIMPLIFICADO'].astype(str) + " - " + df_main['DESC_SIMPLIFICADA']
            servico_selecionado = st.selectbox("Selecione o Serviço (NBS):", options=opcoes_servicos)

            # Extrai o código NBS da seleção (parte antes do " - ")
            nbs_codigo = servico_selecionado.split(" - ")[0]

            # Busca os dados desse serviço específico no DataFrame
            dados_servico = df_main[df_main['NBS_SIMPLIFICADO'] == nbs_codigo].iloc[0]
            
            # Pega o Código de Tributação para usar no cálculo
            cod_tributacao = dados_servico.get('COD_TRIBUTACAO', '000000')

            # Alíquotas de Referência (Padrão ou ajustável)
            st.markdown("---")
            st.caption("Alíquotas de Referência (%)")
            col_aliq1, col_aliq2 = st.columns(2)
            aliq_ibs_ref = col_aliq1.number_input("IBS Ref.", value=17.7)
            aliq_cbs_ref = col_aliq2.number_input("CBS Ref.", value=8.8)

            # Botão de Calcular
            calcular = st.button("Calcular Tributos", type="primary")

        with col_dir:
            st.subheader("Resultado da Análise")
            
            if calcular:
                # CHAMA A FUNÇÃO DE CÁLCULO DO BACKEND
                resultado = backend_fiscal.calcular_tributos(
                    valor_servico, 
                    aliq_ibs_ref, 
                    aliq_cbs_ref, 
                    cod_tributacao, 
                    df_regras
                )

                # --- EXIBIÇÃO DOS RESULTADOS (VISUAL) ---
                
                # 1. Card com a Regra Aplicada
                st.info(f"📋 **Regra Identificada:** {resultado['descricao_regra']}")

                # 2. Métricas Principais
                col_metrica1, col_metrica2 = st.columns(2)
                col_metrica1.metric("Carga Total Estimada", f"{resultado['carga_total_perc']:.2f}%")
                col_metrica1.metric("Valor Total Tributos", f"R$ {resultado['total_tributos']:.2f}")
                
                col_metrica2.metric("Redução IBS", f"{resultado['reducao_ibs']}%")
                col_metrica2.metric("Redução CBS", f"{resultado['reducao_cbs']}%")

                st.markdown("---")

                # 3. Detalhamento (Tabela ou Texto)
                st.markdown("#### Detalhamento do Cálculo")
                st.write(f"**IBS Efetivo:** {resultado['ibs_efetivo']:.2f}% -> R$ {resultado['valor_ibs']:.2f}")
                st.write(f"**CBS Efetivo:** {resultado['cbs_efetivo']:.2f}% -> R$ {resultado['valor_cbs']:.2f}")

                # 4. Dados Cadastrais do Serviço (Do arquivo principal)
                st.markdown("---")
                with st.expander("Ver Detalhes do Cadastro NBS"):
                    st.json(dados_servico.to_dict())

    # =========================================================================
    # ABA 2: CONSULTA CNAE (NOVA FUNCIONALIDADE)
    # =========================================================================
    with tab_cnae:
        st.subheader("Consulta Cruzada: CNAE x Lista de Serviços (LC 116)")
        st.markdown("Pesquise pelo código CNAE, descrição da atividade ou código do serviço.")

        if not df_cnae.empty:
            # Campo de busca
            termo = st.text_input("Digite sua busca:", placeholder="Ex: 6920, Contabilidade, ou 17.19")
            
            if termo:
                # CHAMA A FUNÇÃO DE BUSCA DO BACKEND
                resultado_cnae = backend_fiscal.buscar_cnae(df_cnae, termo)
                
                qtd = len(resultado_cnae)
                if qtd > 0:
                    st.success(f"{qtd} registro(s) encontrado(s).")
                    st.dataframe(
                        resultado_cnae,
                        column_config={
                            "cnae": "CNAE",
                            "descricao_cnae": "Descrição CNAE",
                            "item_lista_servico": "Item LC 116",
                            "descricao_item": "Descrição Serviço",
                            "observacoes": "Observações"
                        },
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.warning("Nenhum registro encontrado para essa busca.")
            else:
                st.info("👆 Digite algo acima para filtrar a tabela.")
                # Mostra uma amostra inicial
                st.dataframe(df_cnae.head(10), use_container_width=True, hide_index=True)

        else:
            st.error("O arquivo 'cnae_lista_servicos.json' não foi carregado corretamente.")


if __name__ == "__main__":
    main()
