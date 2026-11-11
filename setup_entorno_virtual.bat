
@echo off
setlocal
title Setup - G5-IA-APLICADA

cd /d "%~dp0"

echo.
echo ==========================================
echo       CONFIGURACION - G5-IA-APLICADA
echo ==========================================

echo.
echo === 1. Verificando Python 3.12 ===

py -3.12 --version >nul 2>&1

if errorlevel 1 (
    echo [!] Python 3.12 no encontrado.
    echo.
    choice /C SN /M "Deseas instalar Python 3.12"

    if errorlevel 2 (
        echo.
        echo [!] Instalacion cancelada por el usuario.
        pause
        exit /b 1
    )

    echo.
    echo [INFO] Instalando Python 3.12...
    py install 3.12

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo instalar Python 3.12.
        pause
        exit /b 1
    )

    echo.
    echo [OK] Python 3.12 instalado correctamente.
) else (
    echo [OK] Python 3.12 encontrado.
    echo [INFO] Version detectada:
    py -3.12 --version
)

echo.
echo === 2. Creando entorno virtual ===

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creando entorno virtual .venv...
    py -3.12 -m venv .venv

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )

    echo [OK] Entorno virtual creado correctamente.
) else (
    echo [OK] Ya existe el entorno virtual .venv.
)

echo.
echo === 3. Activando entorno virtual ===

call ".venv\Scripts\activate.bat"

if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

echo [OK] Entorno virtual activado.
echo [INFO] Python que se utilizara:
python --version
echo [INFO] Ruta del interprete:
where python

echo.
echo === 4. Actualizando pip ===

echo [INFO] Actualizando pip...
python -m pip install --upgrade pip

if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo actualizar pip.
    pause
    exit /b 1
)

echo [OK] pip actualizado correctamente.

echo.
echo === 5. Instalando librerias ===

if not exist "requirements.txt" (
    echo [ERROR] No se encontro requirements.txt.
    echo Verifica que el archivo este en la misma carpeta que este BAT.
    pause
    exit /b 1
)

echo [INFO] Instalando dependencias desde requirements.txt...
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo [OK] Dependencias instaladas correctamente.

echo.
echo === 6. Instalando soporte para notebooks de VS Code ===

echo [INFO] Instalando ipykernel...
python -m pip install ipykernel

if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo instalar ipykernel.
    pause
    exit /b 1
)

echo.
echo [INFO] Registrando kernel del proyecto...
python -m ipykernel install --sys-prefix --name g5-ia-aplicada --display-name "Python 3.12 (G5-IA-APLICADA)"

if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo registrar el kernel.
    pause
    exit /b 1
)

echo [OK] Kernel registrado correctamente.

echo.
echo ==========================================
echo       CONFIGURACION COMPLETADA
echo ==========================================
echo.
echo [OK] Python 3.12 disponible.
echo [OK] Entorno virtual: .venv
echo [OK] Dependencias instaladas.
echo [OK] ipykernel instalado.
echo [OK] Kernel de VS Code registrado.
echo.
echo En VS Code selecciona:
echo Python 3.12 (G5-IA-APLICADA)
echo.
echo El entorno virtual permanece activado.
echo.

cmd /k
