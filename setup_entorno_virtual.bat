@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Setup - G5-IA-APLICADA

cd /d "%~dp0"

rem Extensiones de VS Code a instalar (separadas por espacio)
set "EXTENSIONS=ms-python.python ms-toolsai.jupyter"

echo.
echo ==========================================
echo       CONFIGURACION - G5-IA-APLICADA
echo ==========================================

rem ==========================================
echo.
echo === 1. Verificando Visual Studio Code ===

call :detect_code

if not defined CODE_CMD (
    echo [!] Visual Studio Code no encontrado.
    echo.
    choice /C SN /M "Deseas instalar Visual Studio Code"

    if errorlevel 2 (
        echo.
        echo [!] Instalacion cancelada por el usuario.
        pause
        exit /b 1
    )

    echo.
    echo [INFO] Instalando Visual Studio Code...
    call :install_code

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo instalar Visual Studio Code.
        pause
        exit /b 1
    )

    call :detect_code

    if not defined CODE_CMD (
        echo.
        echo [ERROR] Visual Studio Code sigue sin estar disponible.
        echo         Cierra esta ventana y vuelve a ejecutar el BAT.
        pause
        exit /b 1
    )

    echo [OK] Visual Studio Code instalado correctamente.
) else (
    echo [OK] Visual Studio Code encontrado.
)

echo [INFO] CLI detectado: !CODE_CMD!
echo.
call :wait_code_closed

if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

rem ==========================================
echo.
echo === 2. Instalando extensiones de VS Code ===

for %%E in (%EXTENSIONS%) do (
    call :ensure_ext %%E

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo instalar la extension %%E.
        echo         Revisa el mensaje de arriba.
        pause
        exit /b 1
    )
)

echo [OK] Extensiones instaladas.

rem ==========================================
echo.
echo === 3. Verificando Python 3.12 ===

call :detect_py

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
    echo [INFO] Verificando el instalador de versiones de Python...

    where py >nul 2>&1

    if errorlevel 1 (
        echo [!] El instalador de versiones de Python no esta instalado.
        echo [INFO] Instalando Python install manager...
        call :install_pymanager

        if errorlevel 1 (
            echo.
            echo [ERROR] No se pudo instalar el instalador de versiones de Python.
            pause
            exit /b 1
        )

        where py >nul 2>&1

        if errorlevel 1 (
            echo.
            echo [ERROR] El instalador se instalo, pero este terminal aun no lo reconoce.
            echo         Cierra esta ventana y vuelve a ejecutar el BAT.
            pause
            exit /b 1
        )

        echo [OK] Instalador de versiones de Python instalado.
    ) else (
        echo [OK] Instalador de versiones de Python encontrado.
    )

    echo.
    echo [INFO] Instalando Python 3.12...
    py install --yes 3.12

    if errorlevel 1 (
        echo.
        echo [ERROR] No se pudo instalar Python 3.12.
        echo         Si tienes el launcher antiguo de python.org, desinstalalo
        echo         y vuelve a ejecutar este BAT.
        pause
        exit /b 1
    )

    call :detect_py

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

rem ==========================================
echo.
echo === 4. Recreando entorno virtual ===

if not exist "requirements.txt" (
    echo [ERROR] No se encontro requirements.txt.
    echo Verifica que el archivo este en la misma carpeta que este BAT.
    pause
    exit /b 1
)

if exist ".venv" (
    echo [INFO] Entorno virtual existente encontrado en la raiz del repo.
    echo [INFO] Eliminando entorno virtual anterior...
    rmdir /s /q ".venv"

    if exist ".venv" (
        echo.
        echo [ERROR] No se pudo eliminar el entorno virtual anterior.
        echo         Cierra VS Code, los notebooks y cualquier terminal que lo use.
        pause
        exit /b 1
    )

    echo [OK] Entorno virtual anterior eliminado.
) else (
    echo [INFO] No existe un entorno virtual previo.
)

