@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Auditoria NBS - Teste Local

cd /d "%~dp0"

echo ============================================================
echo           AUDITORIA NBS - TESTE LOCAL
echo ============================================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo [ERRO] O Python nao foi encontrado no computador.
    echo.
    echo Instale o Python e marque a opcao "Add Python to PATH".
    echo Depois, execute este arquivo novamente.
    goto :falha
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Criando ambiente isolado do programa...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERRO] Nao foi possivel criar o ambiente virtual.
        goto :falha
    )
) else (
    echo [1/4] Ambiente isolado localizado.
)

set "PYTHON_LOCAL=%CD%\.venv\Scripts\python.exe"

echo.
echo [2/4] Verificando as dependencias...
"%PYTHON_LOCAL%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERRO] Nao foi possivel instalar as dependencias.
    echo Verifique a conexao com a internet e tente novamente.
    goto :falha
)

echo.
echo [3/4] Executando os testes automatizados...
"%PYTHON_LOCAL%" -m unittest discover -s tests -v
if errorlevel 1 (
    echo.
    echo [ERRO] Um ou mais testes falharam. A aplicacao nao sera iniciada.
    goto :falha
)

echo.
echo ============================================================
echo Todos os testes foram aprovados.
echo ============================================================
echo.
echo [4/4] Iniciando a aplicacao no navegador...
echo Para encerrar, volte a esta janela e pressione Ctrl+C.
echo.

"%PYTHON_LOCAL%" -m streamlit run app_auditoria.py --server.headless false --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo [ERRO] A aplicacao foi encerrada com uma falha.
    goto :falha
)

echo.
echo Aplicacao encerrada normalmente.
pause
exit /b 0

:falha
echo.
echo O teste local nao foi concluido.
pause
exit /b 1
