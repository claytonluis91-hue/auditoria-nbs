import unittest

import manual_nfse as manual


class ManualNFSeTests(unittest.TestCase):
    def setUp(self):
        self.empresa = {
            "razao_social": "Empresa Árvore Tecnologia Ltda.",
            "nome_fantasia": "Árvore Tech",
            "cnpj": "12.345.678/0001-95",
            "codigo_municipio_ibge": "3500105",
            "municipio": "Adamantina",
            "uf": "SP",
        }

    def test_anexo_b_possui_codigos_unicos_e_descricoes(self):
        codigos = manual.carregar_codigos_servico()
        self.assertEqual(len(codigos), 338)
        self.assertEqual(len({registro["codigo"] for registro in codigos}), 338)
        self.assertIn("desenvolvimento", manual.descricao_codigo_servico("010101000").lower())

    def test_classificacoes_por_item_combinam_aliquota_municipal(self):
        resultado = manual.classificacoes_por_itens(
            ["1.03"],
            [
                {"codigo_servico": "01.03.01.000", "aliquota": 2.0},
                {"codigo_servico": "01.03.02.000", "aliquota": None},
            ],
        )
        self.assertEqual([item["codigo"] for item in resultado], ["01.03.01.000", "01.03.02.000"])
        self.assertEqual(resultado[0]["aliquota"], "2,00%")
        self.assertEqual(resultado[1]["aliquota"], "Não informada")

    def test_manual_personalizado_e_pdf_valido(self):
        pdf = manual.gerar_manual_nfse(
            self.empresa,
            ["1.01", "1.03"],
            [{"codigo_servico": "01.01.01.000", "aliquota": 2.0}],
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 250_000)

    def test_nome_do_arquivo_remove_acentos(self):
        self.assertEqual(manual.nome_arquivo_manual(self.empresa), "manual_nfse_arvore_tech.pdf")

    def test_manual_exige_cnpj_e_item(self):
        with self.assertRaises(manual.ManualNFSeError):
            manual.gerar_manual_nfse({}, ["1.01"])
        with self.assertRaises(manual.ManualNFSeError):
            manual.gerar_manual_nfse(self.empresa, [])


if __name__ == "__main__":
    unittest.main()
