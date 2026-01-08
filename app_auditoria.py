import streamlit as st
import motor  # Importa o arquivo motor.py (certifique-se que estão na mesma pasta)

# --- Configuração Inicial ---
st.set_page_config(layout="wide", page_title="Consultor Fiscal")

# CSS para ajuste do topo
st.markdown("""
    <style>
        .block-container {
            padding-top: 3rem;
            padding-bottom: 2rem;
        }
    </style>
""", unsafe_allow_html=True)

def main():
    # 1. Carrega os dados vindos do motor (agora são 4 variáveis)
    df_main, df_indop, df_regras, df_cnae = motor.carregar_dados()

    st.title("🔎 Auditoria e Consulta Fiscal")

    if df_main is None:
        st.error("Erro crítico: Arquivo principal de dados não encontrado.")
        return

    # 2. Criação das Abas
    tab_calculadora, tab_cnae = st.tabs(["🧮 Calculadora & NBS", "📋 Consulta CNAE x Serviço"])

    # --- ABA 1: Calculadora (Sua interface antiga vem aqui) ---
    with tab_calculadora:
        st.write("### Calculadora de Tributos e Consulta NBS")
        # [AQUI VOCÊ MANTÉM O SEU CÓDIGO DE INTERFACE DA CALCULADORA]
        # Exemplo de uso da função do motor:
        # resultado = motor.calcular_tributos(...)
        st.info("Mantenha aqui os inputs e botões da sua calculadora original.")

    # --- ABA 2: Nova Consulta CNAE ---
    with tab_cnae:
        st.header("Vínculo CNAE x Lista de Serviços (LC 116)")
        
        if not df_cnae.empty:
            termo = st.text_input("Pesquisar CNAE ou Serviço:", placeholder="Ex: 6920 ou Contabilidade")
            
            if termo:
                # Chama a função de busca lá do motor
                resultado_df = motor.buscar_cnae(df_cnae, termo)
                
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
                # Mostra uma amostra inicial
                st.dataframe(df_cnae.head(5), use_container_width=True, hide_index=True)
        else:
            st.error("O arquivo 'cnae_lista_servicos.json' não foi carregado. Verifique a pasta.")

if __name__ == "__main__":
    main()
