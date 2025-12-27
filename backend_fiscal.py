import pandas as pd
import os
import streamlit as st

# --- 1. FUNÇÃO DE CARREGAMENTO DE DADOS ---
@st.cache_data
def carregar_dados():
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    path_main = os.path.join(pasta_atual, "AnexoVIII_Convertido.json")
    path_indop = os.path.join(pasta_atual, "IndOp_Descricoes.json")
    
    if not os.path.exists(path_main):
        return None, None
        
    df_main = pd.read_json(path_main, dtype={'INDOP': str})
    
    if os.path.exists(path_indop):
        df_indop = pd.read_json(path_indop, dtype={'CODIGO': str})
    else:
        df_indop = pd.DataFrame()
        
    return df_main, df_indop

# --- 2. MOTOR DE CÁLCULO (SIMULADOR LC 214) ---
def calcular_tributos(valor_servico, aliq_ibs_ref, aliq_cbs_ref, codigo_tributacao):
    """
    Calcula IBS e CBS baseado na LC 214/2025 e no código de tributação (cClassTrib).
    Retorna um dicionário com os valores calculados.
    """
    
    # Lógica de Redutor baseada no Código de Tributação (cClassTrib)
    # ATENÇÃO: Essa lógica deve ser ajustada conforme a Lei final.
    # Exemplo hipotético de mapeamento de reduções:
    
    fator_reducao = 0.0 # Quanto DESCONTA (0 = paga cheio, 0.6 = desconto de 60%)
    tipo_regime = "Padrão"
    
    # Convertendo código para inteiro para facilitar
    try:
        cod = int(codigo_tributacao)
    except:
        cod = 0

    # --- REGRAS DE REDUÇÃO (SIMULAÇÃO) ---
    # Códigos hipotéticos baseados na lógica da Reforma:
    if cod == 1: # Tributado Integralmente
        fator_reducao = 0.0
        tipo_regime = "Tributação Padrão (Sem Redução)"
    elif cod in [20, 21]: # Exemplo: Redução de 30% (Profissões Intelectuais, etc)
        fator_reducao = 0.30
        tipo_regime = "Regime Diferenciado (Redução de 30%)"
    elif cod in [30, 31]: # Exemplo: Redução de 60% (Saúde, Educação)
        fator_reducao = 0.60
        tipo_regime = "Regime Diferenciado (Redução de 60%)"
    elif cod == 40: # Isento / Imune
        fator_reducao = 1.00 # 100% de desconto
        tipo_regime = "Isenção / Imunidade"
    else:
        # Se não mapeado, assume padrão por segurança
        tipo_regime = "Tributação Padrão (Código não mapeado especificamente)"
        fator_reducao = 0.0

    # Cálculo das Alíquotas Efetivas
    aliq_ibs_efetiva = aliq_ibs_ref * (1 - fator_reducao)
    aliq_cbs_efetiva = aliq_cbs_ref * (1 - fator_reducao)
    
    # Cálculo dos Valores
    valor_ibs = valor_servico * (aliq_ibs_efetiva / 100)
    valor_cbs = valor_servico * (aliq_cbs_efetiva / 100)
    total_imposto = valor_ibs + valor_cbs
    carga_tributaria_total = aliq_ibs_efetiva + aliq_cbs_efetiva

    return {
        "regime": tipo_regime,
        "reducao_aplicada": f"{fator_reducao*100:.0f}%",
        "ibs_efetivo": aliq_ibs_efetiva,
        "cbs_efetivo": aliq_cbs_efetiva,
        "valor_ibs": valor_ibs,
        "valor_cbs": valor_cbs,
        "total_tributos": total_imposto,
        "carga_total_perc": carga_tributaria_total
    }