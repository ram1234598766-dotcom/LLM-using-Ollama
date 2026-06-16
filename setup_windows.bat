@echo off
:: ============================================================
::  LocalAI — One-click Windows 11 Setup
::  Run this script ONCE before using main.py
:: ============================================================
title LocalAI Setup
color 0B

echo.
echo  ============================================================
echo    LocalAI — Windows 11 Setup Script
echo  ============================================================
echo.

:: ── 1. Check Python ───────────────────────────────────────────
echo [1/5] Checking Python...
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo  ERROR: Python is not installed or not in PATH.
    echo  Download Python 3.11+ from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during install.
    pause
    exit /b 1
)
python --version
echo  Python found.
echo.

:: ── 2. Upgrade pip ────────────────────────────────────────────
echo [2/5] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo  pip upgraded.
echo.

:: ── 3. Install Python dependencies ───────────────────────────
echo [3/5] Installing Python packages (this may take a few minutes)...
pip install -r requirements.txt
IF ERRORLEVEL 1 (
    echo  ERROR: Package installation failed.
    echo  Try running: pip install -r requirements.txt
    pause
    exit /b 1
)
echo  All packages installed.
echo.

:: ── 4. Install Ollama ─────────────────────────────────────────
echo [4/5] Checking Ollama (local LLM runtime)...
ollama --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo  Ollama not found. Downloading installer...
    echo.
    :: Download Ollama installer using PowerShell
    powershell -Command ^
        "Invoke-WebRequest -Uri 'https://ollama.com/download/OllamaSetup.exe' ^
         -OutFile '%TEMP%\OllamaSetup.exe'"
    echo  Running Ollama installer...
    start /wait %TEMP%\OllamaSetup.exe
    echo  Ollama installed. Waiting for it to start...
    timeout /t 5 /nobreak >nul
) ELSE (
    echo  Ollama already installed.
)
echo.

:: ── 5. Pull the LLM model ─────────────────────────────────────
echo [5/5] Downloading AI model (llama3.2 ~ 2GB, one-time download)...
echo  This will take a few minutes depending on your connection...
echo.
start /min ollama serve
timeout /t 3 /nobreak >nul
ollama pull llama3.2
IF ERRORLEVEL 1 (
    echo  Trying fallback model: mistral...
    ollama pull mistral
)
echo.
echo  Model downloaded.

:: ── Done ──────────────────────────────────────────────────────
echo.
echo  ============================================================
echo    Setup Complete!
echo  ============================================================
echo.
echo  To start LocalAI:
echo    python main.py
echo.
echo  In PyCharm:
echo    1. Open this folder as a project
echo    2. Set Python interpreter (File > Settings > Python Interpreter)
echo    3. Right-click main.py and select "Run main"
echo.
pause
