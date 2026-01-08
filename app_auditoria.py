import streamlit as st
import backend_fiscal  # <--- AJUSTADO: Agora importa o nome correto do seu arquivo

# --- Configuração Inicial ---
st.set_page_config(layout="wide", page_title="Consultor Fiscal")

# CSS para ajustar aquele espaçamento do topo
st.markdown("""
    <style>
        .block-container {
            padding-top: 3rem;
            padding-bottom: 2rem;
        }
    </style>
""", unsafe_allow_html=True)

def main():
    # 1. Carrega os dados chamando a função do SEU backend
    # Note que agora usamos "backend_fiscal." antes da função
    df_main, df_indop, df_regras, df_cnae = backend_fiscal.carregar_dados()

    st.title("🔎 Auditoria e Consulta Fiscal")

    if df_main is None:
        st.error("Erro crítico: Arquivo principal de dados (AnexoVIII) não encontrado.")
        return

    # 2. Criação das Abas
    tab_calculadora, tab_cnae = st.tabs(["🧮 Calculadora & NBS", "📋 Consulta CNAE x Serviço"])

    # --- ABA 1: Calculadora ---
    with tab_calculadora:
        st.write("### Calculadora de Tributos e Consulta NBS")
        
        # --- AQUI VAI O SEU CÓDIGO ANTIGO DA CALCULADORA ---
        # Cole aqui a lógica de inputs e botões que você já tinha.
        # Lembre-se: se você chamar a função de cálculo, use:
        # backend_fiscal.calcular_tributos(...)
        
        st.info("👆 Lembre-se de colar os inputs da calculadora aqui dentro.")

    # --- ABA 2: Nova Consulta CNAE ---
    with tab_cnae:
        st.header("Vínculo CNAE x Lista de Serviços (LC 116)")
        
        if not df_cnae.empty:
            termo = st.text_input("Pesquisar CNAE ou Serviço:", placeholder="Ex: 6920 ou Contabilidade")
            
            if termo:
                # Chama a nova função de busca localizada no backend_fiscal
                resultado_df = backend_fiscal.buscar_cnae(df_cnae, termo)
                
                qtd = len(resultado_df)
                if qtd > 0:
                    st.success(f"{qtd} registro(s) encontrado(s).")
                    st.dataframe(
                        resultado_df,
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
                    st.warning("Nenhum resultado encontrado.")
            else:
                st.caption("Digite algo para iniciar a pesquisa.")
                # Mostra uma amostra inicial para não ficar vazio
                st.dataframe(df_cnae.head(5), use_container_width=True, hide_index=True)
        else:
            st.error("O arquivo 'cnae_lista_servicos.json' não foi carregado. Verifique se ele está na mesma pasta.")

if __name__ == "__main__":
    main()
