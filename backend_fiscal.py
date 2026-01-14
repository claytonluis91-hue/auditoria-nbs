import pandas as pd
import os
import json
import streamlit as st
import requests
import re
from fpdf import FPDF
from datetime import datetime
import io

# --- 1. FUNÇÃO DE CARREGAMENTO DE DADOS ---
@st.cache_data
def carregar_dados():
    pasta_atual = os.path.dirname(os.path.abspath(__file__))
    
    path_main = os.path.join(pasta_atual, "AnexoVIII_Convertido.json")
    path_indop = os.path.join(pasta_atual, "IndOp_Descricoes.json")
    path_regras = os.path.join(pasta_atual, "classificacao_tributaria.json")
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

    # 4. Carrega CNAE (NOVO ARQUIVO)
    if os.path.exists(path_cnae):
        try:
            with open(path_cnae, 'r', encoding='utf-8') as f:
                data_cnae = json.load(f)
            df_cnae = pd.DataFrame(data_cnae)
            
            if not df_cnae.empty:
                df_cnae = df_cnae[df_cnae['cnae'].astype(str).str.contains(r'\d', na=False)]
                
                df_cnae = df_cnae.rename(columns={
                    'cnae': 'cnae_numeros_raw', 
                    'descricao_cnae': 'cnae',
                    'item_lista_servico': 'descricao_cnae',
                    'descricao_item': 'item_lista_servico',
                    'observacoes': 'descricao_item'
                })
                
                df_cnae['item_lista_servico'] = df_cnae['item_lista_servico'].astype(str).str.replace(',', '.')
                df_cnae['item_lista_servico'] = df_cnae['item_lista_servico'].apply(lambda x: x.lstrip('0') if x.startswith('0') else x)
                df_cnae['cnae_numeros'] = df_cnae['cnae'].astype(str).apply(lambda x: re.sub(r'\D', '', x))
                
        except Exception as e:
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
    mask = (
        df_cnae['cnae'].astype(str).str.contains(termo, case=False) |
        df_cnae['descricao_cnae'].str.contains(termo, case=False) |
        df_cnae['descricao_item'].str.contains(termo, case=False)
    )
    return df_cnae[mask]

# --- 4. CONSULTA CNPJ BLINDADA ---
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

# --- 5. EXPORTADORES (PDF & EXCEL) ---

# PDF SIMPLES (VERTICAL) - USADO NA CALCULADORA
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
    
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, '1. Dados da Empresa', 0, 1)
    pdf.set_font('Arial', '', 12)
    if dados_empresa:
        razao = dados_empresa.get('razao_social') or dados_empresa.get('nome') or "-"
        cnpj = dados_empresa.get('cnpj') or "-"
        pdf.cell(0, 8, f"Razão Social: {razao}", 0, 1)
        pdf.cell(0, 8, f"CNPJ: {cnpj}", 0, 1)
    else:
        pdf.cell(0, 8, "Simulação avulsa", 0, 1)
    pdf.ln(5)

    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 10, '2. Serviço Analisado (NBS)', 0, 1)
    pdf.set_font('Arial', '', 12)
    pdf.multi_cell(0, 8, f"NBS: {dados_servico.get('NBS', '-')}")
    pdf.multi_cell(0, 8, f"Descrição: {dados_servico.get('DESCRIÇÃO NBS', '-')}")
    pdf.multi_cell(0, 8, f"Item LC 116: {dados_servico.get('Item LC 116', '-')}")
    pdf.ln(5)

    if dados_simulacao:
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, '3. Comparativo Tributário', 0, 1)
        pdf.set_fill_color(200, 220, 255)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(60, 10, 'Cenário', 1, 0, 'C', 1)
        pdf.cell(40, 10, 'Alíquota Total', 1, 0, 'C', 1)
        pdf.cell(40, 10, 'Valor Tributo', 1, 1, 'C', 1)
        pdf.set_font('Arial', '', 10)
        pdf.cell(60, 10, 'Sistema Atual', 1, 0)
        pdf.cell(40, 10, f"{dados_simulacao['aliq_total_atual']:.2f}%", 1, 0, 'C')
        pdf.cell(40, 10, f"R$ {dados_simulacao['valor_atual']:,.2f}", 1, 1, 'C')
        pdf.cell(60, 10, 'Reforma (IBS/CBS)', 1, 0)
        pdf.cell(40, 10, f"{dados_simulacao['aliq_total_nova']:.2f}%", 1, 0, 'C')
        pdf.cell(40, 10, f"R$ {dados_simulacao['valor_novo']:,.2f}", 1, 1, 'C')
        pdf.ln(10)

    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- PDF PAISAGEM (TABELA COMPLETA) ---
