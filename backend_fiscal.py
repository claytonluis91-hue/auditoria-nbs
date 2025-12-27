import pandas as pd
import os
import streamlit as st

# --- 1. FUNÇÃO DE CARREGAMENTO DE DADOS ---
@st.cache_data
def carregar_dados():
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    
    # Caminhos dos 3 arquivos
    path_main = os.path.join(pasta_atual, "AnexoVIII_Convertido.json")
    path_indop = os.path.join(pasta_atual, "IndOp_Descricoes.json")
    path_regras = os.path.join(pasta_atual, "classificacao_tributaria.json") # Seu novo arquivo
    
    # 1. Carrega Principal
    if not os.path.exists(path_main):
        return None, None, None
    df_main = pd.read_json(path_main, dtype={'INDOP': str})
    
    # 2. Carrega IndOp (Opcional)
    if os.path.exists(path_indop):
        df_indop = pd.read_json(path_indop, dtype={'CODIGO': str})
    else:
        df_indop = pd.DataFrame()

    # 3. Carrega Regras Tributárias (O Novo Arquivo!)
    if os.path.exists(path_regras):
        try:
            df_regras = pd.read_json(path_regras)
            # Normalização Vital: Cria uma coluna 'CHAVE' padronizada (000001) para cruzar com o outro arquivo
            col_codigo = 'Código da Classificação Tributária'
            if col_codigo in df_regras.columns:
                df_regras['CHAVE'] = df_regras[col_codigo].fillna(0).astype(int).apply(lambda x: f"{x:06d}")
            else:
                # Se o nome da coluna for diferente, tenta achar
                df_regras['CHAVE'] = df_regras.iloc[:, 0].astype(str) # Pega a primeira coluna na dúvida
        except:
            df_regras = pd.DataFrame()
    else:
        df_regras = pd.DataFrame()
        
    return df_main, df_indop, df_regras

# --- 2. MOTOR DE CÁLCULO (INTEGRADO AO ARQUIVO DE REGRAS) ---
def calcular_tributos(valor_servico, aliq_ibs_ref, aliq_cbs_ref, codigo_tributacao, df_regras):
    """
    Calcula IBS e CBS cruzando o código do serviço com o arquivo de regras fiscais.
    """
    
    # Garante que o código de entrada tenha 6 dígitos (ex: '1' vira '000001')
    try:
        chave_busca = f"{int(codigo_tributacao):06d}"
    except:
        chave_busca = "000000"

    # Valores padrão (caso não ache a regra)
    perc_red_ibs = 0.0
    perc_red_cbs = 0.0
    descricao_regra = "Regra não encontrada (Cálculo Padrão)"
    
    # BUSCA NO ARQUIVO DE REGRAS
    if not df_regras.empty and 'CHAVE' in df_regras.columns:
        regra_encontrada = df_regras[df_regras['CHAVE'] == chave_busca]
        
        if not regra_encontrada.empty:
            dados = regra_encontrada.iloc[0]
            # Pega os percentuais do arquivo (ex: 60, 30, 0)
            perc_red_ibs = float(dados.get('Percentual Redução IBS', 0))
            perc_red_cbs = float(dados.get('Percentual Redução CBS', 0))
            descricao_regra = dados.get('Descrição do Código da Classificação Tributária', 'Regra Personalizada')

    # --- CÁLCULO MATEMÁTICO ---
    # Fórmula: Alíquota Efetiva = Alíquota Cheia * (1 - (Redução / 100))
    
    aliq_ibs_efetiva = aliq_ibs_ref * (1 - (perc_red_ibs / 100))
    aliq_cbs_efetiva = aliq_cbs_ref * (1 - (perc_red_cbs / 100))
    
    valor_ibs = valor_servico * (aliq_ibs_efetiva / 100)
    valor_cbs = valor_servico * (aliq_cbs_efetiva / 100)
    
    total_imposto = valor_ibs + valor_cbs
    carga_total = aliq_ibs_efetiva + aliq_cbs_efetiva

    return {
        "descricao_regra": descricao_regra,
        "reducao_ibs": perc_red_ibs,
        "reducao_cbs": perc_red_cbs,
        "ibs_efetivo": aliq_ibs_efetiva,
        "cbs_efetivo": aliq_cbs_efetiva,
        "valor_ibs": valor_ibs,
        "valor_cbs": valor_cbs,
        "total_tributos": total_imposto,
        "carga_total_perc": carga_total
    }