echo [INFO] Creando entorno virtual .venv con Python 3.12...

py -3.12 -m venv .venv

if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo crear el entorno virtual.
    pause
    exit /b 1
)

echo [OK] Entorno virtual creado correctamente.

rem ==========================================
echo.
echo === 5. Activando entorno virtual ===

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

rem ==========================================
echo.
echo === 6. Actualizando pip ===

echo [INFO] Actualizando pip...
python -m pip install --upgrade pip

if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo actualizar pip.
    pause
    exit /b 1
)

echo [OK] pip actualizado correctamente.

rem ==========================================
echo.
echo === 7. Instalando ipykernel en .venv ===

echo [INFO] Instalando ipykernel...
python -m pip install ipykernel

if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo instalar ipykernel.
    pause
    exit /b 1
)

echo [OK] ipykernel instalado dentro de .venv.

rem ==========================================
echo.
echo === 8. Instalando librerias ===

echo [INFO] Instalando dependencias desde requirements.txt...
python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)

echo [OK] Dependencias instaladas correctamente.

rem ==========================================
echo.
echo === 9. Verificando entorno ===

python -c "import sys, numpy, pandas, ipykernel; print('Python:', sys.version); print('Interprete:', sys.executable); print('NumPy:', numpy.__version__); print('Pandas:', pandas.__version__); print('ipykernel:', ipykernel.__version__)"

if errorlevel 1 (
    echo.
    echo [ERROR] Fallo la verificacion del entorno.
    pause
    exit /b 1
)

rem ==========================================
echo.
echo === 10. Configurando VS Code para usar .venv ===

if exist ".vscode\settings.json" (
    echo [INFO] Ya existe .vscode\settings.json. No se modifica.
    echo        Verifica que python.defaultInterpreterPath apunte a .venv.
) else (
    if not exist ".vscode" mkdir ".vscode"
    call :write_workspace_settings
    echo [OK] .vscode\settings.json creado. El interprete por defecto es .venv.
)

rem ==========================================
echo.
echo === 11. Desactivando entorno virtual ===

call ".venv\Scripts\deactivate.bat" >nul 2>&1
echo [OK] Entorno virtual desactivado.

echo.
echo ==========================================
echo       CONFIGURACION COMPLETADA
echo ==========================================
echo.
echo [OK] Visual Studio Code y extensiones disponibles.
echo [OK] Python 3.12 disponible.
echo [OK] Entorno virtual recreado: .venv
echo [OK] pip actualizado.
echo [OK] ipykernel instalado en .venv.
echo [OK] Dependencias instaladas.
echo [OK] VS Code configurado para usar .venv.
echo.

rem ==========================================
echo === 12. Abriendo VS Code con el proyecto ===

echo [INFO] Se abrira en modo de confianza ^(sin Restricted Mode^) solo en esta sesion.
call "!CODE_CMD!" --disable-workspace-trust "%CD%"

if errorlevel 1 (
    echo [!] No se pudo abrir VS Code automaticamente.
    echo     Abrelo y usa Archivo ^> Abrir carpeta para elegir esta carpeta.
) else (
    echo [OK] VS Code abierto en: !CD!
)

echo.
pause
exit /b 0


rem ==========================================
rem  SUBRUTINAS
rem ==========================================

:detect_code
set "CODE_CMD="
for /f "delims=" %%C in ('where code.cmd 2^>nul') do if not defined CODE_CMD set "CODE_CMD=%%C"
if defined CODE_CMD exit /b 0
if exist "%LocalAppData%\Programs\Microsoft VS Code\bin\code.cmd" set "CODE_CMD=%LocalAppData%\Programs\Microsoft VS Code\bin\code.cmd"
if defined CODE_CMD exit /b 0
if exist "%ProgramFiles%\Microsoft VS Code\bin\code.cmd" set "CODE_CMD=%ProgramFiles%\Microsoft VS Code\bin\code.cmd"
exit /b 0

