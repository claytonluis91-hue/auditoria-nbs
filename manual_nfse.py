"""Geração de manual assistido para emissão no Portal Nacional da NFS-e."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from fpdf import FPDF, FontFace

import backend_issqn as issqn


PASTA_PROJETO = Path(__file__).resolve().parent
CAMINHO_CODIGOS = PASTA_PROJETO / "codigo_servico_nacional.json"
PASTA_IMAGENS = PASTA_PROJETO / "assets" / "manual_nfse"
VERSAO_MANUAL = "2.2"
VERSAO_GUIA_OFICIAL = "1.2.1"
URL_EMISSOR = "https://www.nfse.gov.br/EmissorNacional"
URL_GUIA = (
    "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/"
    "documentacao-atual/guia-emissorpubliconacionalweb_snnfse-ern-v12.pdf"
)
URL_ORIENTACAO_SIMPLES_2026 = (
    "https://www.gov.br/receitafederal/pt-br/assuntos/noticias/2026/agosto/"
    "simples-nacional-nfs-e-nacional-sera-obrigatoria-para-me-e-epp-a-partir-de-"
    "1o-de-novembro-de-2026"
)
ALERTA_SIMPLES_2026 = (
    "Se o emitente for optante pelo Simples Nacional, não destaque IBS nem CBS nas "
    "NFS-e com competência até 31/12/2026. Na página Pessoas, mantenha a opção "
    "'Preencher as informações IBS/CBS?' marcada como Não. As regras de IBS/CBS "
    "para esses contribuintes passam a produzir efeitos a partir de 01/01/2027, "
    "nas hipóteses previstas na regulamentação."
)

# Identidade visual do Grupo Nascel, baseada nos ativos oficiais do site institucional.
COR_NASCEL_PRETO = (24, 24, 24)
COR_NASCEL_DOURADO = (245, 180, 62)
COR_NASCEL_CREME = (250, 247, 240)
COR_TEXTO = (43, 43, 43)
COR_CINZA = (102, 102, 102)
COR_BORDA = (224, 215, 196)
CAMINHO_LOGO_NASCEL = PASTA_IMAGENS / "logo-nascel.png"


class ManualNFSeError(ValueError):
    """Indica dados insuficientes ou arquivos ausentes para gerar o manual."""


def _pdf_texto(valor: Any) -> str:
    return str(valor or "").encode("latin-1", errors="replace").decode("latin-1")


def _primeiro_valor(dados: dict[str, Any], *chaves: str) -> str:
    for chave in chaves:
        valor = dados.get(chave)
        if valor not in (None, "", [], {}):
            return str(valor).strip()
    return ""


def _formatar_cnpj(valor: Any) -> str:
    numeros = re.sub(r"\D", "", str(valor or ""))
    if len(numeros) != 14:
        return str(valor or "").strip()
    return (
        f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}/"
        f"{numeros[8:12]}-{numeros[12:]}"
    )


def _normalizar_item_lc116(valor: Any) -> str:
    prefixo = issqn.prefixo_item_lc116(valor)
    if not prefixo:
        return ""
    item, subitem = prefixo.rstrip(".").split(".")
    return f"{int(item)}.{subitem}"


@lru_cache(maxsize=1)
def carregar_codigos_servico(
    caminho: str | Path = CAMINHO_CODIGOS,
) -> tuple[dict[str, str], ...]:
    arquivo = Path(caminho)
    if not arquivo.is_file():
        raise ManualNFSeError(f"Tabela nacional de serviços não encontrada: {arquivo}.")
    with arquivo.open("r", encoding="utf-8-sig") as entrada:
        dados = json.load(entrada)
    registros = dados.get("registros") if isinstance(dados, dict) else None
    if not isinstance(registros, list):
        raise ManualNFSeError("Formato inválido da tabela nacional de serviços.")
    codigos: list[dict[str, str]] = []
    vistos: set[str] = set()
    for registro in registros:
        codigo = issqn.normalizar_codigo_nacional(registro.get("codigo"))
        descricao = str(registro.get("descricao") or "").strip()
        if not codigo or not descricao or codigo in vistos:
            continue
        vistos.add(codigo)
        codigos.append({"codigo": codigo, "descricao": descricao})
    return tuple(codigos)


def descricao_codigo_servico(codigo: Any) -> str:
    normalizado = issqn.normalizar_codigo_nacional(codigo)
    return next(
        (
            registro["descricao"]
            for registro in carregar_codigos_servico()
            if registro["codigo"] == normalizado
        ),
        "Descrição não localizada no Anexo B",
    )


def classificacoes_por_itens(
    itens_lc116: Iterable[Any],
    aliquotas: Iterable[dict[str, Any]] = (),
) -> list[dict[str, str]]:
    """Lista os desdobramentos nacionais e combina as alíquotas municipais."""

    itens: list[str] = []
    for valor in itens_lc116:
        item = _normalizar_item_lc116(valor)
        if item and item not in itens:
            itens.append(item)
    if not itens:
        raise ManualNFSeError("Selecione ao menos um item da LC 116 para o manual.")

    taxas: dict[str, set[float | None]] = {}
    for registro in aliquotas:
        codigo = issqn.normalizar_codigo_nacional(registro.get("codigo_servico"))
        if codigo:
            taxas.setdefault(codigo, set()).add(registro.get("aliquota"))

    resultado: list[dict[str, str]] = []
    for item in itens:
        prefixo = issqn.prefixo_item_lc116(item)
        for registro in carregar_codigos_servico():
            codigo = registro["codigo"]
            if not codigo.startswith(prefixo):
                continue
            valores = taxas.get(codigo, set())
            numeros = sorted(float(valor) for valor in valores if valor is not None)
            if numeros:
                aliquota = " / ".join(
                    f"{valor:.2f}%".replace(".", ",") for valor in numeros
                )
            else:
                aliquota = "Não informada"
            resultado.append(
                {
                    "item_lc116": item,
                    "codigo": codigo,
                    "descricao": registro["descricao"],
                    "aliquota": aliquota,
                }
            )
    return resultado


def preparar_enquadramentos_nbs(
    registros: Iterable[dict[str, Any]],
) -> list[dict[str, str]]:
    """Normaliza e remove duplicidades dos enquadramentos escolhidos na consulta."""

    resultado: list[dict[str, str]] = []
    vistos: set[tuple[str, ...]] = set()
    for registro in registros:
        item = _normalizar_item_lc116(
            registro.get("item_lc116", registro.get("Item LC 116", ""))
        )
        nbs = _primeiro_valor(registro, "nbs", "NBS")
        if not item or not nbs or nbs.casefold() == "não localizada":
            continue
        normalizado = {
            "item_lc116": item,
            "descricao_lc116": _primeiro_valor(
                registro, "descricao_lc116", "Descrição LC 116"
            ),
            "cnae": _primeiro_valor(registro, "cnae", "CNAE"),
            "descricao_cnae": _primeiro_valor(
                registro, "descricao_cnae", "Descrição CNAE"
            ),
            "cclass_trib": _primeiro_valor(registro, "cclass_trib", "cClassTrib"),
            "classificacao_tributaria": _primeiro_valor(
                registro, "classificacao_tributaria", "Classificação Tributária"
            ),
            "anexo": _primeiro_valor(registro, "anexo", "Anexo") or "Não informado",
            "nbs": nbs,
            "descricao_nbs": _primeiro_valor(registro, "descricao_nbs", "Descrição NBS"),
        }
        chave = tuple(normalizado.values())
        if chave not in vistos:
            vistos.add(chave)
            resultado.append(normalizado)
    return resultado


class ManualPDF(FPDF):
    def __init__(self, empresa: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.empresa = empresa
        self.set_margins(15, 16, 15)
        self.set_auto_page_break(auto=True, margin=17)
        self.set_title(_pdf_texto("Manual de primeira emissão da NFS-e — Simples Nacional"))
        self.set_author("Grupo Nascel")
        self.set_subject(_pdf_texto("Primeira emissão no Portal Nacional para optantes do Simples Nacional"))

    def header(self) -> None:
        if self.page_no() == 1:
            return
        if CAMINHO_LOGO_NASCEL.is_file():
            self.set_fill_color(*COR_NASCEL_PRETO)
            self.rect(15, 7, 43, 10, style="F")
            self.image(str(CAMINHO_LOGO_NASCEL), x=17, y=8.4, w=37)
        self.set_xy(61, 10)
        self.set_font("Helvetica", "B", 7.5)
        self.set_text_color(*COR_NASCEL_PRETO)
        self.cell(140, 5, _pdf_texto("AUDITORIA NBS | MANUAL DO EMISSOR NACIONAL"), align="R")
        self.set_y(18)
        self.set_draw_color(*COR_NASCEL_DOURADO)
        self.set_line_width(0.7)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(6)

    def footer(self) -> None:
        self.set_y(-13)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*COR_CINZA)
        self.cell(
            150,
            5,
            _pdf_texto(
                f"Grupo Nascel | Manual v{VERSAO_MANUAL} | Guia oficial v{VERSAO_GUIA_OFICIAL}"
            ),
        )
        self.cell(30, 5, _pdf_texto(f"Página {self.page_no()}"), align="R")


def _titulo_secao(pdf: ManualPDF, numero: int, titulo: str) -> None:
    y = pdf.get_y()
    pdf.set_fill_color(*COR_NASCEL_PRETO)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _pdf_texto(f"{numero}. {titulo}"), fill=True)
    pdf.set_fill_color(*COR_NASCEL_DOURADO)
    pdf.rect(192, y, 3, 10, style="F")
    pdf.ln(15)
    pdf.set_text_color(*COR_TEXTO)


def _subtitulo(pdf: ManualPDF, titulo: str) -> None:
    if pdf.get_y() > 262:
        pdf.add_page()
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(*COR_NASCEL_PRETO)
    pdf.cell(0, 7, _pdf_texto(titulo))
    pdf.ln(8)
    pdf.set_draw_color(*COR_NASCEL_DOURADO)
    pdf.set_line_width(0.5)
    pdf.line(15, pdf.get_y(), 48, pdf.get_y())
    pdf.ln(3)


def _paragrafos(pdf: ManualPDF, textos: Iterable[str]) -> None:
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*COR_TEXTO)
    for texto in textos:
        pdf.multi_cell(0, 5.4, _pdf_texto(texto))
        pdf.ln(2)


def _lista_passos(pdf: ManualPDF, passos: Iterable[str]) -> None:
    pdf.set_font("Helvetica", "", 9.5)
    for numero, passo in enumerate(passos, start=1):
        if pdf.get_y() > 270:
            pdf.add_page()
        y = pdf.get_y()
        pdf.set_fill_color(*COR_NASCEL_DOURADO)
        pdf.set_text_color(*COR_NASCEL_PRETO)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.ellipse(15, y, 6, 6, style="F")
        pdf.set_xy(15, y + 0.3)
        pdf.cell(6, 5, str(numero), align="C")
        pdf.set_xy(24, y)
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*COR_TEXTO)
        pdf.multi_cell(171, 5.2, _pdf_texto(passo))
        pdf.ln(2)


def _caixa_destaque(
    pdf: ManualPDF,
    titulo: str,
    texto: str,
    *,
    tipo: str = "dica",
) -> None:
    cores = {
        "dica": (COR_NASCEL_CREME, COR_NASCEL_DOURADO),
        "atencao": ((253, 242, 239), (191, 69, 54)),
        "confira": ((241, 247, 243), (63, 120, 78)),
    }
    fundo, destaque = cores.get(tipo, cores["dica"])
    linhas = max(1, len(_pdf_texto(texto)) // 92 + 1)
    altura = 13 + linhas * 5
    if pdf.get_y() + altura > 276:
        pdf.add_page()
    y = pdf.get_y()
    pdf.set_fill_color(*fundo)
    pdf.set_draw_color(*COR_BORDA)
    pdf.rect(15, y, 180, altura, style="DF")
    pdf.set_fill_color(*destaque)
    pdf.rect(15, y, 3, altura, style="F")
    pdf.set_xy(22, y + 3)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*COR_NASCEL_PRETO)
    pdf.cell(0, 5, _pdf_texto(titulo.upper()))
    pdf.set_xy(22, y + 9)
    pdf.set_font("Helvetica", "", 8.8)
    pdf.set_text_color(*COR_TEXTO)
    pdf.multi_cell(166, 4.7, _pdf_texto(texto))
    pdf.set_y(y + altura + 4)


def _imagem(
    pdf: ManualPDF,
    nome: str,
    legenda: str,
    *,
    altura: float = 105,
    largura: float = 180,
) -> None:
    caminho = PASTA_IMAGENS / nome
    if not caminho.is_file():
        raise ManualNFSeError(f"Imagem do manual não encontrada: {caminho}.")
    if pdf.get_y() + altura + 14 > 280:
        pdf.add_page()
    x = (210 - largura) / 2
    pdf.image(
        str(caminho),
        x=x,
        y=pdf.get_y(),
        w=largura,
        h=altura,
        keep_aspect_ratio=True,
    )
    pdf.set_y(pdf.get_y() + altura + 2)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*COR_CINZA)
    pdf.multi_cell(0, 4, _pdf_texto(legenda), align="C")
    pdf.set_text_color(*COR_TEXTO)


def _seta_numerada(
    pdf: ManualPDF,
    inicio_x: float,
    inicio_y: float,
    destino_x: float,
    destino_y: float,
    numero: int,
) -> None:
    """Desenha uma chamada vetorial sem alterar a captura oficial."""

    pdf.set_draw_color(*COR_NASCEL_DOURADO)
    pdf.set_line_width(0.9)
    pdf.line(inicio_x, inicio_y, destino_x, destino_y)
    angulo = math.atan2(destino_y - inicio_y, destino_x - inicio_x)
    for abertura in (-0.52, 0.52):
        pdf.line(
            destino_x,
            destino_y,
            destino_x - 3.2 * math.cos(angulo + abertura),
            destino_y - 3.2 * math.sin(angulo + abertura),
        )
    pdf.set_fill_color(*COR_NASCEL_DOURADO)
    pdf.ellipse(inicio_x - 3.2, inicio_y - 3.2, 6.4, 6.4, style="F")
    pdf.set_xy(inicio_x - 3.2, inicio_y - 2.6)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(*COR_NASCEL_PRETO)
    pdf.cell(6.4, 4.5, str(numero), align="C")


def _imagem_anotada(
    pdf: ManualPDF,
    nome: str,
    legenda: str,
    marcadores: Iterable[tuple[float, float, float, float]],
    *,
    altura: float,
    largura: float = 180,
) -> None:
    """Insere a captura e sobrepõe setas nas coordenadas relativas informadas."""

    caminho = PASTA_IMAGENS / nome
    if not caminho.is_file():
        raise ManualNFSeError(f"Imagem do manual não encontrada: {caminho}.")
    if pdf.get_y() + altura + 14 > 280:
        pdf.add_page()
    x = (210 - largura) / 2
    y = pdf.get_y()
    pdf.image(
        str(caminho),
        x=x,
        y=y,
        w=largura,
        h=altura,
        keep_aspect_ratio=True,
    )
    for numero, (inicio_x, inicio_y, destino_x, destino_y) in enumerate(
        marcadores, start=1
    ):
        _seta_numerada(
            pdf,
            x + inicio_x * largura,
            y + inicio_y * altura,
            x + destino_x * largura,
            y + destino_y * altura,
            numero,
        )
    pdf.set_y(y + altura + 2)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(*COR_CINZA)
    pdf.multi_cell(0, 4, _pdf_texto(legenda), align="C")
    pdf.set_text_color(*COR_TEXTO)


def _pagina_capa(
    pdf: ManualPDF,
    empresa: dict[str, Any],
    itens: list[str],
    localidade: dict[str, str],
) -> None:
    pdf.add_page()
    pdf.set_fill_color(*COR_NASCEL_PRETO)
    pdf.rect(0, 0, 210, 91, style="F")
    pdf.set_fill_color(*COR_NASCEL_DOURADO)
    pdf.rect(0, 88, 210, 3, style="F")
    if CAMINHO_LOGO_NASCEL.is_file():
        pdf.image(str(CAMINHO_LOGO_NASCEL), x=18, y=14, w=58)
    pdf.set_xy(18, 39)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 24)
    pdf.multi_cell(174, 11, _pdf_texto("Manual de primeira emissão da NFS-e"))
    pdf.set_x(18)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(*COR_NASCEL_DOURADO)
    pdf.cell(0, 8, _pdf_texto("Simples Nacional | Portal Nacional | Passo a passo"))

    pdf.set_xy(18, 105)
    pdf.set_text_color(*COR_NASCEL_PRETO)
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(174, 8, _pdf_texto(pdf.empresa))
    pdf.set_text_color(*COR_TEXTO)
    pdf.set_font("Helvetica", "", 11)
    pdf.ln(4)
    pdf.cell(0, 7, _pdf_texto(f"CNPJ: {_formatar_cnpj(empresa.get('cnpj')) or 'não informado'}"))
    pdf.ln(7)
    municipio = localidade.get("municipio") or "Município não identificado"
    uf = localidade.get("uf") or "--"
    pdf.cell(0, 7, _pdf_texto(f"Localidade cadastral: {municipio}/{uf}"))
    pdf.ln(7)
    pdf.multi_cell(0, 6, _pdf_texto(f"Itens LC 116 selecionados: {', '.join(itens)}"))
    pdf.ln(10)

    pdf.set_fill_color(*COR_NASCEL_CREME)
    pdf.set_draw_color(*COR_BORDA)
    y = pdf.get_y()
    pdf.rect(18, y, 174, 47, style="DF")
    pdf.set_xy(23, y + 6)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(*COR_NASCEL_PRETO)
    pdf.cell(0, 6, _pdf_texto("ORIENTAÇÃO NASCEL"))
    pdf.ln(8)
    pdf.set_x(23)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*COR_TEXTO)
    pdf.multi_cell(
        164,
        5,
        _pdf_texto(
            "Este roteiro foi preparado para a primeira emissão de optantes do Simples Nacional. Use as "
            "classificações sugeridas como apoio e confirme a operação efetiva, o contrato, o "
            "tomador, o local de incidência e a legislação aplicável antes de emitir."
        ),
    )
    pdf.set_y(246)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*COR_CINZA)
    pdf.multi_cell(
        0,
        5,
        _pdf_texto(
            f"Gerado em {datetime.now().astimezone().strftime('%d/%m/%Y às %H:%M')} | "
            f"Manual v{VERSAO_MANUAL} | Guia oficial v{VERSAO_GUIA_OFICIAL}"
        ),
        align="C",
    )


def _codigo_e_descricao(codigo: str, descricao: str) -> str:
    if codigo and descricao:
        return f"{codigo} - {descricao}"
    return codigo or descricao or "Não informado"


def _tabela_classificacoes(
    pdf: ManualPDF,
    classificacoes: list[dict[str, str]],
    enquadramentos_nbs: list[dict[str, str]],
    localidade: dict[str, str],
    numero_secao: int,
) -> None:
    pdf.add_page()
    _titulo_secao(pdf, numero_secao, "Classificações possíveis para o campo Serviço")
    municipio = localidade.get("municipio") or "município não identificado"
    uf = localidade.get("uf") or "--"
    _paragrafos(
        pdf,
        [
            f"A tabela cruza os itens LC 116 selecionados com o Anexo B oficial. A coluna de ISSQN usa a publicação municipal para {municipio}/{uf}; ausência de valor não significa alíquota zero.",
            "No Portal Nacional, pesquise o código ou parte da descrição e escolha somente a classificação compatível com o serviço descrito no contrato e na nota.",
        ],
    )
    pdf.set_font("Helvetica", "", 7.4)
    estilo = FontFace(
        emphasis="BOLD",
        color=COR_NASCEL_PRETO,
        fill_color=COR_NASCEL_DOURADO,
    )
    estilo_corpo = FontFace(
        color=COR_TEXTO,
        fill_color=(255, 255, 255),
    )
    pdf.set_draw_color(*COR_BORDA)
    with pdf.table(
        width=180,
        col_widths=(20, 31, 27, 102),
        headings_style=estilo,
        line_height=4.3,
        text_align=("CENTER", "CENTER", "CENTER", "LEFT"),
        borders_layout="HORIZONTAL_LINES",
    ) as tabela:
        cabecalho = tabela.row()
        for valor in ("LC 116", "Código nacional", "ISSQN", "Descrição oficial"):
            cabecalho.cell(_pdf_texto(valor))
        for registro in classificacoes:
            linha = tabela.row(style=estilo_corpo)
            linha.cell(_pdf_texto(registro["item_lc116"]))
            linha.cell(_pdf_texto(registro["codigo"]))
            linha.cell(_pdf_texto(registro["aliquota"]))
            linha.cell(_pdf_texto(registro["descricao"]))

    if not enquadramentos_nbs:
        return
    pdf.ln(8)
    pdf.set_fill_color(*COR_NASCEL_CREME)
    pdf.set_text_color(*COR_NASCEL_PRETO)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _pdf_texto("Possibilidades NBS da consulta empresarial"), fill=True)
    pdf.ln(11)
    pdf.set_text_color(*COR_TEXTO)
    _paragrafos(
        pdf,
        [
            "A lista abaixo reúne as possibilidades de NBS encontradas para os serviços selecionados. Para o Simples Nacional em 2026, use a NBS como apoio ao campo Serviço e não preencha cClassTrib ou outros campos de IBS/CBS.",
        ],
    )
    pdf.set_font("Helvetica", "", 6.6)
    with pdf.table(
        width=180,
        col_widths=(52, 58, 70),
        headings_style=estilo,
        line_height=4.1,
        text_align="LEFT",
        borders_layout="HORIZONTAL_LINES",
        repeat_headings=1,
    ) as tabela_nbs:
        cabecalho = tabela_nbs.row()
        for valor in ("Serviço LC 116", "CNAE", "NBS"):
            cabecalho.cell(_pdf_texto(valor))
        for registro in enquadramentos_nbs:
            linha = tabela_nbs.row(style=estilo_corpo)
            linha.cell(
                _pdf_texto(
                    _codigo_e_descricao(
                        registro["item_lc116"], registro["descricao_lc116"]
                    )
                )
            )
            linha.cell(
                _pdf_texto(
                    _codigo_e_descricao(registro["cnae"], registro["descricao_cnae"])
                )
            )
            linha.cell(
                _pdf_texto(_codigo_e_descricao(registro["nbs"], registro["descricao_nbs"]))
            )


def gerar_manual_nfse(
    empresa: dict[str, Any],
    itens_lc116: Iterable[Any],
    aliquotas: Iterable[dict[str, Any]] = (),
    enquadramentos_nbs: Iterable[dict[str, Any]] = (),
) -> bytes:
    """Gera o manual personalizado em PDF para download no Streamlit."""

    cnpj = _formatar_cnpj(empresa.get("cnpj"))
    if not cnpj:
        raise ManualNFSeError("Consulte um CNPJ antes de gerar o manual.")
    itens = [_normalizar_item_lc116(item) for item in itens_lc116]
    itens = list(dict.fromkeys(item for item in itens if item))
    classificacoes = classificacoes_por_itens(itens, aliquotas)
    if not classificacoes:
        raise ManualNFSeError("Nenhuma classificação nacional foi localizada para os itens selecionados.")

    enquadramentos = [
        registro
        for registro in preparar_enquadramentos_nbs(enquadramentos_nbs)
        if registro["item_lc116"] in itens
    ]
    razao = _primeiro_valor(empresa, "razao_social", "nome") or "Empresa consultada"
    localidade = issqn.extrair_localidade_empresa(empresa)
    pdf = ManualPDF(razao)
    _pagina_capa(pdf, empresa, itens, localidade)

    pdf.add_page()
    _titulo_secao(pdf, 1, "Antes de começar")
    _paragrafos(
        pdf,
        [
            "Este passo a passo acompanha a primeira emissão de uma empresa do Simples Nacional no Portal Nacional. Separe os dados antes de começar: o portal salva rascunhos, mas uma preparação curta reduz retrabalho e escolhas incorretas.",
        ],
    )
    _subtitulo(pdf, "Tenha em mãos")
    _lista_passos(
        pdf,
        [
            "Data de competência e documento que comprove a prestação: contrato, pedido, ordem de serviço ou medição.",
            "CPF/CNPJ ou identificação do tomador, endereço, município e informação sobre eventual intermediário.",
            "Descrição objetiva do serviço, valor, descontos, deduções documentadas e retenções combinadas.",
            "Código de Tributação Nacional e NBS coerentes com a operação. Consulte as possibilidades personalizadas deste manual.",
            "Confirmação do município de incidência do ISSQN e da alíquota aplicável à operação concreta.",
        ],
    )
    _caixa_destaque(
        pdf,
        "Dados usados neste roteiro",
        f"Emitente: {razao} | CNPJ: {cnpj} | Localidade cadastral: "
        f"{localidade.get('municipio') or 'não identificada'}/{localidade.get('uf') or '--'} | "
        f"Itens LC 116 analisados: {', '.join(itens)}.",
        tipo="confira",
    )
    _caixa_destaque(
        pdf,
        "Atenção",
        "O manual orienta o preenchimento, mas não decide sozinho a tributação. Havendo exportação, imunidade, suspensão, benefício, dedução, retenção ou operação no exterior, valide o tratamento antes da emissão.",
        tipo="atencao",
    )
    _caixa_destaque(
        pdf,
        "Simples Nacional em 2026 — não destaque IBS/CBS",
        ALERTA_SIMPLES_2026,
        tipo="atencao",
    )

    pdf.add_page()
    _titulo_secao(pdf, 2, "Acesse o Portal Nacional")
    _paragrafos(
        pdf,
        [
            f"Acesse {URL_EMISSOR}. O portal oferece entrada com usuário e senha, certificado digital ou conta GOV.BR.",
            f"Confirme que o emitente exibido é {razao}, CNPJ {cnpj}, antes de iniciar o preenchimento.",
        ],
    )
    _imagem(
        pdf,
        "01-acesso.png",
        f"Tela de acesso reproduzida do Guia do Emissor Público Nacional Web v{VERSAO_GUIA_OFICIAL}.",
        altura=90,
    )
    _caixa_destaque(
        pdf,
        "Primeiro acesso",
        "Se ainda não houver senha, use Fazer primeiro acesso e tenha os dados do responsável legal disponíveis. Para certificado digital, confira se o certificado corresponde ao emitente que será usado.",
    )

    pdf.add_page()
    _titulo_secao(pdf, 3, "Configure o emissor")
    _paragrafos(
        pdf,
        [
            "Acesse Configurações pelo ícone de engrenagem antes da primeira emissão e sempre que os dados de contato ou a forma de exibir os tributos mudarem.",
        ],
    )
    _imagem(
        pdf,
        "08-configuracoes.png",
        f"Página Configurações reproduzida do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        altura=106,
    )
    _lista_passos(
        pdf,
        [
            "Confira e-mail e telefone. O portal pode usar esses dados quando as fontes cadastrais oficiais não os fornecerem.",
            "Valide a opção atual no Simples Nacional exibida pelo sistema.",
            "Escolha como informar os valores aproximados dos tributos: valores por nota, percentuais configurados ou alíquota do Simples, quando disponível.",
            "Clique em Salvar e confirme a mensagem de conclusão.",
        ],
    )

    pdf.add_page()
    _titulo_secao(pdf, 4, "Inicie uma emissão completa")
    _paragrafos(
        pdf,
        [
            "No painel principal, abra Tipos de emissão no ícone da NFS-e com sinal de mais e escolha Emissão completa. O atalho da página inicial leva ao mesmo fluxo.",
            "Use a emissão completa quando precisar informar tomador, local da prestação, intermediário, retenções, campos de IBS/CBS ou demais detalhes da operação. A emissão simplificada é destinada ao fluxo próprio disponível no portal.",
        ],
    )
    _imagem(
        pdf,
        "02-iniciar-emissao.png",
        f"Menu Tipos de emissão reproduzido do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        altura=97,
    )
    _caixa_destaque(
        pdf,
        "Dica Nascel",
        "Não escolha Emissão simplificada apenas para reduzir campos. Use o fluxo compatível com o perfil do emitente e com a operação que será documentada.",
    )

    pdf.add_page()
    _titulo_secao(pdf, 5, "Preencha Pessoas")
    _paragrafos(
        pdf,
        [
            "Nesta página você define a competência, quem está emitindo e os participantes da operação. Essas escolhas controlam campos exibidos nas etapas seguintes.",
        ],
    )
    _imagem_anotada(
        pdf,
        "03-pessoas.png",
        f"Passo Pessoas com os três pontos iniciais destacados. Captura do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        (
            (0.13, 0.28, 0.025, 0.30),
            (0.34, 0.39, 0.17, 0.43),
            (0.86, 0.84, 0.50, 0.90),
        ),
        altura=133,
    )
    _caixa_destaque(
        pdf,
        "Simples Nacional: marque Não em 2026",
        "Para emitente optante pelo Simples Nacional e competência até 31/12/2026, selecione Não no campo 'Preencher as informações IBS/CBS?'. Não informe nem destaque IBS/CBS nessa NFS-e.",
        tipo="atencao",
    )
    _lista_passos(
        pdf,
        [
            "Marcador 1: selecione Não em Preencher as informações IBS/CBS? para competências de 2026.",
            "Marcador 2: informe a data de competência. Preencha série e número da DPS somente quando houver controle próprio que exija esses dados.",
            "Marcador 3: confirme município, inscrição municipal, opção e regime de apuração do Simples Nacional.",
        ],
    )

    pdf.add_page()
    _titulo_secao(pdf, 5, "Preencha o Tomador do Serviço")
    _paragrafos(
        pdf,
        [
            "O tomador é quem contratou ou adquiriu o serviço. Na primeira emissão, dedique atenção especial a este bloco: CPF/CNPJ, nome e contato incorretos podem exigir correção posterior da nota.",
        ],
    )
    _imagem_anotada(
        pdf,
        "16-tomador.png",
        f"Bloco Tomador/Adquirente no Brasil anotado sobre captura do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        (
            (0.18, 0.05, 0.012, 0.18),
            (0.34, 0.35, 0.16, 0.50),
            (0.45, 0.35, 0.275, 0.50),
            (0.82, 0.67, 0.57, 0.82),
        ),
        altura=51,
    )
    _lista_passos(
        pdf,
        [
            "Marcador 1: selecione Brasil. Use Exterior somente quando o estabelecimento ou domicílio do tomador estiver fora do país.",
            "Marcador 2: informe o CPF/CNPJ do tomador exatamente como consta no contrato ou pedido.",
            "Marcador 3: clique na lupa e confira o Nome/Razão Social recuperado pelo portal antes de continuar.",
            "Marcador 4: informe telefone e e-mail válidos. Marque Informar endereço quando o portal não recuperar o cadastro ou quando o preenchimento for necessário.",
            "Informe destinatário ou intermediário somente quando houver participante diferente do tomador e suporte documental para isso.",
        ],
    )
    _caixa_destaque(
        pdf,
        "Ponto de controle",
        "Não confunda tomador/adquirente com destinatário ou intermediário. Guarde o contrato e o cadastro usado para justificar a identificação escolhida.",
        tipo="atencao",
    )

    pdf.add_page()
    _titulo_secao(pdf, 6, "Preencha Serviço")
    _paragrafos(
        pdf,
        [
            "A página Serviço reúne local, classificações e descrição daquilo que foi efetivamente fornecido. Escolha os códigos pelo conteúdo da prestação, não apenas pela atividade cadastral da empresa.",
        ],
    )
    _imagem_anotada(
        pdf,
        "04-servico.png",
        f"Campos principais do Serviço anotados sobre captura do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        (
            (0.44, 0.12, 0.22, 0.19),
            (0.88, 0.30, 0.54, 0.38),
            (0.88, 0.54, 0.55, 0.60),
            (0.20, 0.70, 0.42, 0.78),
        ),
        altura=122,
    )
    _lista_passos(
        pdf,
        [
            "Marcador 1: informe país e município em que o serviço foi concluído. Não presuma que será sempre o município do prestador.",
            "Marcador 2: pesquise o Código de Tributação Nacional e compare com a tabela personalizada da próxima seção.",
            "Marcador 3: selecione a NBS compatível e o Código indicador da operação quando exibido.",
            "Marcador 4: descreva objeto, período ou referência. Evite descrições genéricas como somente 'serviços prestados'.",
            "Para uma prestação comum, mantenha Não na pergunta sobre imunidade, exportação ou não incidência. Marque Sim apenas com fundamento confirmado.",
        ],
    )

    pdf.add_page()
    _titulo_secao(pdf, 6, "Serviço: campos complementares")
    _imagem(
        pdf,
        "09-servico-complementares.png",
        f"Continuação do passo Serviço reproduzida do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        altura=102,
    )
    _lista_passos(
        pdf,
        [
            "Informe documento de responsabilidade técnica quando a atividade e a documentação da operação o exigirem.",
            "Use Documento de referência e Informações complementares para relacionar contrato, medição ou fundamento relevante, sem inserir dados desnecessários.",
            "Em operações B2B, informe pedido, ordem de compra, ordem de serviço ou projeto quando esse vínculo existir.",
            "Preencha blocos especiais de imóvel, obra, evento, comércio exterior ou operação governamental somente quando forem habilitados pela classificação escolhida.",
        ],
    )
    _caixa_destaque(
        pdf,
        "Campos condicionais",
        "A página muda conforme as respostas anteriores. Se um campo esperado não aparecer, volte e confira local, Código de Tributação Nacional, tipo de operação e participantes.",
    )

    _tabela_classificacoes(pdf, classificacoes, enquadramentos, localidade, 7)

    pdf.add_page()
    _titulo_secao(pdf, 8, "Informe os valores e tributos")
    _paragrafos(
        pdf,
        [
            "Informe o valor bruto da prestação e trate separadamente descontos, deduções, retenções e tributos. Os campos exibidos variam conforme o regime, o serviço, o município, os participantes e as respostas anteriores.",
        ],
    )
    _subtitulo(pdf, "ISSQN e retenções")
    _lista_passos(
        pdf,
        [
            "Digite o valor do serviço e confira se descontos condicionados ou incondicionados estão documentados.",
            "Revise tributação, município de incidência, exigibilidade, regime especial, benefício e retenção do ISSQN.",
            "Se houver dedução ou redução da base, inclua somente documentos e valores aceitos para a operação e guarde os comprovantes.",
            "Confira a alíquota apresentada pelo portal com a publicação municipal indicada neste manual. Ausência de alíquota na tabela não significa alíquota zero.",
            "Preencha PIS, COFINS, IRRF, CSLL e contribuição previdenciária conforme a responsabilidade e a retenção efetivamente aplicáveis.",
        ],
    )
    _caixa_destaque(
        pdf,
        "Divergência de alíquota",
        "Se o portal e a referência municipal apresentarem valores diferentes, interrompa a emissão e confirme o código, o local de incidência e a regra vigente com a administração tributária ou a assessoria responsável.",
        tipo="atencao",
    )
    _caixa_destaque(
        pdf,
        "Simples Nacional em 2026: sem destaque de IBS/CBS",
        "Não preencha CST, cClassTrib, base, alíquota ou valores de IBS/CBS. Se esses campos aparecerem, volte à página Pessoas e confirme que a opção 'Preencher as informações IBS/CBS?' está marcada como Não.",
        tipo="atencao",
    )

    pdf.add_page()
    _titulo_secao(pdf, 9, "Revise Pessoas e Serviço")
    _paragrafos(
        pdf,
        [
            "O passo Emitir NFS-e consolida as informações em blocos. Use os botões Editar Pessoas, Editar Serviço e Editar Valores sempre que encontrar qualquer divergência.",
        ],
    )
    _imagem(
        pdf,
        "06-revisao-servico.png",
        f"Resumo do serviço para conferência, reproduzido do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        altura=62,
    )
    _lista_passos(
        pdf,
        [
            "Confira competência, papel do emitente, tomador, destinatário e intermediário.",
            "Compare local, Código de Tributação Nacional, NBS, indicador da operação e descrição com contrato e pedido.",
            "Confirme que a opção de IBS/CBS ficou marcada como Não e que não há destaque desses tributos na emissão de 2026.",
        ],
    )

    pdf.add_page()
    _titulo_secao(pdf, 9, "Revise Valores e emita")
    _paragrafos(
        pdf,
        [
            "Na prévia, compare cada valor com o contrato, pedido ou cobrança. Para optantes do Simples Nacional em 2026, a conferência deve mostrar ISSQN e eventuais retenções aplicáveis, sem destaque de IBS/CBS.",
        ],
    )
    _lista_passos(
        pdf,
        [
            "Reconcilie valor bruto, base de cálculo, deduções, descontos, retenções e valor líquido.",
            "Confira o ISSQN e os tributos federais ou retenções aplicáveis. Certifique-se de que não há base, alíquota ou valor de IBS/CBS destacado.",
            "Use Editar Pessoas, Editar Serviço ou Editar Valores para corrigir qualquer divergência antes da autorização.",
            "Clique em Emitir NFS-e somente depois da conferência final. A correção posterior pode exigir substituição, cancelamento ou análise fiscal.",
        ],
    )
    _caixa_destaque(
        pdf,
        "Primeira emissão",
        "Faça uma conferência por outra pessoa, quando possível. Depois da autorização, confirme o resultado antes de enviar o documento ao tomador.",
        tipo="confira",
    )

    pdf.add_page()
    _titulo_secao(pdf, 10, "Confirme a emissão e arquive")
    _paragrafos(
        pdf,
        [
            "A mensagem de sucesso confirma a autorização. Antes de sair da página, revise o resumo e use os botões de download disponíveis.",
        ],
    )
    _lista_passos(
        pdf,
        [
            "Anote ou preserve a chave de acesso e confirme município gerador, competência, participantes, serviço, NBS e valores.",
            "Baixe o XML e o DANFSe imediatamente. O XML é o documento eletrônico estruturado; o DANFSe é sua representação auxiliar.",
            "Arquive contrato, pedido, comprovantes de local, deduções, retenções e demais evidências junto com os arquivos da nota.",
        ],
    )
    _caixa_destaque(
        pdf,
        "Padrão de arquivo sugerido",
        "AAAA-MM_Documento_Tomador_Valor_Chave. Mantenha XML e DANFSe na mesma pasta e preserve também o comprovante de envio ao cliente.",
    )

    pdf.add_page()
    _titulo_secao(pdf, 11, "Consulte e gerencie notas emitidas")
    _imagem(
        pdf,
        "11-notas-emitidas.png",
        f"Menu de ações das notas emitidas reproduzido do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        altura=52,
    )
    _lista_passos(
        pdf,
        [
            "Use Visualizar para revisar a NFS-e e os eventos vinculados.",
            "Use Substituir quando a correção puder seguir o fluxo de substituição. O sistema vincula a nova nota à original.",
            "Use Cancelar NFS-e conforme as regras disponíveis. Alguns casos exigem motivo, justificativa e solicitação de análise fiscal.",
            "Use Download XML e Download DANFSe para recompor o arquivo quando necessário.",
        ],
    )
    _imagem(
        pdf,
        "12-cancelamento.png",
        f"Exemplo de solicitação de análise fiscal para cancelamento, reproduzido do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        altura=84,
        largura=145,
    )
    _caixa_destaque(
        pdf,
        "Antes de cancelar ou substituir",
        "Registre o motivo, confirme o efeito fiscal e comunique o tomador. Não trate cancelamento e substituição como equivalentes.",
        tipo="atencao",
    )

    pdf.add_page()
    _titulo_secao(pdf, 11, "Confira o DANFSe")
    _paragrafos(
        pdf,
        [
            "Abra o DANFSe baixado e faça uma última conferência visual. A ausência ou a apresentação resumida de um dado no PDF não substitui a validação do XML.",
        ],
    )
    _imagem(
        pdf,
        "15-danfse.png",
        f"Exemplo de DANFSe reproduzido do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        altura=156,
        largura=112,
    )
    _lista_passos(
        pdf,
        [
            "Confira chave, número, competência, emitente, tomador, serviço, valores e tributação.",
            "Valide a autenticidade pelo QR Code ou pela consulta pública quando necessário.",
            "Em caso de divergência, analise a possibilidade de substituição ou cancelamento antes de qualquer novo envio ao tomador.",
        ],
    )

    pdf.add_page()
    _titulo_secao(pdf, 12, "Use rascunhos e serviços favoritos")
    _subtitulo(pdf, "Serviços favoritos")
    _paragrafos(
        pdf,
        [
            "Cadastre serviços recorrentes para recuperar Código de Tributação Nacional, NBS e descrição com mais rapidez. Revise o favorito sempre que a operação ou as tabelas mudarem.",
        ],
    )
    _imagem(
        pdf,
        "14-servicos-favoritos.png",
        f"Cadastro de serviço favorito reproduzido do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        altura=95,
    )
    _subtitulo(pdf, "Rascunhos")
    _paragrafos(
        pdf,
        [
            "O portal salva a DPS em preenchimento automaticamente. Em Rascunhos, escolha Editar para retomar ou Excluir somente quando tiver certeza de que o registro não será usado.",
        ],
    )
    _imagem(
        pdf,
        "13-rascunhos.png",
        f"Lista de rascunhos reproduzida do guia oficial v{VERSAO_GUIA_OFICIAL}.",
        altura=28,
    )

    pdf.add_page()
    _titulo_secao(pdf, 13, "Checklist final da Nascel")
    _lista_passos(
        pdf,
        [
            "O emitente, a inscrição municipal e o regime tributário estão corretos.",
            "Se o emitente é optante pelo Simples Nacional e a competência é de 2026, a opção de IBS/CBS está marcada como Não e não há destaque desses tributos.",
            "A competência corresponde ao período da prestação e à documentação de suporte.",
            "Tomador, destinatário e intermediário foram identificados nos papéis corretos.",
            "Local da prestação e município de incidência do ISSQN foram conferidos.",
            "Código de Tributação Nacional, NBS, CST e cClassTrib são coerentes entre si e com o contrato.",
            "Descrição, valor, descontos, deduções e retenções coincidem com os documentos comerciais.",
            "Alíquota e valor do ISSQN foram validados; base, alíquotas e valores de IBS/CBS foram revisados quando aplicáveis.",
            "XML, DANFSe e evidências da operação foram arquivados após a emissão.",
        ],
    )
    _caixa_destaque(
        pdf,
        "Pare e valide",
        "Se qualquer item do checklist estiver incerto, salve o rascunho e valide antes de emitir. Corrigir antes da autorização é mais seguro do que depender de cancelamento ou substituição.",
        tipo="confira",
    )

    pdf.add_page()
    _titulo_secao(pdf, 14, "Fontes, versão e responsabilidade")
    _paragrafos(
        pdf,
        [
            f"Guia oficial analisado: Guia do Emissor Público Nacional Web da NFS-e, arquivo local versão {VERSAO_GUIA_OFICIAL}, revisão de 27/07/2026.",
            f"Endereço oficial de referência: {URL_GUIA}",
            f"Orientação oficial sobre Simples Nacional em 2026: {URL_ORIENTACAO_SIMPLES_2026}",
            f"Alíquotas municipais: {issqn.FONTE_ALIQUOTAS}",
            "Classificações nacionais: ANEXO_B-NBS2-LISTA_SERVICO_NACIONAL-SNNFSe v1.01, publicado em 22/01/2026.",
            "As capturas do Portal Nacional foram reproduzidas do guia oficial e podem conter dados fictícios usados pelo próprio documento de referência.",
            "A interface, as tabelas e as regras de negócio podem mudar. Antes de utilizar o manual, confira a versão indicada no rodapé e as atualizações oficiais.",
            "Este material é orientativo e não constitui parecer fiscal ou jurídico. A classificação final depende da operação concreta e da legislação vigente.",
            "Identidade visual: Grupo Nascel. Conteúdo assistido: Auditoria NBS.",
        ],
    )
    return bytes(pdf.output())


def nome_arquivo_manual(empresa: dict[str, Any]) -> str:
    razao = _primeiro_valor(empresa, "nome_fantasia", "razao_social", "nome")
    normalizado = unicodedata.normalize("NFKD", razao)
    seguro = "".join(char for char in normalizado if not unicodedata.combining(char))
    seguro = re.sub(r"[^a-zA-Z0-9]+", "_", seguro).strip("_").lower()
    return f"manual_nfse_{seguro or 'empresa'}.pdf"
