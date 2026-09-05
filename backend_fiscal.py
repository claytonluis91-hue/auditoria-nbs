"""Motor de dados, simulação e relatórios da auditoria NBS.

As funções deste módulo não substituem uma análise tributária profissional. O
objetivo é produzir candidatos de classificação e cenários comparáveis, sempre
mantendo a rastreabilidade dos dados utilizados.
"""

from __future__ import annotations

import html
import io
import json
import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Iterable

import pandas as pd
import requests
import streamlit as st
from fpdf import FPDF


VERSAO_DADOS = "2026.07"
FONTE_LC_214 = "https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214compilado.htm"
FONTE_NBS = (
    "https://www.gov.br/mdic/pt-br/assuntos/sdic/comercio-e-servicos/"
    "nbs-nomenclatura-brasileira-de-servicos/painel-de-codigos-nbs/"
    "painel-de-codigos-nbs/"
)
AVISO_CLASSIFICACAO = (
    "Resultado indicativo. O CNAE auxilia a localizar possibilidades, mas não "
    "determina isoladamente a NBS. Confirme a natureza do serviço, as notas "
    "explicativas e a legislação vigente."
)


class ValidacaoFiscalError(ValueError):
    """Erro de entrada ou consistência apresentado de forma amigável."""


def _texto_sem_acentos(valor: Any) -> str:
    texto = "" if valor is None else str(valor)
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFKD", texto)
        if not unicodedata.combining(caractere)
    ).casefold()


def normalizar_codigo_servico(valor: Any) -> str:
    """Normaliza itens da LC 116 preservando o segundo dígito decimal.

    Bases que serializam 4.10 como número acabam produzindo 4.1. Como os itens
    oficiais possuem dois dígitos após o ponto, uma única casa é completada à
    direita: 4.1 -> 4.10. Já 4.01 permanece 4.01.
    """

    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    texto = str(valor).strip().replace(",", ".")
    correspondencia = re.search(r"(\d+)\s*\.\s*(\d+)", texto)
    if not correspondencia:
        digitos = re.sub(r"\D", "", texto)
        return str(int(digitos)) if digitos else ""
    grupo = str(int(correspondencia.group(1)))
    item = correspondencia.group(2)[:2].ljust(2, "0")
    return f"{grupo}.{item}"


def normalizar_cnae(valor: Any) -> str:
    digitos = re.sub(r"\D", "", "" if valor is None else str(valor))
    return digitos.zfill(7) if digitos else ""


def formatar_cnae(valor: Any) -> str:
    digitos = normalizar_cnae(valor)
    return f"{digitos[:4]}-{digitos[4]}/{digitos[5:]}" if len(digitos) == 7 else digitos


def formatar_cnpj(valor: Any) -> str:
    digitos = re.sub(r"\D", "", "" if valor is None else str(valor))
    if len(digitos) != 14:
        return str(valor or "")
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def normalizar_classificacao(valor: Any) -> str:
    digitos = re.sub(r"\D", "", "" if valor is None else str(valor))
    return digitos.zfill(6) if digitos else "000000"


def _carregar_json(caminho: str) -> list[dict[str, Any]]:
    with open(caminho, "r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados, list):
        raise ValidacaoFiscalError(f"Formato inválido em {os.path.basename(caminho)}.")
    return dados


@st.cache_data(show_spinner=False)
def carregar_dados():
    pasta = os.path.dirname(os.path.abspath(__file__))
    caminhos = {
        "principal": os.path.join(pasta, "AnexoVIII_Convertido.json"),
        "indop": os.path.join(pasta, "IndOp_Descricoes.json"),
        "regras": os.path.join(pasta, "classificacao_tributaria.json"),
        "cnae": os.path.join(pasta, "lista_servicos_completa.json"),
    }
    if not os.path.exists(caminhos["principal"]):
        return None, pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    df_main = pd.DataFrame(_carregar_json(caminhos["principal"]))
    df_main["Item LC 116"] = df_main["Item LC 116"].map(normalizar_codigo_servico)
    df_main["cClassTrib"] = df_main["cClassTrib"].map(normalizar_classificacao)
    df_main["INDOP"] = df_main["INDOP"].fillna("").astype(str).str.strip()

    if os.path.exists(caminhos["indop"]):
        df_indop = pd.DataFrame(_carregar_json(caminhos["indop"]))
        df_indop["CODIGO"] = df_indop["CODIGO"].fillna("").astype(str).str.strip()
    else:
        df_indop = pd.DataFrame()

    if os.path.exists(caminhos["regras"]):
        df_regras = pd.DataFrame(_carregar_json(caminhos["regras"]))
        coluna_codigo = "Código da Classificação Tributária"
        if coluna_codigo not in df_regras.columns:
            raise ValidacaoFiscalError("A base tributária não possui a coluna de classificação.")
        df_regras["CHAVE"] = df_regras[coluna_codigo].map(normalizar_classificacao)
    else:
        df_regras = pd.DataFrame()

    if os.path.exists(caminhos["cnae"]):
        df_cnae_bruto = pd.DataFrame(_carregar_json(caminhos["cnae"]))
        df_cnae_bruto["cnae_numeros"] = df_cnae_bruto["cnae"].map(normalizar_cnae)
        df_cnae = pd.DataFrame(
            {
                "cnae_numeros_raw": df_cnae_bruto["cnae"].astype(str),
                "cnae_numeros": df_cnae_bruto["cnae_numeros"],
                "cnae": df_cnae_bruto["cnae_numeros"].map(formatar_cnae),
                "descricao_cnae": df_cnae_bruto["item_lista_servico"].fillna("").astype(str),
                "item_lista_servico": df_cnae_bruto["descricao_item"].map(normalizar_codigo_servico),
                "descricao_item": df_cnae_bruto["observacoes"].fillna("").astype(str),
            }
        )
        df_cnae = df_cnae[df_cnae["cnae_numeros"].str.len() == 7].drop_duplicates()
    else:
        df_cnae = pd.DataFrame()

    return df_main, df_indop, df_regras, df_cnae.reset_index(drop=True)


def validar_integridade_dados(
    df_main: pd.DataFrame,
    df_indop: pd.DataFrame,
    df_regras: pd.DataFrame,
    df_cnae: pd.DataFrame,
) -> dict[str, Any]:
    itens_main = set(df_main["Item LC 116"].dropna().astype(str))
    itens_cnae = set(df_cnae["item_lista_servico"].dropna().astype(str))
    regras = set(df_regras.get("CHAVE", pd.Series(dtype=str)).astype(str))
    indops = set(df_indop.get("CODIGO", pd.Series(dtype=str)).astype(str))
    return {
        "registros_nbs": len(df_main),
        "registros_cnae": len(df_cnae),
        "itens_lc_sem_correspondencia": sorted(itens_cnae - itens_main),
        "classificacoes_sem_regra": int((~df_main["cClassTrib"].isin(regras)).sum()),
        "indops_sem_tabela_auxiliar": int((~df_main["INDOP"].isin(indops)).sum()),
        "versao_dados": VERSAO_DADOS,
    }


def buscar_servicos(df: pd.DataFrame, termo: str) -> pd.DataFrame:
    if df.empty or not termo:
        return df.copy()
    procurado = _texto_sem_acentos(termo)
    colunas = ["Item LC 116", "NBS", "DESCRIÇÃO NBS", "Descrição Item", "nome cClassTrib"]
    mascara = pd.Series(False, index=df.index)
    for coluna in colunas:
        if coluna in df.columns:
            mascara |= df[coluna].fillna("").map(_texto_sem_acentos).str.contains(
                procurado, regex=False, na=False
            )
    return df[mascara]


def buscar_cnae(df_cnae: pd.DataFrame, termo: str) -> pd.DataFrame:
    if df_cnae.empty or not termo:
        return pd.DataFrame(columns=df_cnae.columns)
    procurado = _texto_sem_acentos(termo)
    digitos = re.sub(r"\D", "", termo)
    mascara = pd.Series(False, index=df_cnae.index)
    for coluna in ("cnae", "descricao_cnae", "item_lista_servico", "descricao_item"):
        mascara |= df_cnae[coluna].fillna("").map(_texto_sem_acentos).str.contains(
            procurado, regex=False, na=False
        )
    if digitos:
        mascara |= df_cnae["cnae_numeros"].str.contains(digitos, regex=False, na=False)
    return df_cnae[mascara].drop_duplicates().reset_index(drop=True)


def _numero_percentual(valor: Any, nome: str) -> float:
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError) as erro:
        raise ValidacaoFiscalError(f"{nome} deve ser numérico.") from erro
    if not 0 <= numero <= 100:
        raise ValidacaoFiscalError(f"{nome} deve estar entre 0% e 100%.")
    return numero


