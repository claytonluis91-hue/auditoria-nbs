import pandas as pd
import os
import json
import streamlit as st
import requests
import re

# --- 1. FUNÇÃO DE CARREGAMENTO DE DADOS ---
@st.cache_data
def carregar_dados():
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    
    path_main = os.path.join(pasta_atual, "AnexoVIII_Convertido.json")
    path_indop = os.path.join(pasta_atual, "IndOp_Descricoes.json")
    path_regras = os.path.join(pasta_atual, "classificacao_tributaria.json")
    path_cnae = os.path.join(pasta_atual, "cnae_lista_servicos.json")
    
    # 1. Carrega Principal (NBS)
    if not os.path.exists(path_main):
        return None, None, None, None
    df_main = pd.read_json(path_main, dtype={'INDOP': str, 'cClassTrib': str})
    
    # 2. Carrega IndOp
    if os.path.exists(path_indop):
        df_indop = pd.read_json(path_indop, dtype={'CODIGO': str})
    else:
        df_indop = pd.DataFrame()

    # 3. Carrega Regras
    if os.path.exists(path_regras):
        try:
            df_regras = pd.read_json(path_regras)
            col_codigo = 'Código da Classificação Tributária'
            if col_codigo in df_regras.columns:
                df_regras['CHAVE'] = df_regras[col_codigo].fillna(0).astype(int).apply(lambda x: f"{x:06d}")
            else:
                df_regras['CHAVE'] = df_regras.iloc[:, 0].astype(str)
        except:
            df_regras = pd.DataFrame()
    else:
        df_regras = pd.DataFrame()

    # 4. Carrega CNAE
    if os.path.exists(path_cnae):
        try:
            with open(path_cnae, 'r', encoding='utf-8') as f:
                data_cnae = json.load(f)
            df_cnae = pd.DataFrame(data_cnae)
            
            # CRIAR COLUNA LIMPA (APENAS NÚMEROS) PARA FACILITAR O CRUZAMENTO
            # Ex: transforma "6920-6/01" em "6920601"
            if not df_cnae.empty:
                df_cnae['cnae_limpo'] = df_cnae['cnae'].astype(str).apply(lambda x: re.sub(r'\D', '', x))
                
        except:
            df_cnae = pd.DataFrame()
    else:
        df_cnae = pd.DataFrame()
        
    return df_main, df_indop, df_regras, df_cnae

# --- 2. MOTOR DE CÁLCULO COMPARATIVO ---
def calcular_comparativo(valor, iss, pis, cofins, ibs_ref, cbs_ref, codigo_tributacao, df_regras):
    aliq_total_atual = iss + pis + cofins
    valor_tributo_atual = valor * (aliq_total_atual / 100)

    try:
        chave_busca = f"{int(codigo_tributacao):06d}"
    except:
        chave_busca = "000000"

    perc_red_ibs = 0.0
    perc_red_cbs = 0.0
    descricao_regra = "Padrão (Sem Benefício)"
    
    if not df_regras.empty and 'CHAVE' in df_regras.columns:
        regra_encontrada = df_regras[df_regras['CHAVE'] == chave_busca]
        if not regra_encontrada.empty:
            dados = regra_encontrada.iloc[0]
            perc_red_ibs = float(dados.get('Percentual Redução IBS', 0))
            perc_red_cbs = float(dados.get('Percentual Redução CBS', 0))
            descricao_regra = dados.get('Descrição do Código da Classificação Tributária', 'Regra Personalizada')

    ibs_efetiva = ibs_ref * (1 - (perc_red_ibs / 100))
    cbs_efetiva = cbs_ref * (1 - (perc_red_cbs / 100))
    aliq_total_nova = ibs_efetiva + cbs_efetiva
    valor_tributo_novo = valor * (aliq_total_nova / 100)
    diferenca_valor = valor_tributo_novo - valor_tributo_atual

    return {
        "aliq_total_atual": aliq_total_atual,
        "valor_atual": valor_tributo_atual,
        "descricao_regra": descricao_regra,
        "reducao_ibs": perc_red_ibs,
        "reducao_cbs": perc_red_cbs,
        "ibs_efetivo": ibs_efetiva,
        "cbs_efetivo": cbs_efetiva,
        "aliq_total_nova": aliq_total_nova,
        "valor_novo": valor_tributo_novo,
        "diferenca": diferenca_valor
    }

# --- 3. BUSCA CNAE MANUAL ---
def buscar_cnae(df_cnae, termo):
    if df_cnae.empty or not termo:
        return pd.DataFrame()
    mask = (
        df_cnae['cnae'].astype(str).str.contains(termo, case=False) |
        df_cnae['descricao_cnae'].str.contains(termo, case=False) |
        df_cnae['descricao_item'].str.contains(termo, case=False)
    )
    return df_cnae[mask]

# --- 4. CONSULTA CNPJ VIA API (NOVA FUNÇÃO) ---
def consultar_cnpj_api(cnpj_input):
    """
    Consulta a BrasilAPI e retorna os dados da empresa.
    """
    # Limpa o CNPJ (deixa só números)
    cnpj_limpo = re.sub(r'\D', '', cnpj_input)
    
    if len(cnpj_limpo) != 14:
        return {"erro": "CNPJ deve ter 14 dígitos."}
    
    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            return {"erro": "CNPJ não encontrado na base da Receita."}
        elif response.status_code == 429:
            return {"erro": "Muitas consultas. Aguarde um momento."}
        else:
            return {"erro": f"Erro na API: {response.status_code}"}
    except Exception as e:
        return {"erro": f"Erro de conexão: {str(e)}"}
