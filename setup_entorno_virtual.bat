```bat
@echo off
setlocal
title Setup - G5-IA-APLICADA

cd /d "%~dp0"

echo.
echo === 1. Verificando Python 3.12 ===

py -3.12 --version >nul 2>&1

if errorlevel 1 (
    echo Python 3.12 no esta instalado.
    choice /C SN /M "Deseas instalar Python 3.12"
    if errorlevel 2 exit /b 1

    py install 3.12

    if errorlevel 1 (
        echo ERROR: No se pudo instalar Python 3.12.
        pause
        exit /b 1
    )
)

echo.
echo === 2. Creando entorno virtual ===

if not exist ".venv\Scripts\python.exe" (
    py -3.12 -m venv .venv
    if errorlevel 1 (
        echo ERROR: No se pudo crear .venv.
        pause
        exit /b 1
    )
)

echo.
echo === 3. Activando entorno virtual ===

call ".venv\Scripts\activate.bat"

if errorlevel 1 (
    echo ERROR: No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

echo.
echo === 4. Instalando librerias ===

python -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: No se pudo actualizar pip.
    pause
    exit /b 1
)

python -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo.
echo Configuracion completada correctamente.
echo Entorno virtual: .venv
echo.

cmd /k
```