def calcular_comparativo(
    valor: float,
    iss: float,
    pis: float,
    cofins: float,
    ibs_ref: float,
    cbs_ref: float,
    codigo_tributacao: Any,
    df_regras: pd.DataFrame,
    *,
    ano: int = 2033,
    regime: str = "Não informado",
    credito_atual: float = 0,
    credito_novo: float = 0,
) -> dict[str, Any]:
    try:
        valor = float(valor)
    except (TypeError, ValueError) as erro:
        raise ValidacaoFiscalError("O valor do serviço deve ser numérico.") from erro
    if valor < 0:
        raise ValidacaoFiscalError("O valor do serviço não pode ser negativo.")

    iss = _numero_percentual(iss, "ISS")
    pis = _numero_percentual(pis, "PIS")
    cofins = _numero_percentual(cofins, "COFINS")
    ibs_ref = _numero_percentual(ibs_ref, "IBS")
    cbs_ref = _numero_percentual(cbs_ref, "CBS")
    credito_atual = _numero_percentual(credito_atual, "Crédito do sistema atual")
    credito_novo = _numero_percentual(credito_novo, "Crédito de IBS/CBS")
    if not 2026 <= int(ano) <= 2033:
        raise ValidacaoFiscalError("O ano do cenário deve estar entre 2026 e 2033.")

    chave = normalizar_classificacao(codigo_tributacao)
    reducao_ibs = reducao_cbs = 0.0
    descricao = "Regra não localizada — aplicada tributação sem redução"
    regra_localizada = False
    if not df_regras.empty and "CHAVE" in df_regras.columns:
        encontrada = df_regras[df_regras["CHAVE"] == chave]
        if not encontrada.empty:
            dados = encontrada.iloc[0]
            reducao_ibs = _numero_percentual(dados.get("Percentual Redução IBS", 0), "Redução IBS")
            reducao_cbs = _numero_percentual(dados.get("Percentual Redução CBS", 0), "Redução CBS")
            descricao = str(
                dados.get("Descrição do Código da Classificação Tributária", "Regra localizada")
            )
            regra_localizada = True

    aliquota_atual = iss + pis + cofins
    tributo_atual_bruto = valor * aliquota_atual / 100
    valor_credito_atual = tributo_atual_bruto * credito_atual / 100
    valor_atual = tributo_atual_bruto - valor_credito_atual

    ibs_efetivo = ibs_ref * (1 - reducao_ibs / 100)
    cbs_efetivo = cbs_ref * (1 - reducao_cbs / 100)
    aliquota_nova = ibs_efetivo + cbs_efetivo
    tributo_novo_bruto = valor * aliquota_nova / 100
    valor_credito_novo = tributo_novo_bruto * credito_novo / 100
    valor_novo = tributo_novo_bruto - valor_credito_novo

    observacao = (
        "2026 é ano de teste: a apuração possui regras de dispensa e compensação "
        "condicionadas ao cumprimento das obrigações acessórias."
        if int(ano) == 2026
        else "Cenário estimativo; as alíquotas de referência e regras devem ser confirmadas."
    )
    return {
        "ano": int(ano),
        "regime": regime,
        "codigo_tributacao": chave,
        "regra_localizada": regra_localizada,
        "descricao_regra": descricao,
        "valor_base": valor,
        "aliq_total_atual": aliquota_atual,
        "valor_atual_bruto": tributo_atual_bruto,
        "credito_atual_perc": credito_atual,
        "valor_credito_atual": valor_credito_atual,
        "valor_atual": valor_atual,
        "reducao_ibs": reducao_ibs,
        "reducao_cbs": reducao_cbs,
        "ibs_efetivo": ibs_efetivo,
        "cbs_efetivo": cbs_efetivo,
        "aliq_total_nova": aliquota_nova,
        "valor_novo_bruto": tributo_novo_bruto,
        "credito_novo_perc": credito_novo,
        "valor_credito_novo": valor_credito_novo,
        "valor_novo": valor_novo,
        "diferenca": valor_novo - valor_atual,
        "valor_ibs": valor * ibs_efetivo / 100,
        "valor_cbs": valor * cbs_efetivo / 100,
        "observacao": observacao,
    }


