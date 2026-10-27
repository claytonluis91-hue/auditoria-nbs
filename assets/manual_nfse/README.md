# Imagens do manual NFS-e

Capturas extraídas, sem edição, do **Guia do Emissor Público Nacional Web da
NFS-e — versão 1.2.1**, revisão de 27/07/2026, adicionado à pasta
`Manual - NFSe Original`.

O manual gerado identifica as 16 imagens como reproduções do guia oficial. O
arquivo `manifesto.json` relaciona cada ativo à página e ao `xref` da imagem no
PDF de origem.

As setas, círculos numerados e legendas são desenhados vetorialmente durante a
geração do PDF. As capturas permanecem intactas para preservar os textos e os
campos do portal.

Os arquivos `logo-nascel.png` e `icone-nascel.png` são ativos públicos obtidos
do site institucional do [Grupo Nascel](https://nascel.com.br/) e são usados
somente na identidade visual do manual.

Ao substituir o guia oficial:

1. revise a versão e a data em `manual_nfse.py` e neste diretório;
2. extraia novamente as telas e atualize o manifesto;
3. confira campos condicionais, textos e legendas;
4. execute `python -m unittest tests.test_manual_nfse`;
5. abra o PDF gerado e faça a revisão visual de todas as páginas.