class PDFLandscape(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Relatório Completo de Enquadramento Fiscal - LC 214', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}', 0, 0, 'C')

def gerar_pdf_paisagem(dados_empresa, df_dados):
    # Cria PDF em Paisagem ('L' = Landscape)
    pdf = PDFLandscape(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    
    # Cabeçalho Empresa
    pdf.set_font('Arial', 'B', 12)
    razao = dados_empresa.get('razao_social') or dados_empresa.get('nome') or "Empresa"
    cnpj = dados_empresa.get('cnpj') or ""
    pdf.cell(0, 8, f"Empresa: {razao} | CNPJ: {cnpj}", 0, 1, 'L')
    pdf.ln(5)
    
    # Cabeçalho Tabela
    pdf.set_font('Arial', 'B', 9)
    pdf.set_fill_color(220, 220, 220)
    
    # Larguras das colunas (Total ~275mm)
    w_lc = 15
    w_nbs = 20
    w_desc = 130
    w_cst = 20
    w_indop = 20
    w_local = 70
    
    pdf.cell(w_lc, 8, "LC 116", 1, 0, 'C', 1)
    pdf.cell(w_nbs, 8, "NBS", 1, 0, 'C', 1)
    pdf.cell(w_desc, 8, "Descrição NBS", 1, 0, 'C', 1)
    pdf.cell(w_cst, 8, "CST", 1, 0, 'C', 1)
    pdf.cell(w_indop, 8, "Cód.Loc", 1, 0, 'C', 1)
    pdf.cell(w_local, 8, "Local Incidência", 1, 1, 'C', 1)
    
    # Dados da Tabela
    pdf.set_font('Arial', '', 8)
    
    for index, row in df_dados.iterrows():
        # Trata textos longos para não quebrar o layout
        desc = str(row.get('DESCRIÇÃO NBS', ''))[:90] # Corta se for gigante
        local = str(row.get('LOCAL_OPERACAO', ''))[:45]
        
        pdf.cell(w_lc, 8, str(row.get('Item LC 116', '')), 1, 0, 'C')
        pdf.cell(w_nbs, 8, str(row.get('NBS', '')), 1, 0, 'C')
        pdf.cell(w_desc, 8, desc, 1, 0, 'L')
        pdf.cell(w_cst, 8, str(row.get('cClassTrib', '')), 1, 0, 'C')
        pdf.cell(w_indop, 8, str(row.get('INDOP', '')), 1, 0, 'C')
        pdf.cell(w_local, 8, local, 1, 1, 'L')
        
    return pdf.output(dest='S').encode('latin-1', 'replace')

# --- EXCEL COMPLETO ---
def gerar_excel_completo(dados_empresa, df_dados):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Aba 1: Empresa
        df_emp = pd.DataFrame([dados_empresa])
        df_emp.to_excel(writer, sheet_name='Dados Empresa', index=False)
        
        # Aba 2: Lista Completa
        # Seleciona e renomeia colunas para ficar bonito no Excel
        colunas_desejadas = ['Item LC 116', 'NBS', 'DESCRIÇÃO NBS', 'cClassTrib', 'nome cClassTrib', 'INDOP', 'LOCAL_OPERACAO']
        # Garante que as colunas existem antes de filtrar
        colunas_finais = [c for c in colunas_desejadas if c in df_dados.columns]
        
        df_export = df_dados[colunas_finais].copy()
        df_export.to_excel(writer, sheet_name='Analise Fiscal', index=False)
        
        # Ajuste de largura de colunas (opcional, requer xlsxwriter avançado, aqui vamos no básico)
    return output.getvalue()
