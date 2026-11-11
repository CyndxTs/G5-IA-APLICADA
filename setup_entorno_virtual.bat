```bat
@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Setup - G5-IA-APLICADA

cd /d "%~dp0"

echo.
echo ==========================================
echo       CONFIGURACION - G5-IA-APLICADA
echo ==========================================

echo.
echo === 1. Verificando Python 3.12 ===

set "PY312_VERSION="

for /f "tokens=1,2" %%A in ('py -3.12 -c "import sys; print(sys.version_info[0], sys.version_info[1])" 2^>nul') do (
    set "PY312_VERSION=%%A.%%B"
)

if not "!PY312_VERSION!"=="3.12" (
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

    set "PY312_VERSION="

    for /f "tokens=1,2" %%A in ('py -3.12 -c "import sys; print(sys.version_info[0], sys.version_info[1])" 2^>nul') do (
        set "PY312_VERSION=%%A.%%B"
    )

    if not "!PY312_VERSION!"=="3.12" (
        echo.
        echo [ERROR] Python 3.12 sigue sin estar disponible.
        pause
        exit /b 1
    )

    echo [OK] Python 3.12 instalado correctamente.
) else (
    echo [OK] Python 3.12 encontrado.
)

echo [INFO] Version detectada: !PY312_VERSION!

echo.
echo === 2. Verificando entorno virtual ===

if exist ".venv\Scripts\python.exe" (
    echo [INFO] Comprobando entorno virtual existente...

    ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(sys.version_info[:2] != (3,12))" >nul 2>&1

    if errorlevel 1 (
        echo [!] El entorno virtual no funciona o utiliza otra version.
        echo [INFO] Eliminando entorno virtual anterior...
        rmdir /s /q ".venv"

        if exist ".venv" (
            echo.
            echo [ERROR] No se pudo eliminar el entorno virtual anterior.
            pause
            exit /b 1
        )
    ) else (
        echo [OK] Entorno virtual existente y funcional.
    )
)

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
echo === 6. Instalando ipykernel en .venv ===

echo [INFO] Instalando ipykernel...
python -m pip install ipykernel

if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo instalar ipykernel.
    pause
    exit /b 1
)

echo [OK] ipykernel instalado dentro de .venv.

echo.
echo === 7. Verificando entorno ===

python -c "import sys, numpy, pandas, ipykernel; print('Python:', sys.version); print('Interprete:', sys.executable); print('NumPy:', numpy.__version__); print('Pandas:', pandas.__version__); print('ipykernel:', ipykernel.__version__)"

if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la verificacion del entorno.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo       CONFIGURACION COMPLETADA
echo ==========================================
echo.
echo [OK] Python 3.12 disponible.
echo [OK] Entorno virtual: .venv
echo [OK] Dependencias instaladas.
echo [OK] ipykernel instalado en .venv.
echo [OK] No se registro ningun kernel personalizado.
echo.
echo El entorno virtual permanece activado.
echo.

cmd /k
```