def validar_cnpj(cnpj_input: Any) -> bool:
    cnpj = re.sub(r"\D", "", str(cnpj_input or ""))
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    def digito(base: str, pesos: list[int]) -> str:
        soma = sum(int(numero) * peso for numero, peso in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    primeiro = digito(cnpj[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    segundo = digito(cnpj[:12] + primeiro, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return cnpj[-2:] == primeiro + segundo


@st.cache_data(ttl=3600, show_spinner=False)
def consultar_cnpj_api(cnpj_input: str) -> dict[str, Any]:
    cnpj = re.sub(r"\D", "", cnpj_input or "")
    if not validar_cnpj(cnpj):
        return {"erro": "CNPJ inválido. Confira os 14 dígitos e os verificadores."}

    fontes = [
        (f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", "BrasilAPI v1"),
        (f"https://brasilapi.com.br/api/cnpj/v2/{cnpj}", "BrasilAPI v2"),
        (f"https://minhareceita.org/{cnpj}", "Minha Receita"),
        (f"https://www.receitaws.com.br/v1/cnpj/{cnpj}", "ReceitaWS"),
    ]
    ultimo_erro = "Serviços indisponíveis."
    cabecalhos = {"Accept": "application/json", "User-Agent": "Auditoria-NBS/2.0"}
    for url, nome in fontes:
        try:
            resposta = requests.get(url, timeout=(3.05, 6), headers=cabecalhos)
            if resposta.status_code == 200:
                dados = resposta.json()
                if not isinstance(dados, dict):
                    ultimo_erro = f"Resposta inesperada de {nome}."
                    continue
                if nome == "ReceitaWS" and dados.get("status") == "ERROR":
                    ultimo_erro = str(dados.get("message", "Erro na ReceitaWS"))
                    continue
                dados["fonte_dados"] = nome
                dados.setdefault("cnpj", cnpj)
                return dados
            if resposta.status_code == 404:
                ultimo_erro = "CNPJ não encontrado."
            elif resposta.status_code == 429:
                ultimo_erro = f"Limite temporário atingido em {nome}."
            else:
                ultimo_erro = f"{nome} respondeu com status {resposta.status_code}."
        except (requests.RequestException, ValueError) as erro:
            ultimo_erro = f"Falha ao consultar {nome}: {erro.__class__.__name__}."
    return {"erro": f"Não foi possível consultar o CNPJ. {ultimo_erro}"}


def extrair_cnaes_empresa(dados_empresa: dict[str, Any]) -> list[str]:
    encontrados: list[str] = []

    def adicionar(valor: Any) -> None:
        codigo = normalizar_cnae(valor)
        if codigo and codigo not in encontrados:
            encontrados.append(codigo)

    if dados_empresa.get("cnae_fiscal"):
        adicionar(dados_empresa["cnae_fiscal"])
    principal = dados_empresa.get("cnae_fiscal_principal")
    if isinstance(principal, dict):
        adicionar(principal.get("codigo") or principal.get("code"))
    atividades = dados_empresa.get("atividade_principal") or []
    if isinstance(atividades, list):
        for atividade in atividades:
            if isinstance(atividade, dict):
                adicionar(atividade.get("codigo") or atividade.get("code"))

    secundarias = dados_empresa.get("cnaes_secundarios") or dados_empresa.get("atividades_secundarias") or []
    if isinstance(secundarias, list):
        for atividade in secundarias:
            if isinstance(atividade, dict):
                adicionar(
                    atividade.get("codigo")
                    or atividade.get("cnae_fiscal")
                    or atividade.get("code")
                )
    return encontrados


COLUNAS_RELATORIO = [
    "CNAE",
    "Descrição CNAE",
    "Item LC 116",
    "Descrição LC 116",
    "NBS",
    "Descrição NBS",
    "cClassTrib",
    "Classificação Tributária",
    "Redução IBS (%)",
    "Redução CBS (%)",
    "Tipo de Alíquota",
    "Fundamento legal",
    "INDOP",
    "Detalhamento INDOP",
    "Status do vínculo",
]

COLUNAS_RESUMO = [
    "CNAE",
    "Descrição CNAE",
    "Item LC 116",
    "Descrição LC 116",
    "NBS",
    "Descrição NBS",
    "cClassTrib",
    "Classificação Tributária",
    "Redução IBS (%)",
    "Redução CBS (%)",
    "Tipo de Alíquota",
    "Fundamento legal",
    "Quantidade INDOP",
    "Opções INDOP",
    "Detalhamentos INDOP",
    "Status do vínculo",
]


def gerar_combinacoes_cnae_nbs(
    codigos_cnae: Iterable[Any],
    df_cnae: pd.DataFrame,
    df_main: pd.DataFrame,
    df_indop: pd.DataFrame,
    df_regras: pd.DataFrame | None = None,
) -> pd.DataFrame:
    codigos = {normalizar_cnae(codigo) for codigo in codigos_cnae if normalizar_cnae(codigo)}
    if not codigos or df_cnae.empty:
        return pd.DataFrame(columns=COLUNAS_RELATORIO)

    vinculos = df_cnae[df_cnae["cnae_numeros"].isin(codigos)].copy()
    if vinculos.empty:
        return pd.DataFrame(columns=COLUNAS_RELATORIO)

    principal = df_main.copy()
    colunas_regra = {
        "CHAVE": "cClassTrib",
        "Percentual Redução IBS": "Redução IBS (%)",
        "Percentual Redução CBS": "Redução CBS (%)",
        "Tipo de Alíquota": "Tipo de Alíquota",
        "Url da Legislação": "Fundamento legal",
    }
    if df_regras is not None and not df_regras.empty:
        disponiveis = [coluna for coluna in colunas_regra if coluna in df_regras.columns]
        regras = (
            df_regras[disponiveis]
            .drop_duplicates("CHAVE")
            .rename(columns=colunas_regra)
        )
        principal = principal.merge(regras, on="cClassTrib", how="left")
    for coluna, padrao in {
        "Redução IBS (%)": 0.0,
        "Redução CBS (%)": 0.0,
        "Tipo de Alíquota": "Não informada",
        "Fundamento legal": FONTE_LC_214,
    }.items():
        if coluna not in principal.columns:
            principal[coluna] = padrao
        principal[coluna] = principal[coluna].fillna(padrao)
    for coluna in ("Redução IBS (%)", "Redução CBS (%)"):
        principal[coluna] = pd.to_numeric(principal[coluna], errors="coerce").fillna(0.0)
    if not df_indop.empty:
        colunas_indop = [
            coluna
            for coluna in ["CODIGO", "LOCAL_OPERACAO", "DESCRICAO", "LOCAL_DFE", "BASE_LEGAL"]
            if coluna in df_indop.columns
        ]
        locais = df_indop[colunas_indop].drop_duplicates("CODIGO")
        principal = principal.merge(locais, left_on="INDOP", right_on="CODIGO", how="left")
    else:
        principal["LOCAL_OPERACAO"] = ""
        principal["DESCRICAO"] = ""
        principal["LOCAL_DFE"] = ""
        principal["BASE_LEGAL"] = ""
    local_base = principal.get("Local incidência IBS", pd.Series("", index=principal.index))
    principal["LOCAL_FINAL"] = principal["LOCAL_OPERACAO"].fillna("")
    principal.loc[principal["LOCAL_FINAL"].eq(""), "LOCAL_FINAL"] = local_base.fillna("")

    def detalhar_indop(linha: pd.Series) -> str:
        descricao = str(linha.get("DESCRICAO", "") or "").strip()
        referencia_dfe = str(linha.get("LOCAL_DFE", "") or "").strip()
        base_legal = str(linha.get("BASE_LEGAL", "") or "").strip()
        local = str(linha.get("LOCAL_FINAL", "") or "").strip()
        partes = []
        if descricao:
            partes.append(descricao)
        if referencia_dfe:
            partes.append(f"Referência no DFe: {referencia_dfe}")
        if base_legal:
            partes.append(f"Base legal: {base_legal}")
        if not partes and local:
            partes.append(f"Local de incidência: {local}")
        return " | ".join(partes) or "Não detalhado na base atual"

    principal["DETALHE_INDOP"] = principal.apply(detalhar_indop, axis=1)

    combinado = vinculos.merge(
        principal,
        left_on="item_lista_servico",
        right_on="Item LC 116",
        how="left",
        suffixes=("_cnae", "_nbs"),
    )
    possui_nbs = combinado["NBS"].fillna("").astype(str).str.strip().ne("")
    resultado = pd.DataFrame(
        {
            "CNAE": combinado["cnae"],
            "Descrição CNAE": combinado["descricao_cnae"],
            "Item LC 116": combinado["item_lista_servico"],
            "Descrição LC 116": combinado["descricao_item"],
            "NBS": combinado["NBS"].fillna("Não localizada"),
            "Descrição NBS": combinado["DESCRIÇÃO NBS"].fillna(""),
            "cClassTrib": combinado["cClassTrib"].fillna(""),
            "Classificação Tributária": combinado["nome cClassTrib"].fillna(""),
            "Redução IBS (%)": combinado["Redução IBS (%)"].fillna(0.0),
            "Redução CBS (%)": combinado["Redução CBS (%)"].fillna(0.0),
            "Tipo de Alíquota": combinado["Tipo de Alíquota"].fillna("Não informada"),
            "Fundamento legal": combinado["Fundamento legal"].fillna(FONTE_LC_214),
            "INDOP": combinado["INDOP"].fillna(""),
            "Detalhamento INDOP": combinado["DETALHE_INDOP"].fillna(""),
            "Status do vínculo": possui_nbs.map(
                {True: "NBS candidata localizada", False: "Sem NBS na base atual"}
            ),
        }
    )
    return resultado.drop_duplicates().sort_values(
        ["CNAE", "Item LC 116", "NBS"], kind="stable"
    ).reset_index(drop=True)


def buscar_codigos_servico(df_cnae: pd.DataFrame, termo: str) -> pd.DataFrame:
    """Busca itens da LC 116 por código ou descrição, sem duplicar CNAEs."""

    colunas = ["item_lista_servico", "descricao_item"]
    if df_cnae.empty or not termo:
        return pd.DataFrame(columns=colunas)
    procurado = _texto_sem_acentos(termo)
    codigo = normalizar_codigo_servico(termo) if re.search(r"\d", termo) else ""
    mascara = pd.Series(False, index=df_cnae.index)
    for coluna in ("item_lista_servico", "descricao_item"):
        mascara |= df_cnae[coluna].fillna("").map(_texto_sem_acentos).str.contains(
            procurado, regex=False, na=False
        )
    if codigo:
        mascara |= df_cnae["item_lista_servico"].eq(codigo)
    return (
        df_cnae.loc[mascara, colunas]
        .drop_duplicates()
        .sort_values("item_lista_servico", kind="stable")
        .reset_index(drop=True)
    )


def gerar_combinacoes_codigo_servico(
    codigos_servico: Iterable[Any],
    df_cnae: pd.DataFrame,
    df_main: pd.DataFrame,
    df_indop: pd.DataFrame,
    df_regras: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Faz o caminho inverso LC 116 -> CNAE -> NBS e regras tributárias."""

    codigos = {
        normalizar_codigo_servico(codigo)
        for codigo in codigos_servico
        if normalizar_codigo_servico(codigo)
    }
    if not codigos or df_cnae.empty:
        return pd.DataFrame(columns=COLUNAS_RELATORIO)
    vinculos = df_cnae[df_cnae["item_lista_servico"].isin(codigos)]
    resultado = gerar_combinacoes_cnae_nbs(
        vinculos["cnae_numeros"].unique(), df_cnae, df_main, df_indop, df_regras
    )
    return resultado[resultado["Item LC 116"].isin(codigos)].reset_index(drop=True)


def obter_regra_tributaria(codigo: Any, df_regras: pd.DataFrame) -> dict[str, Any]:
    """Retorna os percentuais e metadados legais de uma cClassTrib."""

    chave = normalizar_classificacao(codigo)
    if df_regras.empty or "CHAVE" not in df_regras.columns:
        return {
            "codigo": chave,
            "localizada": False,
            "reducao_ibs": 0.0,
            "reducao_cbs": 0.0,
            "tipo_aliquota": "Não informada",
            "numero_anexo": "Não informado",
            "descricao": "Regra não localizada na base atual.",
            "fundamento_legal": FONTE_LC_214,
        }
    encontrada = df_regras[df_regras["CHAVE"].eq(chave)]
    if encontrada.empty:
        return obter_regra_tributaria(chave, pd.DataFrame())
    linha = encontrada.iloc[0]
    return {
        "codigo": chave,
        "localizada": True,
        "reducao_ibs": _numero_percentual(linha.get("Percentual Redução IBS", 0), "Redução IBS"),
        "reducao_cbs": _numero_percentual(linha.get("Percentual Redução CBS", 0), "Redução CBS"),
        "tipo_aliquota": str(linha.get("Tipo de Alíquota", "Não informada") or "Não informada"),
        "numero_anexo": str(linha.get("Número do Anexo", "") or "Não informado"),
        "descricao": str(
            linha.get("Descrição do Código da Classificação Tributária", "Regra localizada")
        ),
        "fundamento_legal": str(linha.get("Url da Legislação", FONTE_LC_214) or FONTE_LC_214).strip('"\r\n '),
    }


SETORES_SERVICO = {
    "Tecnologia, informação e comunicação": {
        "divisoes": set(range(58, 64)),
        "foco": "software, licenciamento, suporte, telecomunicações e serviços digitais",
        "recomendacoes": [
            "Separar contratos de desenvolvimento, licenciamento, suporte, hospedagem e cessão de direitos.",
            "Confirmar a NBS pela entrega efetiva e pelo grau de customização, não apenas pelo CNAE cadastral.",
            "Revisar o domicílio do adquirente e o INDOP para determinar o local de incidência.",
            "Em segurança da informação ou cibernética, conferir NBS e requisitos societários da legislação vigente.",
        ],
    },
    "Serviços profissionais, científicos e técnicos": {
        "divisoes": set(range(69, 76)),
        "foco": "jurídico, contábil, engenharia, arquitetura, consultoria e atividades técnicas",
        "recomendacoes": [
            "Verificar se a atividade é exercida por profissão fiscalizada por conselho e se a forma societária cumpre os requisitos legais.",
            "Testar a hipótese de redução de 30% somente após validar atividade, profissionais e contrato.",
            "Segregar serviços intelectuais de intermediação, administração e atividades acessórias.",
            "Documentar escopo, responsável técnico, conselho profissional e NBS em cada linha de serviço.",
        ],
    },
    "Educação": {
        "divisoes": {85},
        "foco": "ensino, treinamento e atividades educacionais",
        "recomendacoes": [
            "Confrontar o serviço com as NBS do Anexo II da LC 214 antes de aplicar redução.",
            "Separar mensalidades e cursos das receitas acessórias, materiais, alimentação e locações.",
            "Revisar bolsas, descontos, cancelamentos e momento de reconhecimento da contraprestação.",
            "Manter evidência da modalidade, público, carga horária e natureza do serviço prestado.",
        ],
    },
    "Saúde e assistência social": {
        "divisoes": {86, 87, 88},
        "foco": "atendimento de saúde, diagnóstico, cuidados e assistência social",
        "recomendacoes": [
            "Confrontar cada procedimento com as NBS do Anexo III da LC 214 e distinguir serviço de saúde de atividade acessória.",
            "Separar atendimento direto, intermediação e planos de assistência, pois os regimes e créditos podem divergir.",
            "Reconciliar glosas, repasses, materiais, medicamentos e honorários com os documentos fiscais.",
            "Validar redução, alíquota zero e restrições de crédito pela operação concreta.",
        ],
    },
    "Transporte, armazenagem e logística": {
        "divisoes": set(range(49, 54)),
        "foco": "transporte de passageiros e cargas, armazenagem, correios e entregas",
        "recomendacoes": [
            "Identificar modal, origem, destino, percurso e natureza municipal, intermunicipal ou internacional.",
            "Separar frete, armazenagem, manuseio, agenciamento, pedágio e serviços acessórios.",
            "Revisar o INDOP e o documento fiscal aplicável antes de definir o local de incidência.",
            "Conferir regimes específicos e regras de crédito conforme o tipo de transporte.",
        ],
    },
    "Serviços financeiros, seguros e planos": {
        "divisoes": {64, 65, 66},
        "foco": "intermediação financeira, seguros, previdência e planos",
        "recomendacoes": [
            "Mapear receitas por produto, tarifa, comissão, spread, prêmio e contraprestação.",
            "Não aplicar automaticamente a alíquota padrão: validar o regime específico e a base de cálculo.",
            "Revisar deduções, estornos, repasses e restrições de crédito de cada operação.",
            "Conciliar cClassTrib, documento fiscal e obrigações do regime uniforme setorial.",
        ],
    },
    "Construção e serviços imobiliários": {
        "divisoes": {41, 42, 43, 68},
        "foco": "obras, instalações, incorporação, locação e administração de imóveis",
        "recomendacoes": [
            "Separar obra, projeto, administração, manutenção, incorporação e locação.",
            "Identificar materiais fornecidos, subcontratações e o imóvel vinculado à operação.",
            "Revisar o local do imóvel como elemento de incidência e a documentação por empreendimento.",
            "Avaliar o regime específico imobiliário e controles de custo, aquisição e créditos.",
        ],
    },
    "Hospedagem e alimentação": {
        "divisoes": {55, 56},
        "foco": "hotéis, hospedagem, restaurantes, bares e alimentação",
        "recomendacoes": [
            "Segregar hospedagem, alimentação, eventos, estacionamento, taxas e outras comodidades.",
            "Revisar gorjetas, taxas de serviço, cancelamentos e valores repassados a terceiros.",
            "Confirmar o tratamento das vendas combinadas e dos insumos usados em cada linha de receita.",
            "Conferir cClassTrib e local de incidência conforme a prestação efetiva.",
        ],
    },
    "Artes, cultura, esportes e recreação": {
        "divisoes": {90, 91, 92, 93},
        "foco": "produção cultural, jornalística, audiovisual, eventos e atividades desportivas",
        "recomendacoes": [
            "Conferir se a produção ou atividade e a NBS constam dos anexos legais aplicáveis.",
            "Separar produção, cessão de direitos, patrocínio, publicidade, bilheteria e intermediação.",
            "Validar requisitos de produção nacional e a natureza do beneficiário quando exigidos.",
            "Manter contratos e memórias que sustentem a classificação de cada receita.",
        ],
    },
    "Serviços administrativos, locação e apoio": {
        "divisoes": set(range(77, 83)),
        "foco": "locação, seleção, turismo, vigilância, limpeza e apoio empresarial",
        "recomendacoes": [
            "Distinguir locação de bens, cessão de mão de obra, intermediação e serviço executado.",
            "Revisar reembolsos, despesas por conta e ordem, comissões e repasses contratuais.",
            "Validar o local de incidência pela natureza real do serviço e pelo INDOP.",
            "Documentar tomador, local da execução, ativos envolvidos e critérios de formação do preço.",
        ],
    },
    "Outros serviços e serviços pessoais": {
        "divisoes": {94, 95, 96},
        "foco": "associações, reparos, cuidados pessoais, funerários e demais serviços",
        "recomendacoes": [
            "Detalhar a entrega efetiva, pois CNAEs amplos podem levar a itens LC 116 e NBS diferentes.",
            "Separar mensalidades associativas, serviços individualizados, venda de bens e intermediação.",
            "Em atividades funerárias e planos, verificar se há regime ou redução específica.",
            "Revisar contratos, cadastro de itens e descrição do documento fiscal antes da migração.",
        ],
    },
}

_setor_outros = "Outros serviços e serviços pessoais"
_divisoes_especificas = set().union(
    *(
        dados["divisoes"]
        for nome, dados in SETORES_SERVICO.items()
        if nome != _setor_outros
    )
)
SETORES_SERVICO[_setor_outros]["divisoes"] = set(range(1, 100)) - _divisoes_especificas


def identificar_setor_cnae(codigo: Any) -> str:
    digitos = normalizar_cnae(codigo)
    divisao = int(digitos[:2]) if len(digitos) >= 2 else -1
    for nome, dados in SETORES_SERVICO.items():
        if divisao in dados["divisoes"]:
            return nome
    return "Outros serviços e serviços pessoais"


def diagnostico_setor(
    setor: str,
    df_cnae: pd.DataFrame,
    df_main: pd.DataFrame,
    df_regras: pd.DataFrame,
) -> dict[str, Any]:
    """Resume cobertura e pontos de revisão para um setor de serviços."""

    if setor not in SETORES_SERVICO:
        raise ValidacaoFiscalError("Setor de serviço não reconhecido.")
    divisoes = SETORES_SERVICO[setor]["divisoes"]
    mascara = df_cnae["cnae_numeros"].str[:2].map(
        lambda valor: int(valor) if str(valor).isdigit() else -1
    ).isin(divisoes)
    vinculos = df_cnae[mascara].copy()
    itens = set(vinculos["item_lista_servico"])
    servicos = df_main[df_main["Item LC 116"].isin(itens)].copy()
    regras_reducao = df_regras.copy()
    if not regras_reducao.empty:
        ibs = pd.to_numeric(regras_reducao["Percentual Redução IBS"], errors="coerce").fillna(0)
        cbs = pd.to_numeric(regras_reducao["Percentual Redução CBS"], errors="coerce").fillna(0)
        codigos_reducao = set(regras_reducao.loc[(ibs > 0) | (cbs > 0), "CHAVE"])
    else:
        codigos_reducao = set()
    candidatos_reducao = servicos[servicos["cClassTrib"].isin(codigos_reducao)]
    return {
        "setor": setor,
        "foco": SETORES_SERVICO[setor]["foco"],
        "recomendacoes": list(SETORES_SERVICO[setor]["recomendacoes"]),
        "cnaes": vinculos["cnae_numeros"].nunique(),
        "itens_lc": vinculos["item_lista_servico"].nunique(),
        "nbs": servicos["NBS"].nunique(),
        "candidatos_reducao": candidatos_reducao[
            ["Item LC 116", "NBS", "DESCRIÇÃO NBS", "cClassTrib", "nome cClassTrib"]
        ].drop_duplicates().reset_index(drop=True),
    }


def resumir_combinacoes(df_dados: pd.DataFrame) -> pd.DataFrame:
    """Agrupa opções INDOP repetidas sem perder o detalhamento para exportação."""

    if df_dados.empty:
        return pd.DataFrame(columns=COLUNAS_RESUMO)
    agrupadores = [
        "CNAE",
        "Descrição CNAE",
        "Item LC 116",
        "Descrição LC 116",
        "NBS",
        "Descrição NBS",
        "cClassTrib",
        "Classificação Tributária",
        "Redução IBS (%)",
        "Redução CBS (%)",
        "Tipo de Alíquota",
        "Fundamento legal",
        "Status do vínculo",
    ]

    def unir_unicos(valores: pd.Series) -> str:
        unicos = sorted({str(valor).strip() for valor in valores if str(valor).strip()})
        return ", ".join(unicos)

    resumo = (
        df_dados.groupby(agrupadores, dropna=False, sort=False)
        .agg(
            **{
                "Quantidade INDOP": ("INDOP", lambda valores: valores.astype(str).replace("", pd.NA).nunique()),
                "Opções INDOP": ("INDOP", unir_unicos),
                "Detalhamentos INDOP": ("Detalhamento INDOP", unir_unicos),
            }
        )
        .reset_index()
    )
    return resumo.reindex(columns=COLUNAS_RESUMO)


def filtrar_combinacoes(
    df_dados: pd.DataFrame,
    termo: str = "",
    classificacoes: Iterable[str] | None = None,
) -> pd.DataFrame:
    if df_dados.empty:
        return df_dados.copy()
    resultado = df_dados.copy()
    if termo:
        procurado = _texto_sem_acentos(termo)
        mascara = pd.Series(False, index=resultado.index)
        for coluna in resultado.columns:
            mascara |= resultado[coluna].fillna("").map(_texto_sem_acentos).str.contains(
                procurado, regex=False, na=False
            )
        resultado = resultado[mascara]
    if classificacoes:
        resultado = resultado[resultado["Classificação Tributária"].isin(classificacoes)]
    return resultado.reset_index(drop=True)


def _pdf_texto(valor: Any) -> str:
    return str(valor if valor is not None else "").encode("latin-1", "replace").decode("latin-1")


class PDFReport(FPDF):
    def header(self):
        self.set_fill_color(20, 67, 114)
        self.rect(0, 0, self.w, 25, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.set_y(8)
        self.cell(0, 8, _pdf_texto("Simulação Tributária — IBS e CBS"), align="C")
        self.set_text_color(34, 34, 34)
        self.ln(14)

    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "I", 7)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, _pdf_texto(f"Página {self.page_no()} | Gerado em {datetime.now():%d/%m/%Y %H:%M}"), align="C")


def _pdf_secao(pdf: FPDF, titulo: str) -> None:
    pdf.set_fill_color(225, 235, 247)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _pdf_texto(titulo), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)


def gerar_relatorio_pdf(
    dados_empresa: dict[str, Any] | None,
    dados_simulacao: dict[str, Any],
    dados_servico: pd.Series | dict[str, Any],
) -> bytes:
    pdf = PDFReport()
    pdf.set_auto_page_break(True, 18)
    pdf.add_page()
    pdf.set_font("Helvetica", size=9)

    _pdf_secao(pdf, "1. Identificação")
    empresa = dados_empresa or {}
    razao = empresa.get("razao_social") or empresa.get("nome") or "Simulação avulsa"
    pdf.multi_cell(0, 5, _pdf_texto(f"Empresa: {razao}\nCNPJ: {empresa.get('cnpj', '-') or '-'}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    _pdf_secao(pdf, "2. Serviço e classificação candidata")
    texto_servico = (
        f"Item LC 116: {dados_servico.get('Item LC 116', '-')}\n"
        f"NBS: {dados_servico.get('NBS', '-')}\n"
        f"Descrição: {dados_servico.get('DESCRIÇÃO NBS', '-')}\n"
        f"cClassTrib: {dados_servico.get('cClassTrib', '-')}"
    )
    pdf.multi_cell(0, 5, _pdf_texto(texto_servico), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    _pdf_secao(pdf, "3. Comparativo do cenário")
    pdf.set_font("Helvetica", "B", 8)
    larguras = [55, 42, 42, 42]
    for largura, titulo in zip(larguras, ["Cenário", "Alíquota", "Créditos", "Valor líquido"]):
        pdf.cell(largura, 8, _pdf_texto(titulo), border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", size=8)
    linhas = [
        ("Sistema atual", dados_simulacao["aliq_total_atual"], dados_simulacao["valor_credito_atual"], dados_simulacao["valor_atual"]),
        ("IBS/CBS", dados_simulacao["aliq_total_nova"], dados_simulacao["valor_credito_novo"], dados_simulacao["valor_novo"]),
    ]
    for nome, aliquota, credito, valor in linhas:
        valores = [nome, f"{aliquota:.2f}%", f"R$ {credito:,.2f}", f"R$ {valor:,.2f}"]
        for largura, conteudo in zip(larguras, valores):
            pdf.cell(largura, 8, _pdf_texto(conteudo), border=1, align="C")
        pdf.ln()
    pdf.ln(4)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(
        0,
        5,
        _pdf_texto(
            f"Redução aplicada: IBS {dados_simulacao['reducao_ibs']:.2f}% e "
            f"CBS {dados_simulacao['reducao_cbs']:.2f}%. Alíquotas efetivas: "
            f"IBS {dados_simulacao['ibs_efetivo']:.2f}% e CBS {dados_simulacao['cbs_efetivo']:.2f}%."
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.multi_cell(0, 5, _pdf_texto(dados_simulacao["observacao"]), new_x="LMARGIN", new_y="NEXT")
    pdf.multi_cell(0, 5, _pdf_texto(AVISO_CLASSIFICACAO), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


class PDFLandscape(FPDF):
    def header(self):
        self.set_fill_color(20, 67, 114)
        self.rect(0, 0, self.w, 22, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 12)
        self.set_y(7)
        self.cell(0, 7, _pdf_texto("Relatório de Candidatos CNAE, LC 116 e NBS"), align="C")
        self.set_text_color(30, 30, 30)
        self.ln(12)

    def footer(self):
        self.set_y(-11)
        self.set_font("Helvetica", "I", 6)
        self.cell(0, 5, _pdf_texto(f"Página {self.page_no()} | Resultado indicativo"), align="C")


def gerar_pdf_paisagem(dados_empresa: dict[str, Any], df_dados: pd.DataFrame) -> bytes:
    pdf = PDFLandscape(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(True, 14)
    pdf.add_page()
    pdf.set_font("Helvetica", size=7)
    razao = dados_empresa.get("razao_social") or dados_empresa.get("nome") or "Consulta manual"
    pdf.multi_cell(
        0,
        4,
        _pdf_texto(
            f"Empresa/consulta: {razao} | CNPJ: {dados_empresa.get('cnpj', '-') or '-'} | "
            f"Fonte CNPJ: {dados_empresa.get('fonte_dados', 'consulta manual')}\n{AVISO_CLASSIFICACAO}"
        ),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(2)

    if "Quantidade INDOP" in df_dados.columns:
        colunas = [
            "CNAE",
            "Item LC 116",
            "NBS",
            "Descrição NBS",
            "cClassTrib",
            "Redução IBS (%)",
            "Redução CBS (%)",
            "Quantidade INDOP",
            "Opções INDOP",
        ]
        larguras = [20, 18, 23, 80, 22, 18, 18, 25, 53]
    else:
        colunas = [
            "CNAE",
            "Item LC 116",
            "NBS",
            "Descrição NBS",
            "cClassTrib",
            "Redução IBS (%)",
            "Redução CBS (%)",
            "Detalhamento INDOP",
        ]
        # 277 mm: largura útil exata de uma página A4 paisagem com margens de 10 mm.
        larguras = [20, 18, 23, 85, 22, 18, 18, 73]

    def cabecalho_tabela() -> None:
        pdf.set_fill_color(225, 235, 247)
        pdf.set_font("Helvetica", "B", 7)
        for largura, coluna in zip(larguras, colunas):
            pdf.cell(largura, 7, _pdf_texto(coluna), border=1, align="C", fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", size=6.5)

    cabecalho_tabela()
    for _, linha in df_dados.iterrows():
        if pdf.get_y() > 190:
            pdf.add_page()
            cabecalho_tabela()
        valores = []
        for coluna in colunas:
            valor = str(linha.get(coluna, ""))
            limite = 120 if coluna in {"Descrição NBS", "Detalhamento INDOP"} else 55
            valores.append(valor[:limite])
        for largura, valor in zip(larguras, valores):
            pdf.cell(largura, 6, _pdf_texto(valor), border=1)
        pdf.ln()
    return bytes(pdf.output())


def _seguro_excel(valor: Any) -> Any:
    if isinstance(valor, (dict, list, tuple, set)):
        valor = json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, str) and valor.startswith(("=", "+", "-", "@")):
        return "'" + valor
    return valor


def _preparar_dataframe_excel(df: pd.DataFrame) -> pd.DataFrame:
    return df.map(_seguro_excel)


def _primeiro_valor(dados: dict[str, Any], *chaves: str) -> Any:
    for chave in chaves:
        valor = dados.get(chave)
        if valor not in (None, "", [], {}):
            return valor
    return ""


def _formatar_data_empresa(valor: Any) -> str:
    if not valor:
        return ""
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(texto[:19], formato).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return texto


def _formatar_sim_nao(valor: Any) -> str:
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    texto = str(valor or "").strip()
    if texto.casefold() in {"true", "sim", "s", "1"}:
        return "Sim"
    if texto.casefold() in {"false", "nao", "não", "n", "0"}:
        return "Não"
    return texto


def preparar_dados_empresa(dados: dict[str, Any]) -> pd.DataFrame:
    """Converte respostas heterogêneas das APIs em uma ficha cadastral legível."""

    linhas: list[tuple[str, str, Any]] = []

    def adicionar(secao: str, campo: str, valor: Any) -> None:
        if valor not in (None, "", [], {}):
            linhas.append((secao, campo, _seguro_excel(valor)))

    adicionar("Identificação", "Razão social", _primeiro_valor(dados, "razao_social", "nome"))
    adicionar("Identificação", "Nome fantasia", _primeiro_valor(dados, "nome_fantasia", "fantasia"))
    adicionar("Identificação", "CNPJ", formatar_cnpj(dados.get("cnpj")))
    adicionar("Identificação", "Fonte da consulta", dados.get("fonte_dados"))
    adicionar("Situação cadastral", "Situação", _primeiro_valor(dados, "descricao_situacao_cadastral", "situacao"))
    adicionar(
        "Situação cadastral",
        "Data da situação",
        _formatar_data_empresa(_primeiro_valor(dados, "data_situacao_cadastral", "data_situacao")),
    )
    adicionar("Situação cadastral", "Motivo", _primeiro_valor(dados, "descricao_motivo_situacao_cadastral", "motivo_situacao"))
    adicionar(
        "Situação cadastral",
        "Início da atividade",
        _formatar_data_empresa(_primeiro_valor(dados, "data_inicio_atividade", "abertura")),
    )
    adicionar("Situação cadastral", "Natureza jurídica", dados.get("natureza_juridica"))
    adicionar("Situação cadastral", "Porte", _primeiro_valor(dados, "descricao_porte", "porte"))

    capital = dados.get("capital_social")
    if isinstance(capital, (int, float)):
        capital = f"R$ {capital:,.2f}"
    adicionar("Situação cadastral", "Capital social", capital)

    simples = dados.get("simples") if isinstance(dados.get("simples"), dict) else {}
    opcao_simples = _primeiro_valor(dados, "opcao_pelo_simples")
    if opcao_simples == "":
        opcao_simples = simples.get("optante")
    adicionar("Situação cadastral", "Optante pelo Simples", _formatar_sim_nao(opcao_simples))
    adicionar(
        "Situação cadastral",
        "Data de opção pelo Simples",
        _formatar_data_empresa(_primeiro_valor(dados, "data_opcao_pelo_simples") or simples.get("data_opcao")),
    )

    logradouro = _primeiro_valor(dados, "logradouro")
    numero = _primeiro_valor(dados, "numero")
    complemento = _primeiro_valor(dados, "complemento")
    endereco = ", ".join(str(parte) for parte in (logradouro, numero, complemento) if parte)
    adicionar("Endereço", "Logradouro", endereco)
    adicionar("Endereço", "Bairro", dados.get("bairro"))
    adicionar("Endereço", "Município", dados.get("municipio"))
    adicionar("Endereço", "UF", dados.get("uf"))
    adicionar("Endereço", "CEP", dados.get("cep"))
    adicionar("Contato", "Telefone", _primeiro_valor(dados, "ddd_telefone_1", "telefone"))
    adicionar("Contato", "Telefone adicional", dados.get("ddd_telefone_2"))
    adicionar("Contato", "E-mail", dados.get("email"))

    principal_codigo = dados.get("cnae_fiscal")
    principal_descricao = dados.get("cnae_fiscal_descricao")
    principal_objeto = dados.get("cnae_fiscal_principal")
    if isinstance(principal_objeto, dict):
        principal_codigo = principal_codigo or principal_objeto.get("codigo") or principal_objeto.get("code")
        principal_descricao = principal_descricao or principal_objeto.get("descricao") or principal_objeto.get("text")
    atividades_principais = dados.get("atividade_principal") or []
    if isinstance(atividades_principais, list) and atividades_principais:
        atividade = atividades_principais[0]
        if isinstance(atividade, dict):
            principal_codigo = principal_codigo or atividade.get("codigo") or atividade.get("code")
            principal_descricao = principal_descricao or atividade.get("descricao") or atividade.get("text")
    if principal_codigo:
        texto_principal = formatar_cnae(principal_codigo)
        if principal_descricao:
            texto_principal += f" — {principal_descricao}"
        adicionar("Atividades econômicas", "CNAE principal", texto_principal)

    secundarias = dados.get("cnaes_secundarios") or dados.get("atividades_secundarias") or []
    if isinstance(secundarias, list):
        for indice, atividade in enumerate(secundarias, start=1):
            if not isinstance(atividade, dict):
                continue
            codigo = atividade.get("codigo") or atividade.get("cnae_fiscal") or atividade.get("code")
            descricao = atividade.get("descricao") or atividade.get("text")
            if codigo:
                texto = formatar_cnae(codigo)
                if descricao:
                    texto += f" — {descricao}"
                adicionar("Atividades econômicas", f"CNAE secundário {indice}", texto)

    socios = dados.get("qsa") or []
    if isinstance(socios, list):
        for indice, socio in enumerate(socios, start=1):
            if not isinstance(socio, dict):
                continue
            nome = socio.get("nome_socio") or socio.get("nome")
            qualificacao = socio.get("qualificacao_socio") or socio.get("qual")
            texto = " — ".join(str(parte) for parte in (nome, qualificacao) if parte)
            adicionar("Quadro societário", f"Integrante {indice}", texto)

    return pd.DataFrame(linhas, columns=["Seção", "Campo", "Informação"])


def _formatar_planilha(writer: pd.ExcelWriter, nome: str, df: pd.DataFrame, larguras: dict[str, int]) -> None:
    workbook = writer.book
    worksheet = writer.sheets[nome]
    formato_cabecalho = workbook.add_format(
        {"bold": True, "font_color": "white", "bg_color": "#144372", "border": 1, "align": "center", "valign": "vcenter"}
    )
    formato_texto = workbook.add_format({"valign": "top", "text_wrap": True, "border": 1, "border_color": "#D9E2F3"})
    formato_alternado = workbook.add_format({"bg_color": "#F4F7FB", "valign": "top", "text_wrap": True})
    worksheet.set_row(0, 30, formato_cabecalho)
    for indice, coluna in enumerate(df.columns):
        worksheet.write(0, indice, coluna, formato_cabecalho)
        worksheet.set_column(indice, indice, larguras.get(coluna, 18), formato_texto)
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))
    if len(df):
        worksheet.conditional_format(1, 0, len(df), len(df.columns) - 1, {"type": "formula", "criteria": "=MOD(ROW(),2)=1", "format": formato_alternado})
    worksheet.hide_gridlines(2)
    worksheet.set_landscape()
    worksheet.fit_to_pages(1, 0)
    worksheet.set_margins(0.25, 0.25, 0.5, 0.5)


def gerar_excel_completo(
    dados_empresa: dict[str, Any],
    df_dados: pd.DataFrame,
    *,
    incluir_dados_empresa: bool = True,
) -> bytes:
    output = io.BytesIO()
    resumo = pd.DataFrame(
        [
            ["Relatório", "Candidatos de classificação CNAE → LC 116 → NBS"],
            ["Gerado em", datetime.now().strftime("%d/%m/%Y %H:%M")],
            ["Versão dos dados", VERSAO_DADOS],
            ["Combinações encontradas", len(df_dados)],
            ["CNAEs distintos", df_dados.get("CNAE", pd.Series(dtype=str)).nunique()],
            ["NBS distintas", df_dados.get("NBS", pd.Series(dtype=str)).replace("Não localizada", pd.NA).nunique()],
            ["Aviso", AVISO_CLASSIFICACAO],
            ["Fonte legal", FONTE_LC_214],
            ["Fonte NBS", FONTE_NBS],
        ],
        columns=["Informação", "Valor"],
    )
    df_empresa = preparar_dados_empresa(dados_empresa)
    colunas_exportacao = COLUNAS_RESUMO if "Quantidade INDOP" in df_dados.columns else COLUNAS_RELATORIO
    df_export = _preparar_dataframe_excel(df_dados.reindex(columns=colunas_exportacao))

    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        resumo.to_excel(writer, sheet_name="Resumo", index=False)
        df_export.to_excel(writer, sheet_name="Combinacoes CNAE-NBS", index=False)
        if incluir_dados_empresa:
            df_empresa.to_excel(writer, sheet_name="Dados Empresa", index=False)
        _formatar_planilha(writer, "Resumo", resumo, {"Informação": 24, "Valor": 105})
        _formatar_planilha(
            writer,
            "Combinacoes CNAE-NBS",
            df_export,
            {
                "CNAE": 14,
                "Descrição CNAE": 42,
                "Item LC 116": 14,
                "Descrição LC 116": 50,
                "NBS": 16,
                "Descrição NBS": 65,
                "cClassTrib": 14,
                "Classificação Tributária": 48,
                "Redução IBS (%)": 18,
                "Redução CBS (%)": 18,
                "Tipo de Alíquota": 26,
                "Fundamento legal": 54,
                "INDOP": 14,
                "Detalhamento INDOP": 72,
                "Quantidade INDOP": 18,
                "Opções INDOP": 32,
                "Detalhamentos INDOP": 90,
                "Status do vínculo": 28,
            },
        )
        if incluir_dados_empresa:
            _formatar_planilha(
                writer,
                "Dados Empresa",
                df_empresa,
                {"Seção": 24, "Campo": 32, "Informação": 90},
            )

        workbook = writer.book
        resumo_ws = writer.sheets["Resumo"]
        formato_link = workbook.add_format({"font_color": "blue", "underline": True})
        resumo_ws.write_url(8, 1, FONTE_LC_214, formato_link, "Abrir texto compilado da LC 214")
        resumo_ws.write_url(9, 1, FONTE_NBS, formato_link, "Abrir Painel oficial da NBS")
    return output.getvalue()


def escapar_html(valor: Any) -> str:
    return html.escape(str(valor if valor is not None else ""), quote=True)
