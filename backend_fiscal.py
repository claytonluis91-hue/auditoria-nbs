import pandas as pd
import os
import json
import streamlit as st
import requests
import re
from fpdf import FPDF
from datetime import datetime

# --- 1. FUNÇÃO DE CARREGAMENTO DE DADOS ---
@st.cache_data
def carregar_dados():
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    
    path_main = os.path.join(pasta_atual, "AnexoVIII_Convertido.json")
    path_indop = os.path.join(pasta_atual, "IndOp_Descricoes.json")
    path_regras = os.path.join(pasta_atual, "classificacao_tributaria.json")
    
    # ATENÇÃO: Agora apontamos para o NOVO arquivo
    path_cnae = os.path.join(pasta_atual, "lista_servicos_completa.json")
    
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

    # 4. Carrega CNAE (ADAPTADO PARA O NOVO ARQUIVO)
    if os.path.exists(path_cnae):
        try:
            with open(path_cnae, 'r', encoding='utf-8') as f:
                data_cnae = json.load(f)
            df_cnae = pd.DataFrame(data_cnae)
            
            if not df_cnae.empty:
                # --- LIMPEZA E TRADUÇÃO DAS COLUNAS (NOVO!) ---
                
                # 1. Remove linhas de cabeçalho "lixo" (onde cnae não é número)
                # Filtra apenas onde a coluna 'cnae' contém dígitos
                df_cnae = df_cnae[df_cnae['cnae'].astype(str).str.contains(r'\d', na=False)]
                
                # 2. Renomeia as colunas para o padrão do sistema
                # No novo arquivo:
                # 'cnae' -> É o número limpo (ex: 6201501)
                # 'descricao_cnae' -> É o formatado (ex: 6201-5/01)
                # 'item_lista_servico' -> É a Descrição do CNAE
                # 'descricao_item' -> É o Código LC 116 (ex: 01,01)
                # 'observacoes' -> É a Descrição do Item LC
                
                df_cnae = df_cnae.rename(columns={
                    'cnae': 'cnae_numeros_raw', # Guardamos o original numérico
                    'descricao_cnae': 'cnae',   # Esse vira o CNAE visual (formatado)
                    'item_lista_servico': 'descricao_cnae', # Descrição da atividade
                    'descricao_item': 'item_lista_servico', # Código LC
                    'observacoes': 'descricao_item' # Descrição LC
                })
                
                # 3. Corrige o Código LC 116 (Troca vírgula por ponto: "01,01" -> "1.01")
                df_cnae['item_lista_servico'] = df_cnae['item_lista_servico'].astype(str).str.replace(',', '.')
                # Remove zero à esquerda se necessário (ex: "01.01" -> "1.01") para bater com outras bases
                df_cnae['item_lista_servico'] = df_cnae['item_lista_servico'].apply(lambda x: x.lstrip('0') if x.startswith('0') else x)

                # 4. Garante a coluna de busca numérica (CRUCIAL PARA A BUSCA POR CNPJ)
                # Usa a coluna que já veio numérica ou limpa a formatada por garantia
                df_cnae['cnae_numeros'] = df_cnae['cnae'].astype(str).apply(lambda x: re.sub(r'\D', '', x))
                
        except Exception as e:
            st.error(f"Erro ao processar novo arquivo CNAE: {e}")
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
        "diferenca": diferenca_valor,
        "total_tributos": valor_tributo_novo,
        "carga_total_perc": aliq_total_nova,
        "valor_ibs": valor * (ibs_efetiva / 100),
        "valor_cbs": valor * (cbs_efetiva / 100)
    }

# --- 3. BUSCA CNAE MANUAL ---
def buscar_cnae(df_cnae, termo):
    if df_cnae.empty or not termo:
        return pd.DataFrame()
    
    # Adaptação: busca também na descrição do item LC (que agora está na coluna renomeada descricao_item)
    mask = (
        df_cnae['cnae'].astype(str).str.contains(termo, case=False) |
        df_cnae['descricao_cnae'].str.contains(termo, case=False) |
        df_cnae['descricao_item'].str.contains(termo, case=False)
    )
    return df_cnae[mask]

