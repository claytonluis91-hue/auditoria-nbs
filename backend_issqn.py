"""Importação e consulta das alíquotas municipais de ISSQN da NFS-e Nacional.

Os CSVs publicados pelo Portal Nacional são a fonte de verdade. Este módulo
gera um SQLite derivado para que o Streamlit consulte quase dois milhões de
registros sem carregar toda a base em memória a cada acesso.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import os
import re
import shutil
import sqlite3
import tempfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator


PASTA_PROJETO = Path(__file__).resolve().parent
PASTA_CSV_PADRAO = PASTA_PROJETO / "aliquotas ISSQN"
CAMINHO_BANCO_PADRAO = PASTA_CSV_PADRAO / "issqn.sqlite3"
CAMINHO_BANCO_COMPACTADO_PADRAO = PASTA_CSV_PADRAO / "issqn.sqlite3.gz"
FONTE_ALIQUOTAS = (
    "https://www.gov.br/nfse/pt-br/biblioteca/perguntas-e-respostas/aliquotas"
)
FORMATO_CODIGO_NACIONAL = re.compile(r"^\d{2}\.\d{2}\.\d{2}\.\d{3}$")


class BaseISSQNError(RuntimeError):
    """Erro de configuração, importação ou consulta da base de ISSQN."""


@dataclass(frozen=True)
class EstatisticasImportacao:
    arquivos: int
    registros: int
    municipios: int
    servicos: int
    aliquotas_ausentes: int
    registros_com_fim: int
    intervalos_invalidos: int


def _texto_busca(valor: Any) -> str:
    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(char for char in texto if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", texto).strip().casefold()


def _codigo_ibge(valor: Any) -> str:
    numeros = re.sub(r"\D", "", str(valor or ""))
    return numeros if len(numeros) == 7 else ""


def normalizar_codigo_nacional(valor: Any) -> str:
    """Normaliza o Código de Tributação Nacional para ``00.00.00.000``."""

    texto = str(valor or "").strip()
    if FORMATO_CODIGO_NACIONAL.fullmatch(texto):
        return texto
    numeros = re.sub(r"\D", "", texto)
    if len(numeros) == 9:
        return f"{numeros[:2]}.{numeros[2:4]}.{numeros[4:6]}.{numeros[6:]}"
    return ""


def prefixo_item_lc116(valor: Any) -> str:
    """Converte um item LC 116, como ``1.01``, no prefixo nacional ``01.01.``."""

    texto = str(valor or "").strip().replace(",", ".")
    partes = texto.split(".")
    if len(partes) != 2 or not all(parte.isdigit() for parte in partes):
        return ""
    item, subitem = (int(partes[0]), int(partes[1]))
    if not (0 <= item <= 99 and 0 <= subitem <= 99):
        return ""
    return f"{item:02d}.{subitem:02d}."


def _data_iso(valor: Any, *, permite_vazio: bool = False) -> str | None:
    texto = str(valor or "").strip()
    if not texto and permite_vazio:
        return None
    texto = texto[:10]
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date().isoformat()
    except ValueError as erro:
        raise BaseISSQNError(f"Data de vigência inválida: {valor!r}.") from erro


def _aliquota_decimal(valor: Any) -> float | None:
    texto = str(valor or "").strip().replace("%", "").replace(",", ".")
    if not texto:
        return None
    try:
        numero = float(texto)
    except ValueError as erro:
        raise BaseISSQNError(f"Alíquota inválida: {valor!r}.") from erro
    if not 0 <= numero <= 100:
        raise BaseISSQNError(f"Alíquota fora do intervalo esperado: {valor!r}.")
    return numero


def _criar_schema(conexao: sqlite3.Connection) -> None:
    conexao.executescript(
        """
        CREATE TABLE municipios (
            codigo_ibge TEXT PRIMARY KEY,
            uf TEXT NOT NULL,
            nome TEXT NOT NULL,
            nome_busca TEXT NOT NULL
        );

        CREATE TABLE aliquotas (
            id INTEGER PRIMARY KEY,
            codigo_ibge TEXT NOT NULL,
            codigo_servico TEXT NOT NULL,
            incidencia TEXT NOT NULL,
            aliquota REAL,
            dt_ini TEXT NOT NULL,
            dt_fim TEXT
        );

        CREATE TABLE metadados (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        );
        """
    )


def construir_base(
    pasta_csv: str | os.PathLike[str] = PASTA_CSV_PADRAO,
    caminho_banco: str | os.PathLike[str] = CAMINHO_BANCO_PADRAO,
    *,
    tamanho_lote: int = 20_000,
) -> EstatisticasImportacao:
    """Reconstrói de forma atômica o SQLite derivado dos CSVs oficiais."""

    pasta = Path(pasta_csv)
    destino = Path(caminho_banco)
    arquivos = sorted(pasta.glob("*.csv"))
    if not arquivos:
        raise BaseISSQNError(f"Nenhum CSV foi encontrado em {pasta}.")

    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(f".{destino.name}.tmp")
    if temporario.exists():
        temporario.unlink()

    registros = aliquotas_ausentes = registros_com_fim = intervalos_invalidos = 0
    municipios: dict[str, tuple[str, str, str, str]] = {}
    servicos: set[str] = set()
    lote: list[tuple[str, str, str, float | None, str, str | None]] = []
    colunas_esperadas = {
        "codigo_ibge",
        "uf",
        "nome_municipio",
        "codigo_servico",
        "incidencia",
        "aliquota",
        "dt_ini",
        "dt_fim",
    }

    conexao: sqlite3.Connection | None = None
    try:
        conexao = sqlite3.connect(temporario)
        with conexao:
            conexao.execute("PRAGMA journal_mode=OFF")
            conexao.execute("PRAGMA synchronous=OFF")
            conexao.execute("PRAGMA temp_store=MEMORY")
            _criar_schema(conexao)

            for arquivo in arquivos:
                with arquivo.open("r", encoding="utf-8-sig", newline="") as entrada:
                    leitor = csv.DictReader(entrada, delimiter=";")
                    if set(leitor.fieldnames or []) != colunas_esperadas:
                        raise BaseISSQNError(
                            f"Cabeçalho inesperado em {arquivo.name}: {leitor.fieldnames}."
                        )
                    for numero_linha, linha in enumerate(leitor, start=2):
                        try:
                            codigo_ibge = _codigo_ibge(linha["codigo_ibge"])
                            uf = str(linha["uf"] or "").strip().upper()
                            nome = str(linha["nome_municipio"] or "").strip()
                            codigo_servico = normalizar_codigo_nacional(linha["codigo_servico"])
                            incidencia = normalizar_codigo_nacional(linha["incidencia"])
                            aliquota = _aliquota_decimal(linha["aliquota"])
                            dt_ini = _data_iso(linha["dt_ini"])
                            dt_fim = _data_iso(linha["dt_fim"], permite_vazio=True)
                        except BaseISSQNError as erro:
                            raise BaseISSQNError(
                                f"{arquivo.name}, linha {numero_linha}: {erro}"
                            ) from erro
                        if not codigo_ibge or len(uf) != 2 or not nome:
                            raise BaseISSQNError(
                                f"{arquivo.name}, linha {numero_linha}: município inválido."
                            )
                        if not codigo_servico or not incidencia:
                            raise BaseISSQNError(
                                f"{arquivo.name}, linha {numero_linha}: código nacional inválido."
                            )
                        if dt_fim and dt_ini and dt_fim < dt_ini:
                            # A publicação oficial contém registros encerrados com
                            # intervalo invertido. Eles são preservados para auditoria
                            # e ficam naturalmente fora de qualquer consulta vigente.
                            intervalos_invalidos += 1

                        municipios[codigo_ibge] = (
                            codigo_ibge,
                            uf,
                            nome,
                            _texto_busca(nome),
                        )
                        servicos.add(codigo_servico)
                        aliquotas_ausentes += aliquota is None
                        registros_com_fim += dt_fim is not None
                        lote.append(
                            (
                                codigo_ibge,
                                codigo_servico,
                                incidencia,
                                aliquota,
                                dt_ini,
                                dt_fim,
                            )
                        )
                        registros += 1
                        if len(lote) >= tamanho_lote:
                            conexao.executemany(
                                """INSERT INTO aliquotas
                                   (codigo_ibge, codigo_servico, incidencia, aliquota, dt_ini, dt_fim)
                                   VALUES (?, ?, ?, ?, ?, ?)""",
                                lote,
                            )
                            lote.clear()

            if lote:
                conexao.executemany(
                    """INSERT INTO aliquotas
                       (codigo_ibge, codigo_servico, incidencia, aliquota, dt_ini, dt_fim)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    lote,
                )
            conexao.executemany(
                "INSERT INTO municipios (codigo_ibge, uf, nome, nome_busca) VALUES (?, ?, ?, ?)",
                municipios.values(),
            )
            conexao.executescript(
                """
                CREATE INDEX idx_aliquotas_consulta
                    ON aliquotas (codigo_ibge, codigo_servico, dt_ini, dt_fim);
                CREATE INDEX idx_municipios_nome
                    ON municipios (uf, nome_busca);
                """
            )
            metadados = {
                "gerado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
                "arquivos": str(len(arquivos)),
                "registros": str(registros),
                "municipios": str(len(municipios)),
                "servicos": str(len(servicos)),
                "aliquotas_ausentes": str(aliquotas_ausentes),
                "registros_com_fim": str(registros_com_fim),
                "intervalos_invalidos": str(intervalos_invalidos),
            }
            conexao.executemany(
                "INSERT INTO metadados (chave, valor) VALUES (?, ?)",
                metadados.items(),
            )
            conexao.execute("ANALYZE")
            conexao.commit()
        conexao.close()
        conexao = None
        os.replace(temporario, destino)
    except Exception:
        if conexao is not None:
            conexao.close()
        if temporario.exists():
            temporario.unlink()
        raise

    return EstatisticasImportacao(
        arquivos=len(arquivos),
        registros=registros,
        municipios=len(municipios),
        servicos=len(servicos),
        aliquotas_ausentes=aliquotas_ausentes,
        registros_com_fim=registros_com_fim,
        intervalos_invalidos=intervalos_invalidos,
    )