:install_code
where winget >nul 2>&1
if errorlevel 1 (
    echo [!] No se encontro winget en este equipo.
    echo     Se abrira la pagina de descarga. Instala VS Code y vuelve a ejecutar este BAT.
    start "" "https://code.visualstudio.com/download"
    exit /b 1
)
winget install -e --id Microsoft.VisualStudioCode --scope user --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 exit /b 1
exit /b 0

:ensure_ext
set "EXT=%~1"
set "EXT_LOG=%TEMP%\vscode_ext_%~1.log"
echo [INFO] Instalando %EXT%...
call :try_ext
if not errorlevel 1 goto :ext_ok
echo [!] Fallo la instalacion de %EXT%. Reintentando en 3 segundos...
timeout /t 3 /nobreak >nul
call :try_ext
if errorlevel 1 exit /b 1
:ext_ok
echo [OK] %EXT% disponible.
exit /b 0

:try_ext
call "%CODE_CMD%" --install-extension %EXT% > "%EXT_LOG%" 2>&1
findstr /i /c:"successfully installed" /c:"already installed" "%EXT_LOG%" >nul
if not errorlevel 1 exit /b 0
type "%EXT_LOG%"
exit /b 1

:wait_code_closed
tasklist /FI "IMAGENAME eq Code.exe" 2>nul | find /I "Code.exe" >nul
if errorlevel 1 (
    echo [OK] VS Code esta cerrado.
    exit /b 0
)
echo [!] VS Code esta abierto.
echo     Debe cerrarse para que las extensiones y el entorno nuevo se carguen bien.
echo     Guarda tu trabajo antes de continuar.
echo     Ejecuta este BAT desde el Explorador de archivos, no desde la terminal de VS Code.
echo.
choice /C SN /M "Deseas cerrar VS Code ahora"
if errorlevel 2 (
    echo.
    echo [!] Proceso cancelado por el usuario.
    exit /b 1
)
echo.
echo [INFO] Cerrando VS Code...
taskkill /IM Code.exe >nul 2>&1
set "WAIT_N=0"
:wait_code_loop
timeout /t 1 /nobreak >nul
tasklist /FI "IMAGENAME eq Code.exe" 2>nul | find /I "Code.exe" >nul
if errorlevel 1 goto :wait_code_done
set /a WAIT_N+=1
if !WAIT_N! lss 10 goto :wait_code_loop
echo [!] VS Code no respondio. Forzando cierre...
taskkill /F /IM Code.exe >nul 2>&1
timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq Code.exe" 2>nul | find /I "Code.exe" >nul
if not errorlevel 1 (
    echo [ERROR] No se pudo cerrar VS Code.
    exit /b 1
)
:wait_code_done
echo [OK] VS Code cerrado.
exit /b 0

:write_workspace_settings
> ".vscode\settings.json" echo {
>> ".vscode\settings.json" echo     "python.defaultInterpreterPath": "${workspaceFolder}/.venv/Scripts/python.exe"
>> ".vscode\settings.json" echo }
exit /b 0

:detect_py
set "PY312_VERSION="
for /f "tokens=1,2" %%A in ('py -3.12 -c "import sys; print(sys.version_info[0], sys.version_info[1])" 2^>nul') do set "PY312_VERSION=%%A.%%B"
exit /b 0

:install_pymanager
where winget >nul 2>&1
if errorlevel 1 (
    echo [!] No se encontro winget en este equipo.
    echo     Se abrira la pagina de descarga del Python install manager.
    echo     Instalalo y vuelve a ejecutar este BAT.
    start "" "https://www.python.org/downloads/latest/pymanager/"
    exit /b 1
)
winget install 9NQ7512CXL7T --source msstore --accept-package-agreements --accept-source-agreements
if errorlevel 1 exit /b 1
exit /b 0