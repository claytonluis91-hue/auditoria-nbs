import pandas as pd
import os
import json
import streamlit as st

# --- 1. FUNÇÃO DE CARREGAMENTO DE DADOS ---
@st.cache_data
def carregar_dados():
    """
    Carrega todos os arquivos JSON necessários:
    1. AnexoVIII_Convertido.json (Tabela principal NBS)
    2. IndOp_Descricoes.json (Descrições de Operações)
    3. classificacao_tributaria.json (Regras de alíquotas/reduções)
    4. cnae_lista_servicos.json (Nova lista de CNAE x Serviço)
    """
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    
    # Definição dos caminhos
    path_main = os.path.join(pasta_atual, "AnexoVIII_Convertido.json")
    path_indop = os.path.join(pasta_atual, "IndOp_Descricoes.json")
    path_regras = os.path.join(pasta_atual, "classificacao_tributaria.json")
    path_cnae = os.path.join(pasta_atual, "cnae_lista_servicos.json") 
    
    # 1. Carrega Principal (NBS)
    if not os.path.exists(path_main):
        # Se não achar o principal, retorna tudo vazio para evitar erro de quebra total
        return None, None, None, None
    df_main = pd.read_json(path_main, dtype={'INDOP': str})
    
    # 2. Carrega IndOp
    if os.path.exists(path_indop):
        df_indop = pd.read_json(path_indop, dtype={'CODIGO': str})
    else:
        df_indop = pd.DataFrame()

    # 3. Carrega Regras Tributárias
    if os.path.exists(path_regras):
        try:
            df_regras = pd.read_json(path_regras)
            # Normalização da chave de busca (garante 6 dígitos: '1' vira '000001')
            col_codigo = 'Código da Classificação Tributária'
            if col_codigo in df_regras.columns:
                df_regras['CHAVE'] = df_regras[col_codigo].fillna(0).astype(int).apply(lambda x: f"{x:06d}")
            else:
                # Tenta pegar a primeira coluna se o nome for diferente
                df_regras['CHAVE'] = df_regras.iloc[:, 0].astype(str)
        except:
            df_regras = pd.DataFrame()
    else:
        df_regras = pd.DataFrame()

    # 4. Carrega CNAE (NOVA FUNCIONALIDADE)
    if os.path.exists(path_cnae):
        try:
            with open(path_cnae, 'r', encoding='utf-8') as f:
                data_cnae = json.load(f)
            df_cnae = pd.DataFrame(data_cnae)
        except Exception:
            df_cnae = pd.DataFrame()
    else:
        df_cnae = pd.DataFrame()
        
    return df_main, df_indop, df_regras, df_cnae

# --- 2. MOTOR DE CÁLCULO ---
def calcular_tributos(valor_servico, aliq_ibs_ref, aliq_cbs_ref, codigo_tributacao, df_regras):
    """
    Calcula IBS e CBS cruzando o código do serviço com o arquivo de regras fiscais.
    """
    # Formata o código de entrada para bater com a chave (ex: '000001')
    try:
        chave_busca = f"{int(codigo_tributacao):06d}"
    except:
        chave_busca = "000000"

    # Valores padrão
    perc_red_ibs = 0.0
    perc_red_cbs = 0.0
    descricao_regra = "Regra não encontrada (Cálculo Padrão)"
    
    # Busca nas regras
    if not df_regras.empty and 'CHAVE' in df_regras.columns:
        regra_encontrada = df_regras[df_regras['CHAVE'] == chave_busca]
        
        if not regra_encontrada.empty:
            dados = regra_encontrada.iloc[0]
            perc_red_ibs = float(dados.get('Percentual Redução IBS', 0))
            perc_red_cbs = float(dados.get('Percentual Redução CBS', 0))
            descricao_regra = dados.get('Descrição do Código da Classificação Tributária', 'Regra Personalizada')

    # Cálculos Matemáticos
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

# --- 3. NOVA FUNÇÃO DE BUSCA CNAE (Lógica isolada) ---
def buscar_cnae(df_cnae, termo_busca):
    """
    Filtra a tabela de CNAE com base no termo digitado.
    Procura no Código CNAE, na Descrição CNAE e na Descrição do Serviço.
    """
    if df_cnae.empty or not termo_busca:
        return pd.DataFrame()
    
    mask = (
        df_cnae['cnae'].astype(str).str.contains(termo_busca, case=False) | 
        df_cnae['descricao_cnae'].str.contains(termo_busca, case=False) |
        df_cnae['descricao_item'].str.contains(termo_busca, case=False)
    )
    return df_cnae[mask]