def compactar_base(
    caminho_banco: str | os.PathLike[str] = CAMINHO_BANCO_PADRAO,
    caminho_compactado: str | os.PathLike[str] = CAMINHO_BANCO_COMPACTADO_PADRAO,
) -> Path:
    """Cria um snapshot gzip reproduzível para distribuição no portal."""

    origem = Path(caminho_banco)
    destino = Path(caminho_compactado)
    if not origem.is_file():
        raise BaseISSQNError(f"Base SQLite não encontrada em {origem}.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_name(f".{destino.name}.tmp")
    try:
        with origem.open("rb") as entrada, temporario.open("wb") as arquivo_saida:
            with gzip.GzipFile(
                filename=origem.name,
                mode="wb",
                fileobj=arquivo_saida,
                compresslevel=6,
                mtime=0,
            ) as saida:
                shutil.copyfileobj(entrada, saida, length=1024 * 1024)
        os.replace(temporario, destino)
    except Exception:
        if temporario.exists():
            temporario.unlink()
        raise
    return destino


@lru_cache(maxsize=4)
def _descompactar_snapshot(
    caminho_compactado: str,
    tamanho: int,
    modificado_ns: int,
) -> Path:
    origem = Path(caminho_compactado)
    nome = f"auditoria_nbs_issqn_{tamanho}_{modificado_ns}.sqlite3"
    destino = Path(tempfile.gettempdir()) / nome
    if destino.is_file():
        return destino
    temporario = destino.with_name(f".{destino.name}.{os.getpid()}.tmp")
    try:
        with gzip.open(origem, "rb") as entrada, temporario.open("wb") as saida:
            shutil.copyfileobj(entrada, saida, length=1024 * 1024)
        try:
            os.replace(temporario, destino)
        except FileExistsError:
            temporario.unlink(missing_ok=True)
    except Exception:
        temporario.unlink(missing_ok=True)
        raise
    return destino


def _resolver_caminho_banco(caminho_banco: str | os.PathLike[str]) -> Path:
    caminho = Path(caminho_banco).resolve()
    if caminho.is_file():
        return caminho
    if caminho == CAMINHO_BANCO_PADRAO.resolve():
        compactado = CAMINHO_BANCO_COMPACTADO_PADRAO.resolve()
        if compactado.is_file():
            status = compactado.stat()
            return _descompactar_snapshot(
                str(compactado),
                status.st_size,
                status.st_mtime_ns,
            )
    raise BaseISSQNError(
        f"Base SQLite não encontrada em {caminho}. Execute: python backend_issqn.py"
    )


@contextmanager
def _abrir_banco(
    caminho_banco: str | os.PathLike[str],
) -> Iterator[sqlite3.Connection]:
    caminho = _resolver_caminho_banco(caminho_banco)
    conexao = sqlite3.connect(f"file:{caminho.as_posix()}?mode=ro", uri=True)
    conexao.row_factory = sqlite3.Row
    try:
        yield conexao
    finally:
        conexao.close()


def resumo_base(
    caminho_banco: str | os.PathLike[str] = CAMINHO_BANCO_PADRAO,
) -> dict[str, str]:
    with _abrir_banco(caminho_banco) as conexao:
        return {
            linha["chave"]: linha["valor"]
            for linha in conexao.execute("SELECT chave, valor FROM metadados")
        }


def _primeiro_valor(dados: dict[str, Any], chaves: Iterable[str]) -> Any:
    for chave in chaves:
        valor = dados.get(chave)
        if valor not in (None, "", [], {}):
            return valor
    return ""


def extrair_localidade_empresa(dados: dict[str, Any]) -> dict[str, str]:
    """Extrai código IBGE, município e UF de respostas heterogêneas de CNPJ."""

    codigo = _codigo_ibge(
        _primeiro_valor(
            dados,
            (
                "codigo_municipio_ibge",
                "codigo_ibge",
                "codigo_municipio",
                "municipio_ibge",
            ),
        )
    )
    municipio_valor = dados.get("municipio")
    nome = municipio_valor if isinstance(municipio_valor, str) else ""
    uf = str(_primeiro_valor(dados, ("uf", "sigla_uf")) or "").upper()

    for objeto in (municipio_valor, dados.get("endereco")):
        if not isinstance(objeto, dict):
            continue
        codigo = codigo or _codigo_ibge(
            _primeiro_valor(objeto, ("codigo_ibge", "codigo", "ibge", "id"))
        )
        nome = nome or str(_primeiro_valor(objeto, ("nome", "municipio", "cidade")) or "")
        uf_objeto = objeto.get("uf")
        if isinstance(uf_objeto, dict):
            uf_objeto = _primeiro_valor(uf_objeto, ("sigla", "codigo"))
        uf = uf or str(uf_objeto or "").upper()

    return {"codigo_ibge": codigo, "municipio": str(nome).strip(), "uf": uf.strip()}


def resolver_municipio(
    *,
    codigo_ibge: Any = "",
    municipio: Any = "",
    uf: Any = "",
    caminho_banco: str | os.PathLike[str] = CAMINHO_BANCO_PADRAO,
) -> dict[str, str] | None:
    codigo = _codigo_ibge(codigo_ibge)
    with _abrir_banco(caminho_banco) as conexao:
        if codigo:
            linha = conexao.execute(
                "SELECT codigo_ibge, uf, nome FROM municipios WHERE codigo_ibge = ?",
                (codigo,),
            ).fetchone()
        else:
            nome_busca = _texto_busca(municipio)
            sigla = str(uf or "").strip().upper()
            if not nome_busca or len(sigla) != 2:
                return None
            linha = conexao.execute(
                """SELECT codigo_ibge, uf, nome FROM municipios
                   WHERE uf = ? AND nome_busca = ?""",
                (sigla, nome_busca),
            ).fetchone()
    return dict(linha) if linha else None


def consultar_aliquotas(
    *,
    codigo_ibge: Any = "",
    municipio: Any = "",
    uf: Any = "",
    codigo_servico: Any = "",
    item_lc116: Any = "",
    data_referencia: date | str | None = None,
    caminho_banco: str | os.PathLike[str] = CAMINHO_BANCO_PADRAO,
) -> dict[str, Any]:
    """Consulta regras vigentes por município, serviço e data de competência."""

    localidade = resolver_municipio(
        codigo_ibge=codigo_ibge,
        municipio=municipio,
        uf=uf,
        caminho_banco=caminho_banco,
    )
    if not localidade:
        return {"municipio": None, "registros": []}

    referencia = data_referencia or date.today()
    if isinstance(referencia, date):
        referencia_iso = referencia.isoformat()
    else:
        referencia_iso = _data_iso(referencia)

    codigo = normalizar_codigo_nacional(codigo_servico)
    prefixo = prefixo_item_lc116(item_lc116)
    if codigo_servico and not codigo:
        raise BaseISSQNError("Informe o Código de Tributação Nacional com 9 dígitos.")
    if item_lc116 and not prefixo:
        raise BaseISSQNError("Informe o item da LC 116 no formato 1.01.")

    filtros = [
        "a.codigo_ibge = ?",
        "a.dt_ini <= ?",
        "(a.dt_fim IS NULL OR a.dt_fim >= ?)",
    ]
    parametros: list[Any] = [localidade["codigo_ibge"], referencia_iso, referencia_iso]
    if codigo:
        filtros.append("a.codigo_servico = ?")
        parametros.append(codigo)
    elif prefixo:
        filtros.append("a.codigo_servico LIKE ?")
        parametros.append(f"{prefixo}%")

    sql = f"""
        SELECT a.codigo_servico, a.incidencia, a.aliquota, a.dt_ini, a.dt_fim
        FROM aliquotas a
        WHERE {' AND '.join(filtros)}
        ORDER BY a.codigo_servico, a.dt_ini DESC, a.id DESC
    """
    with _abrir_banco(caminho_banco) as conexao:
        linhas = [dict(linha) for linha in conexao.execute(sql, parametros)]
    return {
        "municipio": localidade,
        "data_referencia": referencia_iso,
        "registros": linhas,
    }


def consultar_aliquotas_empresa(
    dados_empresa: dict[str, Any],
    **filtros: Any,
) -> dict[str, Any]:
    localidade = extrair_localidade_empresa(dados_empresa)
    return consultar_aliquotas(
        codigo_ibge=localidade["codigo_ibge"],
        municipio=localidade["municipio"],
        uf=localidade["uf"],
        **filtros,
    )


def _main() -> None:
    parser = argparse.ArgumentParser(description="Constrói o SQLite de alíquotas ISSQN.")
    parser.add_argument("--csv-dir", default=str(PASTA_CSV_PADRAO))
    parser.add_argument("--database", default=str(CAMINHO_BANCO_PADRAO))
    parser.add_argument(
        "--compactar",
        action="store_true",
        help="Também gera issqn.sqlite3.gz para distribuição no portal.",
    )
    argumentos = parser.parse_args()
    estatisticas = construir_base(argumentos.csv_dir, argumentos.database)
    print(
        "Base ISSQN criada: "
        f"{estatisticas.registros:,} registros, "
        f"{estatisticas.municipios:,} municípios e "
        f"{estatisticas.servicos:,} códigos de serviço."
    )
    if argumentos.compactar:
        compactado = compactar_base(
            argumentos.database,
            f"{argumentos.database}.gz",
        )
        print(f"Snapshot compactado criado em {compactado}.")


if __name__ == "__main__":
    _main()
