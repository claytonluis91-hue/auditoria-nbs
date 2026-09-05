import io
import unittest
import zipfile

import pandas as pd

import backend_fiscal as motor


class BackendFiscalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df, cls.df_indop, cls.df_regras, cls.df_cnae = motor.carregar_dados()

    def test_normaliza_itens_lc_sem_perder_casa_decimal(self):
        self.assertEqual(motor.normalizar_codigo_servico(4.1), "4.10")
        self.assertEqual(motor.normalizar_codigo_servico("04,01"), "4.01")
        self.assertEqual(motor.normalizar_codigo_servico("17.20"), "17.20")

    def test_todos_itens_cnae_possuem_correspondencia_na_base_nbs(self):
        itens_nbs = set(self.df["Item LC 116"])
        itens_cnae = set(self.df_cnae["item_lista_servico"])
        self.assertEqual(itens_cnae - itens_nbs, set())

    def test_busca_trata_caracteres_especiais_como_texto_literal(self):
        resultado = motor.buscar_cnae(self.df_cnae, "[")
        self.assertIsInstance(resultado, pd.DataFrame)
        self.assertTrue(resultado.empty)

    def test_busca_ignora_acentos(self):
        com_acento = motor.buscar_cnae(self.df_cnae, "telecomunicações")
        sem_acento = motor.buscar_cnae(self.df_cnae, "telecomunicacoes")
        self.assertEqual(set(com_acento["cnae_numeros"]), set(sem_acento["cnae_numeros"]))

    def test_consulta_por_codigo_de_servico_retorna_cnaes_e_tributos(self):
        codigos = motor.buscar_codigos_servico(self.df_cnae, "1.01")
        self.assertIn("1.01", set(codigos["item_lista_servico"]))
        resultado = motor.gerar_combinacoes_codigo_servico(
            ["1.01"], self.df_cnae, self.df, self.df_indop, self.df_regras
        )
        self.assertFalse(resultado.empty)
        self.assertTrue(resultado["Item LC 116"].eq("1.01").all())
        self.assertGreater(resultado["CNAE"].nunique(), 1)
        self.assertIn("Redução IBS (%)", resultado.columns)
        self.assertIn("Fundamento legal", resultado.columns)

    def test_consulta_exibe_reducao_vinculada_a_classificacao(self):
        regras_reduzidas = self.df_regras[
            pd.to_numeric(self.df_regras["Percentual Redução IBS"], errors="coerce").fillna(0) > 0
        ]
        linha_reduzida = self.df[self.df["cClassTrib"].isin(regras_reduzidas["CHAVE"])].iloc[0]
        cnae = self.df_cnae[
            self.df_cnae["item_lista_servico"].eq(linha_reduzida["Item LC 116"])
        ]["cnae_numeros"].iloc[0]
        resultado = motor.gerar_combinacoes_cnae_nbs(
            [cnae], self.df_cnae, self.df, self.df_indop, self.df_regras
        )
        reduzidas = resultado[resultado["cClassTrib"].isin(regras_reduzidas["CHAVE"])]
        self.assertFalse(reduzidas.empty)
        self.assertGreater(reduzidas["Redução IBS (%)"].max(), 0)
        self.assertTrue(reduzidas["Fundamento legal"].str.contains("planalto.gov.br").all())

    def test_recomendacoes_setoriais_trazem_diagnostico(self):
        diagnostico = motor.diagnostico_setor(
            "Tecnologia, informação e comunicação",
            self.df_cnae,
            self.df,
            self.df_regras,
        )
        self.assertGreater(diagnostico["cnaes"], 0)
        self.assertGreater(diagnostico["itens_lc"], 0)
        self.assertEqual(len(diagnostico["recomendacoes"]), 4)

    def test_calculo_aplica_reducao_e_creditos(self):
        resultado = motor.calcular_comparativo(
            1000,
            5,
            0.65,
            3,
            10,
            10,
            "000001",
            self.df_regras,
            ano=2033,
            credito_atual=10,
            credito_novo=20,
        )
        self.assertAlmostEqual(resultado["valor_atual"], 77.85)
        self.assertAlmostEqual(resultado["valor_novo"], 160.0)

    def test_calculo_rejeita_valor_negativo(self):
        with self.assertRaises(motor.ValidacaoFiscalError):
            motor.calcular_comparativo(
                -1, 5, 0.65, 3, 0.1, 0.9, "000001", self.df_regras, ano=2026
            )

    def test_valida_digitos_do_cnpj(self):
        self.assertTrue(motor.validar_cnpj("12.345.678/0001-95"))
        self.assertFalse(motor.validar_cnpj("12.345.678/0001-00"))
        self.assertFalse(motor.validar_cnpj("11.111.111/1111-11"))

    def test_relatorio_combina_cnae_lc_e_nbs(self):
        relatorio = motor.gerar_combinacoes_cnae_nbs(
            ["6201501"], self.df_cnae, self.df, self.df_indop
        )
        self.assertFalse(relatorio.empty)
        self.assertEqual(list(relatorio.columns), motor.COLUNAS_RELATORIO)
        self.assertTrue(relatorio["NBS"].astype(str).str.len().gt(0).all())
        self.assertTrue(relatorio["Detalhamento INDOP"].astype(str).str.len().gt(0).all())
        self.assertTrue(relatorio["Detalhamento INDOP"].str.contains("Referência no DFe").any())

    def test_resumo_agrupa_opcoes_indop(self):
        completo = motor.gerar_combinacoes_cnae_nbs(
            ["0162803", "0162899"], self.df_cnae, self.df, self.df_indop
        )
        resumo = motor.resumir_combinacoes(completo)
        self.assertLess(len(resumo), len(completo))
        self.assertEqual(list(resumo.columns), motor.COLUNAS_RESUMO)
        self.assertGreater(resumo["Quantidade INDOP"].max(), 1)
        self.assertTrue(resumo["Opções INDOP"].str.contains(",").any())

    def test_filtro_de_combinacoes_e_literal(self):
        completo = motor.gerar_combinacoes_cnae_nbs(
            ["6201501"], self.df_cnae, self.df, self.df_indop
        )
        self.assertTrue(motor.filtrar_combinacoes(completo, "[").empty)
        self.assertFalse(motor.filtrar_combinacoes(completo, "desenvolvimento").empty)

    def test_dados_empresa_sao_apresentados_como_ficha_cadastral(self):
        dados = {
            "razao_social": "Empresa de Teste Ltda.",
            "nome_fantasia": "Empresa Teste",
            "cnpj": "12345678000195",
            "descricao_situacao_cadastral": "ATIVA",
            "cnae_fiscal": 6201501,
            "cnae_fiscal_descricao": "Desenvolvimento de programas sob encomenda",
            "cnaes_secundarios": [
                {"codigo": 6202300, "descricao": "Licenciamento de programas"}
            ],
            "fonte_dados": "BrasilAPI v1",
        }
        ficha = motor.preparar_dados_empresa(dados)
        self.assertEqual(list(ficha.columns), ["Seção", "Campo", "Informação"])
        self.assertIn("Identificação", set(ficha["Seção"]))
        self.assertIn("Atividades econômicas", set(ficha["Seção"]))
        cnpj = ficha.loc[ficha["Campo"] == "CNPJ", "Informação"].iloc[0]
        self.assertEqual(cnpj, "12.345.678/0001-95")
        cnae = ficha.loc[ficha["Campo"] == "CNAE principal", "Informação"].iloc[0]
        self.assertIn("6201-5/01", cnae)

    def test_pdf_de_simulacao_e_gerado(self):
        simulacao = motor.calcular_comparativo(
            1000, 5, 0.65, 3, 0.1, 0.9, "000001", self.df_regras, ano=2026
        )
        pdf = motor.gerar_relatorio_pdf(None, simulacao, self.df.iloc[0])
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_pdf_de_combinacoes_e_gerado(self):
        relatorio = motor.gerar_combinacoes_cnae_nbs(
            ["6201501"], self.df_cnae, self.df, self.df_indop
        )
        pdf = motor.gerar_pdf_paisagem({"nome": "Empresa Árvore"}, relatorio)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_exportacao_resumida_sem_ficha_da_empresa(self):
        completo = motor.gerar_combinacoes_cnae_nbs(
            ["0162803"], self.df_cnae, self.df, self.df_indop
        )
        resumo = motor.resumir_combinacoes(completo)
        pdf = motor.gerar_pdf_paisagem({"nome": "Consulta manual"}, resumo)
        excel = motor.gerar_excel_completo(
            {"nome": "Consulta manual"}, resumo, incluir_dados_empresa=False
        )
        self.assertTrue(pdf.startswith(b"%PDF"))
        with zipfile.ZipFile(io.BytesIO(excel)) as arquivo:
            workbook_xml = arquivo.read("xl/workbook.xml").decode("utf-8")
        self.assertIn('name="Combinacoes CNAE-NBS"', workbook_xml)
        self.assertNotIn('name="Dados Empresa"', workbook_xml)

    def test_excel_formatado_possui_abas_e_filtros(self):
        relatorio = motor.gerar_combinacoes_cnae_nbs(
            ["6201501"], self.df_cnae, self.df, self.df_indop
        )
        excel = motor.gerar_excel_completo(
            {
                "razao_social": "Empresa de teste",
                "cnpj": "12.345.678/0001-95",
                "descricao_situacao_cadastral": "ATIVA",
                "cnae_fiscal": 6201501,
            },
            relatorio,
        )
        with zipfile.ZipFile(io.BytesIO(excel)) as arquivo:
            workbook_xml = arquivo.read("xl/workbook.xml").decode("utf-8")
            planilha_xml = arquivo.read("xl/worksheets/sheet2.xml").decode("utf-8")
            textos = arquivo.read("xl/sharedStrings.xml").decode("utf-8")
        self.assertIn('name="Resumo"', workbook_xml)
        self.assertIn('name="Combinacoes CNAE-NBS"', workbook_xml)
        self.assertIn('name="Dados Empresa"', workbook_xml)
        self.assertIn('topLeftCell="A2"', planilha_xml)
        self.assertIn("<autoFilter", planilha_xml)
        self.assertIn("CNAE", textos)
        self.assertIn("Detalhamento INDOP", textos)
        self.assertIn("Razão social", textos)


if __name__ == "__main__":
    unittest.main()
