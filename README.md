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

- fluxo persistente em cinco etapas: Empresa, Consulta individual, Simulação, Relatórios e Recomendações;
- consulta individual em dois sentidos: `CNAE → código LC 116` e `código LC 116 → CNAE`;
- painel em cascata após a consulta do CNPJ: Serviço LC 116 → CNAE da empresa → cClassTrib → NBS;
- reduções de IBS e CBS, tipo de alíquota e fundamento legal visíveis no resultado, na simulação e nas exportações;
- recomendações por setor de serviço, com roteiro de revisão e candidatos a redução;
- consulta das alíquotas municipais de ISSQN por código IBGE, Código de Tributação Nacional e data de competência;
- geração de manual personalizado do Emissor Nacional em PDF, com dados do CNPJ, passo a passo ilustrado e tabela de códigos de serviço aplicáveis;
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
2. Escolha a consulta por CNAE ou por código de serviço e revise os candidatos.
3. Selecione um candidato e abra suas opções INDOP detalhadas.
4. Confira reduções, tipo de alíquota e fundamento legal da cClassTrib.
5. Simule o cenário tributário desejado e prepare os relatórios.
6. Consulte o roteiro de recomendações do setor.
7. Confira a alíquota municipal vigente e as possíveis classificações nacionais na etapa ISSQN municipal.
8. Selecione os itens da LC 116 e gere o manual personalizado para baixar em PDF.

## Base municipal de ISSQN

Os CSVs oficiais devem permanecer na pasta `aliquotas ISSQN`. Para gerar a
base SQLite otimizada usada pelo portal, execute:

```powershell
python backend_issqn.py --compactar
```

O arquivo `aliquotas ISSQN/issqn.sqlite3` é derivado, pode ser reconstruído a
qualquer momento e não deve ser versionado. A importação preserva o histórico
de vigência e mantém alíquotas vazias como “não informadas”, sem convertê-las
em zero. A quantidade exibida como “municípios com registros” reflete o
conteúdo efetivamente encontrado nos CSVs, que pode ser menor do que o total
de municípios mencionado na página de publicação.

Para implantação, versione somente o snapshot `issqn.sqlite3.gz` (cerca de
33 MB nesta publicação). Quando o SQLite local não existe, o portal
descompacta esse snapshot automaticamente na pasta temporária do servidor.

## Manual personalizado da NFS-e

Após consultar um CNPJ, acesse **ISSQN municipal**, confira o município e a
data de competência e selecione até dez itens da LC 116. O portal gera um PDF
com:

- identificação da empresa e da localidade considerada;
- tabela com todas as possibilidades da consulta empresarial para os serviços escolhidos, relacionando LC 116, CNAE, cClassTrib, anexo e NBS;
- passo a passo de emissão no Emissor Público Nacional Web;
- capturas do guia oficial, preservadas sem edição;
- todas as classificações nacionais compatíveis com os itens selecionados;
- alíquota municipal vigente quando ela estiver disponível na base oficial.

A lista de 338 códigos e descrições em `codigo_servico_nacional.json` foi
extraída do Anexo B da documentação técnica nacional. O manual é orientativo:
a classificação deve ser confirmada de acordo com o serviço efetivamente
prestado e as regras do município.

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
- [Alíquotas de ISSQN do Sistema Nacional da NFS-e](https://www.gov.br/nfse/pt-br/biblioteca/perguntas-e-respostas/aliquotas)
- [Guia do Emissor Público Nacional Web](https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/guia-emissorpubliconacionalweb_snnfse-ern-v12.pdf)