# --- 4. CONSULTA CNPJ BLINDADA (MANTIDA) ---
def consultar_cnpj_api(cnpj_input):
    cnpj_limpo = re.sub(r'\D', '', cnpj_input)
    if len(cnpj_limpo) != 14:
        return {"erro": "CNPJ deve ter 14 dígitos."}
    
    fontes = [
        {"url": f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}", "tipo": "v1"},
        {"url": f"https://brasilapi.com.br/api/cnpj/v2/{cnpj_limpo}", "tipo": "v2"},
        {"url": f"https://minhareceita.org/{cnpj_limpo}", "tipo": "minha_receita"},
        {"url": f"https://www.receitaws.com.br/v1/cnpj/{cnpj_limpo}", "tipo": "receitaws"}
    ]
    
    ultimo_erro = ""
    for fonte in fontes:
        try:
            response = requests.get(fonte["url"], timeout=8)
            if response.status_code == 200:
                dados = response.json()
                if fonte['tipo'] == 'receitaws' and dados.get('status') == 'ERROR':
                    ultimo_erro = dados.get('message', 'Erro na ReceitaWS')
                    continue
                dados['fonte_dados'] = fonte['tipo']
                return dados
            elif response.status_code == 404:
                ultimo_erro = "CNPJ não encontrado."
            elif response.status_code == 429:
                ultimo_erro = "API ocupada."
        except Exception as e:
            ultimo_erro = f"Erro conexão: {str(e)}"
            continue
            
    return {"erro": f"Não foi possível consultar. ({ultimo_erro})"}

# --- 5. GERADOR DE RELATÓRIO PDF (MANTIDO) ---
class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Relatório de Análise Fiscal - LC 214/2023', 0, 1, 'C')
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def gerar_relatorio_pdf(dados_empresa, dados_simulacao, dados_servico):
    pdf = PDFReport()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)
    
    # 1. Dados da Empresa
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, '1. Dados da Empresa', 0, 1)
    pdf.set_font('Arial', '', 12)
    
    if dados_empresa:
        razao = dados_empresa.get('razao_social') or dados_empresa.get('nome') or "Não informado"
        cnpj = dados_empresa.get('cnpj') or "Não informado"
        pdf.cell(0, 8, f"Razão Social: {razao}", 0, 1)
        pdf.cell(0, 8, f"CNPJ: {cnpj}", 0, 1)
    else:
        pdf.cell(0, 8, "Simulação avulsa (Sem empresa vinculada)", 0, 1)
    pdf.ln(5)

    # 2. Dados do Serviço
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, '2. Serviço Analisado (NBS)', 0, 1)
    pdf.set_font('Arial', '', 12)
    pdf.multi_cell(0, 8, f"NBS: {dados_servico.get('NBS', '-')}")
    pdf.multi_cell(0, 8, f"Descrição: {dados_servico.get('DESCRIÇÃO NBS', '-')}")
    pdf.multi_cell(0, 8, f"Item LC 116: {dados_servico.get('Item LC 116', '-')}")
    pdf.ln(5)

    # 3. Resultado
    if dados_simulacao:
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, '3. Comparativo Tributário', 0, 1)
        
        pdf.set_fill_color(200, 220, 255)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 10, 'Cenário', 1, 0, 'C', 1)
        pdf.cell(40, 10, 'Alíquota Total', 1, 0, 'C', 1)
        pdf.cell(40, 10, 'Valor Tributo', 1, 1, 'C', 1)
        
        pdf.set_font('Arial', '', 10)
        pdf.cell(60, 10, 'Sistema Atual (PIS/COFINS/ISS)', 1, 0)
        pdf.cell(40, 10, f"{dados_simulacao['aliq_total_atual']:.2f}%", 1, 0, 'C')
        pdf.cell(40, 10, f"R$ {dados_simulacao['valor_atual']:,.2f}", 1, 1, 'C')
        
        pdf.cell(60, 10, 'Reforma (IBS/CBS)', 1, 0)
        pdf.cell(40, 10, f"{dados_simulacao['aliq_total_nova']:.2f}%", 1, 0, 'C')
        pdf.cell(40, 10, f"R$ {dados_simulacao['valor_novo']:,.2f}", 1, 1, 'C')
        pdf.ln(5)
        
        pdf.set_font('Arial', 'B', 12)
        dif = dados_simulacao['diferenca']
        if dif > 0:
            pdf.set_text_color(180, 0, 0)
            pdf.cell(0, 10, f"Impacto: Aumento de Carga de R$ {dif:,.2f}", 0, 1)
        elif dif < 0:
            pdf.set_text_color(0, 100, 0)
            pdf.cell(0, 10, f"Impacto: Economia Estimada de R$ {abs(dif):,.2f}", 0, 1)
        else:
            pdf.cell(0, 10, "Impacto: Neutro", 0, 1)
        pdf.set_text_color(0, 0, 0)

    pdf.ln(10)
    pdf.set_font('Arial', 'I', 10)
    pdf.cell(0, 10, f"Gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}", 0, 1, 'R')

    return pdf.output(dest='S').encode('latin-1', 'replace')
