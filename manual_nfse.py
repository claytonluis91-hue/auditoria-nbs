"""Geração de manual assistido para emissão no Portal Nacional da NFS-e."""

from __future__ import annotations

import json
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
VERSAO_MANUAL = "1.0.1"
VERSAO_GUIA_OFICIAL = "1.2"
URL_EMISSOR = "https://www.nfse.gov.br/EmissorNacional"
URL_GUIA = (
    "https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/"
    "documentacao-atual/guia-emissorpubliconacionalweb_snnfse-ern-v12.pdf"
)


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


class ManualPDF(FPDF):
    def __init__(self, empresa: str):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.empresa = empresa
        self.set_margins(15, 16, 15)
        self.set_auto_page_break(auto=True, margin=17)
        self.set_title(_pdf_texto("Manual assistido de emissão da NFS-e"))
        self.set_author("Auditoria NBS")

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(23, 74, 120)
        self.cell(0, 5, _pdf_texto("AUDITORIA NBS | MANUAL DO EMISSOR NACIONAL"))
        self.ln(7)
        self.set_draw_color(190, 205, 218)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-13)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(95, 108, 120)
        self.cell(
            150,
            5,
            _pdf_texto(
                f"Manual v{VERSAO_MANUAL} | Imagens: Guia oficial v{VERSAO_GUIA_OFICIAL}"
            ),
        )
        self.cell(30, 5, _pdf_texto(f"Página {self.page_no()}"), align="R")


def _titulo_secao(pdf: ManualPDF, numero: int, titulo: str) -> None:
    pdf.set_fill_color(23, 74, 120)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, _pdf_texto(f"{numero}. {titulo}"), fill=True)
    pdf.ln(15)
    pdf.set_text_color(31, 43, 55)


def _paragrafos(pdf: ManualPDF, textos: Iterable[str]) -> None:
    pdf.set_font("Helvetica", "", 10)
    for texto in textos:
        pdf.multi_cell(0, 5.4, _pdf_texto(texto))
        pdf.ln(2)


def _imagem(pdf: ManualPDF, nome: str, legenda: str, *, altura: float = 105) -> None:
    caminho = PASTA_IMAGENS / nome
    if not caminho.is_file():
        raise ManualNFSeError(f"Imagem do manual não encontrada: {caminho}.")
    if pdf.get_y() + altura + 14 > 280:
        pdf.add_page()
    pdf.image(str(caminho), x=15, y=pdf.get_y(), w=180, h=altura, keep_aspect_ratio=True)
    pdf.set_y(pdf.get_y() + altura + 2)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(95, 108, 120)
    pdf.multi_cell(0, 4, _pdf_texto(legenda), align="C")
    pdf.set_text_color(31, 43, 55)


def _pagina_capa(
    pdf: ManualPDF,
    empresa: dict[str, Any],
    itens: list[str],
    localidade: dict[str, str],
) -> None:
    pdf.add_page()
    pdf.set_fill_color(23, 74, 120)
    pdf.rect(0, 0, 210, 84, style="F")
    pdf.set_xy(18, 24)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 24)
    pdf.multi_cell(174, 11, _pdf_texto("Manual assistido de emissão da NFS-e"))
    pdf.set_x(18)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, _pdf_texto("Portal Nacional | Emissão completa"))

    pdf.set_xy(18, 101)
    pdf.set_text_color(23, 74, 120)
    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(174, 8, _pdf_texto(pdf.empresa))
    pdf.set_text_color(31, 43, 55)
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

    pdf.set_fill_color(237, 244, 249)
    pdf.set_draw_color(190, 205, 218)
    y = pdf.get_y()
    pdf.rect(18, y, 174, 47, style="DF")
    pdf.set_xy(23, y + 6)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(23, 74, 120)
    pdf.cell(0, 6, _pdf_texto("IMPORTANTE"))
    pdf.ln(8)
    pdf.set_x(23)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(31, 43, 55)
    pdf.multi_cell(
        164,
        5,
        _pdf_texto(
            "Este documento é um roteiro de preenchimento. O CNPJ e o CNAE ajudam a localizar "
            "possibilidades, mas não substituem a análise do serviço efetivamente prestado, do "
            "tomador, do local de incidência e da legislação municipal vigente."
        ),
    )
    pdf.set_y(246)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(95, 108, 120)
    pdf.multi_cell(
        0,
        5,
        _pdf_texto(
            f"Gerado em {datetime.now().astimezone().strftime('%d/%m/%Y às %H:%M')} | "
            f"Manual v{VERSAO_MANUAL} | Guia oficial v{VERSAO_GUIA_OFICIAL}"
        ),
        align="C",
    )


def _tabela_classificacoes(
    pdf: ManualPDF,
    classificacoes: list[dict[str, str]],
    localidade: dict[str, str],
) -> None:
    pdf.add_page()
    _titulo_secao(pdf, 5, "Classificações possíveis para o campo Serviço")
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
        color=(255, 255, 255),
        fill_color=(23, 74, 120),
    )
    estilo_corpo = FontFace(
        color=(31, 43, 55),
        fill_color=(255, 255, 255),
    )
    pdf.set_draw_color(190, 205, 218)
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


