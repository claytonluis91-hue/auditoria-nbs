import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import backend_issqn as issqn


class BackendISSQNTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.temp.name)
        self.csv_dir = self.pasta / "csv"
        self.csv_dir.mkdir()
        self.banco = self.pasta / "issqn.sqlite3"
        with (self.csv_dir / "SP.csv").open("w", encoding="utf-8", newline="") as arquivo:
            escritor = csv.writer(arquivo, delimiter=";")
            escritor.writerow(
                [
                    "codigo_ibge",
                    "uf",
                    "nome_municipio",
                    "codigo_servico",
                    "incidencia",
                    "aliquota",
                    "dt_ini",
                    "dt_fim",
                ]
            )
            escritor.writerows(
                [
                    ["3550308", "SP", "São Paulo", "01.01.01.000", "01.01.01.000", "2", "2025-01-01T00:00:00", "2025-12-31T00:00:00"],
                    ["3550308", "SP", "São Paulo", "01.01.01.000", "01.01.01.000", "2,5", "2026-01-01T00:00:00", ""],
                    ["3550308", "SP", "São Paulo", "01.01.02.000", "01.01.02.000", "", "2026-01-01T00:00:00", ""],
                    ["3550308", "SP", "São Paulo", "02.01.01.000", "02.01.01.000", "5", "2026-01-01T00:00:00", ""],
                    ["3550308", "SP", "São Paulo", "03.01.01.000", "03.01.01.000", "5", "2026-02-01T00:00:00", "2026-01-01T00:00:00"],
                ]
            )
        self.stats = issqn.construir_base(self.csv_dir, self.banco, tamanho_lote=2)

    def tearDown(self):
        self.temp.cleanup()

    def test_normaliza_codigos_nacionais_e_item_lc116(self):
        self.assertEqual(issqn.normalizar_codigo_nacional("010101000"), "01.01.01.000")
        self.assertEqual(issqn.normalizar_codigo_nacional("01.01.01.000"), "01.01.01.000")
        self.assertEqual(issqn.prefixo_item_lc116("1.01"), "01.01.")
        self.assertEqual(issqn.prefixo_item_lc116("17,05"), "17.05.")

    def test_importacao_preserva_historico_e_ausencia_de_aliquota(self):
        self.assertEqual(self.stats.registros, 5)
        self.assertEqual(self.stats.municipios, 1)
        self.assertEqual(self.stats.servicos, 4)
        self.assertEqual(self.stats.aliquotas_ausentes, 1)
        self.assertEqual(self.stats.registros_com_fim, 2)
        self.assertEqual(self.stats.intervalos_invalidos, 1)

    def test_consulta_por_codigo_e_data_respeita_vigencia(self):
        antigo = issqn.consultar_aliquotas(
            codigo_ibge="3550308",
            codigo_servico="010101000",
            data_referencia=date(2025, 6, 1),
            caminho_banco=self.banco,
        )
        atual = issqn.consultar_aliquotas(
            codigo_ibge="3550308",
            codigo_servico="01.01.01.000",
            data_referencia="2026-09-05",
            caminho_banco=self.banco,
        )
        self.assertEqual(antigo["registros"][0]["aliquota"], 2.0)
        self.assertEqual(atual["registros"][0]["aliquota"], 2.5)

    def test_consulta_por_item_lc_retorna_classificacoes_possiveis(self):
        resultado = issqn.consultar_aliquotas(
            municipio="Sao Paulo",
            uf="sp",
            item_lc116="1.01",
            data_referencia="2026-09-05",
            caminho_banco=self.banco,
        )
        self.assertEqual(resultado["municipio"]["codigo_ibge"], "3550308")
        self.assertEqual(len(resultado["registros"]), 2)
        self.assertIsNone(resultado["registros"][1]["aliquota"])

    def test_consulta_empresa_aceita_formatos_heterogeneos(self):
        resultado = issqn.consultar_aliquotas_empresa(
            {"municipio": "São Paulo", "uf": "SP"},
            item_lc116="2.01",
            data_referencia="2026-09-05",
            caminho_banco=self.banco,
        )
        self.assertEqual(resultado["registros"][0]["codigo_servico"], "02.01.01.000")

    def test_snapshot_compactado_substitui_sqlite_no_deploy(self):
        snapshot = self.pasta / "issqn.sqlite3.gz"
        issqn.compactar_base(self.banco, snapshot)
        self.banco.unlink()
        with (
            patch.object(issqn, "CAMINHO_BANCO_PADRAO", self.banco),
            patch.object(issqn, "CAMINHO_BANCO_COMPACTADO_PADRAO", snapshot),
        ):
            resultado = issqn.consultar_aliquotas(
                codigo_ibge="3550308",
                codigo_servico="01.01.01.000",
                data_referencia="2026-09-05",
                caminho_banco=self.banco,
            )
        self.assertEqual(resultado["registros"][0]["aliquota"], 2.5)


if __name__ == "__main__":
    unittest.main()
