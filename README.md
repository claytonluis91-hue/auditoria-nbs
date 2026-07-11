# Auditoria NBS — Reforma Tributária

Aplicação Streamlit para consulta assistida e cruzamento entre CNAE, itens da
LC 116, NBS, classificação tributária e local de incidência do IBS.

## Executar

No Windows, abra `testar_local.bat` com um duplo clique. O arquivo cria um
ambiente isolado, verifica as dependências, executa todos os testes e inicia a
aplicação no navegador quando tudo estiver correto.

Execução manual:

```powershell
python -m pip install -r requirements.txt
streamlit run app_auditoria.py
```

## Principais recursos

- fluxo persistente em quatro etapas: Empresa, Classificação, Simulação e Relatórios;
- visão resumida que agrupa opções INDOP repetidas e painel de detalhes sob demanda;
- pesquisa literal sem falhas com caracteres especiais e sem distinção de acentos;
- normalização dos itens da LC 116, preservando códigos como `4.10`;
- consulta de CNPJ com validação dos dígitos verificadores e indicação da fonte;
- combinações `CNAE → LC 116 → NBS → cClassTrib → local de incidência`;
- simulador com cenário de teste de 2026, referência estimada e cenário personalizado;
- exportação em PDF e Excel formatado, com fontes e versão das bases;
- central de relatórios com seleção de CNAEs, modo resumido/completo e geração sob demanda;
- verificação automática da integridade dos arquivos locais.

## Fluxo de uso

1. Consulte o CNPJ ou avance para a pesquisa manual.
2. Revise os candidatos agrupados por CNAE, item LC 116 e NBS.
3. Selecione um candidato e abra suas opções INDOP detalhadas.
4. Simule o cenário tributário desejado.
5. Configure e prepare o relatório resumido ou completo.

## Testes

```powershell
python -m unittest discover -s tests -v
```

## Limitação importante

O resultado é indicativo. O CNAE auxilia a localizar possibilidades, mas não
determina isoladamente a NBS. A classificação deve considerar a natureza real
do serviço, as regras gerais de interpretação, as notas explicativas e a
legislação vigente. Em caso de dúvida, deve-se avaliar a apresentação de
Solução de Consulta à Receita Federal.

As alíquotas de 17,7% de IBS e 8,8% de CBS presentes no cenário de 2033 são
parâmetros estimativos editáveis e não são apresentadas como alíquotas legais
definitivas.

## Fontes de referência

- [LC 214/2025 — texto compilado](https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214compilado.htm)
- [Painel oficial de códigos NBS](https://www.gov.br/mdic/pt-br/assuntos/sdic/comercio-e-servicos/nbs-nomenclatura-brasileira-de-servicos/painel-de-codigos-nbs/painel-de-codigos-nbs/)