def gerar_manual_nfse(
    empresa: dict[str, Any],
    itens_lc116: Iterable[Any],
    aliquotas: Iterable[dict[str, Any]] = (),
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

    razao = _primeiro_valor(empresa, "razao_social", "nome") or "Empresa consultada"
    localidade = issqn.extrair_localidade_empresa(empresa)
    pdf = ManualPDF(razao)
    _pagina_capa(pdf, empresa, itens, localidade)

    pdf.add_page()
    _titulo_secao(pdf, 1, "Acesse o Portal Nacional")
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
        "Tela de acesso reproduzida do Guia do Emissor Público Nacional Web v1.2.",
        altura=96,
    )

    pdf.add_page()
    _titulo_secao(pdf, 2, "Inicie uma emissão completa")
    _paragrafos(
        pdf,
        [
            "No painel principal, abra Tipos de emissão e escolha Emissão completa.",
            "A emissão completa deve ser usada quando forem necessários dados de local da prestação, tomador, retenções ou demais informações que não cabem na emissão simplificada.",
        ],
    )
    _imagem(
        pdf,
        "02-iniciar-emissao.png",
        "Menu de tipos de emissão do Guia do Emissor Público Nacional Web v1.2.",
        altura=100,
    )

    pdf.add_page()
    _titulo_secao(pdf, 3, "Preencha Pessoas")
    _paragrafos(
        pdf,
        [
            "Informe a data de competência, confira os dados do emitente e selecione a inscrição municipal correta quando houver mais de uma opção.",
            "Identifique o tomador no Brasil ou no exterior. Para determinados serviços, os dados do tomador influenciam a localidade de incidência do ISSQN.",
        ],
    )
    _imagem(
        pdf,
        "03-pessoas.png",
        "Passo Pessoas reproduzido do Guia do Emissor Público Nacional Web v1.2.",
        altura=135,
    )

    pdf.add_page()
    _titulo_secao(pdf, 4, "Preencha Serviço")
    _paragrafos(
        pdf,
        [
            "Informe o país e o município onde o serviço foi concluído. O sistema poderá ajustar a incidência conforme o Código de Tributação Nacional e as regras da LC 116.",
            "No campo Código de Tributação Nacional, digite ao menos três caracteres e selecione uma das classificações da tabela personalizada na página seguinte.",
            "Preencha o código complementar municipal quando o portal o exigir e descreva o serviço de forma coerente com o contrato e a classificação escolhida.",
        ],
    )
    _imagem(
        pdf,
        "04-servico.png",
        "Passo Serviço reproduzido do Guia do Emissor Público Nacional Web v1.2.",
        altura=125,
    )

    _tabela_classificacoes(pdf, classificacoes, localidade)

    pdf.add_page()
    _titulo_secao(pdf, 6, "Informe os valores e tributos")
    _paragrafos(
        pdf,
        [
            "Informe o valor do serviço e, quando aplicável, descontos, deduções, retenções e tributação federal.",
            "Confira a alíquota de ISSQN apresentada pelo portal com a publicação municipal indicada na tabela. Divergências devem ser confirmadas com a administração tributária do município antes da emissão.",
            "Os campos disponíveis variam conforme regime tributário, serviço, município, tomador e opções feitas nas etapas anteriores.",
        ],
    )
    _imagem(
        pdf,
        "05-valores.png",
        "Exemplo de campos tributários reproduzido do Guia do Emissor Público Nacional Web v1.2.",
        altura=72,
    )

    pdf.add_page()
    _titulo_secao(pdf, 7, "Revise e emita a NFS-e")
    _paragrafos(
        pdf,
        [
            "Revise pessoas, serviço e valores antes de clicar em Emitir NFS-e. Volte às etapas anteriores se qualquer informação estiver divergente.",
            "Após a emissão, salve o DANFSe e o XML. Guarde também contrato, evidências do local da prestação e documentos que sustentem deduções, retenções ou tratamentos especiais.",
        ],
    )
    _imagem(
        pdf,
        "06-revisao-servico.png",
        "Resumo do serviço reproduzido do Guia do Emissor Público Nacional Web v1.2.",
        altura=90,
    )
    _imagem(
        pdf,
        "07-revisao-valores.png",
        "Prévia de valores reproduzida do Guia do Emissor Público Nacional Web v1.2.",
        altura=92,
    )

    pdf.add_page()
    _titulo_secao(pdf, 8, "Fontes, versão e responsabilidade")
    _paragrafos(
        pdf,
        [
            f"Guia oficial utilizado: versão {VERSAO_GUIA_OFICIAL} — {URL_GUIA}",
            f"Alíquotas municipais: {issqn.FONTE_ALIQUOTAS}",
            "Classificações nacionais: ANEXO_B-NBS2-LISTA_SERVICO_NACIONAL-SNNFSe v1.01, publicado em 22/01/2026.",
            "A interface do Portal Nacional e as regras de negócio podem mudar. Antes de utilizar o manual, confira a versão indicada no rodapé e as atualizações oficiais.",
            "Este material é orientativo e não constitui parecer fiscal ou jurídico. A classificação final depende da operação concreta e da legislação vigente.",
        ],
    )
    return bytes(pdf.output())


def nome_arquivo_manual(empresa: dict[str, Any]) -> str:
    razao = _primeiro_valor(empresa, "nome_fantasia", "razao_social", "nome")
    normalizado = unicodedata.normalize("NFKD", razao)
    seguro = "".join(char for char in normalizado if not unicodedata.combining(char))
    seguro = re.sub(r"[^a-zA-Z0-9]+", "_", seguro).strip("_").lower()
    return f"manual_nfse_{seguro or 'empresa'}.pdf"
