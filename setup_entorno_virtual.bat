@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Setup - G5-IA-APLICADA

cd /d "%~dp0"

rem ============================================
rem  CONFIGURACION (editar aqui si hace falta)
rem ============================================
set "VENV_NAME=.venv"
set "EXTENSIONS=ms-python.python ms-toolsai.jupyter"
set "VERIFY_MODULES=numpy pandas openpyxl lxml matplotlib seaborn sklearn ipykernel"

rem Estado del proceso
set "HAS_VSC=0"
set "EXT_OK=0"
set "VSC_CONFIGURED=0"
set "END_MSG="
set "END_MSG2="

echo.
echo ==========================================
echo       CONFIGURACION - G5-IA-APLICADA
echo ==========================================
echo.
echo Este asistente prepara el equipo para ejecutar el proyecto:
echo   winget, Visual Studio Code, extensiones, Python 3.12,
echo   entorno virtual %VENV_NAME% y librerias.


rem ============================================
rem  WINGET
rem ============================================
echo.
echo === Validando winget ===
echo [INFO] Validando winget...

where winget >nul 2>&1

if errorlevel 1 (
    echo [ERROR] No se encontro winget en este equipo.
    echo.
    echo winget es necesario para instalar Visual Studio Code y Python.
    echo Puedes instalarlo de cualquiera de estas formas:
    echo.
    echo   1. Microsoft Store: busca "App Installer" e instalalo o actualizalo.
    echo   2. Descarga directa: https://aka.ms/getwinget
    echo   3. PowerShell:
    echo      Add-AppxPackage -RegisterByFamilyName -MainPackage Microsoft.DesktopAppInstaller_8wekyb3d8bbwe
    echo.
    echo Despues de instalarlo, vuelve a ejecutar este BAT.
    set "END_MSG=[ERROR] Proceso detenido: falta winget."
    goto :end_error
)

echo [OK] winget encontrado.


rem ============================================
rem  VISUAL STUDIO CODE - INSTALACION
rem ============================================
echo.
echo === Validando Visual Studio Code ===
echo [INFO] Validando si Visual Studio Code esta instalado...

call :detect_code

if defined CODE_CMD (
    echo [OK] Visual Studio Code encontrado.
    set "HAS_VSC=1"
) else (
    echo [AVISO] Visual Studio Code no encontrado.
    echo.
    choice /C SN /M "Deseas instalar Visual Studio Code"

    if errorlevel 2 (
        echo.
        echo [AVISO] Continuaras sin Visual Studio Code.
        echo         Este instalador esta pensado para ejecutar el repositorio en VS Code.
        echo         No es obligatorio, pero ya no se instalaran las extensiones del editor,
        echo         no se configurara el interprete y no se abrira el proyecto al terminar.
        echo [INFO] Continuando con el proceso...
    ) else (
        echo.
        echo [INFO] Instalando Visual Studio Code...
        call :run_with_retry :do_install_code "instalar Visual Studio Code"

        if errorlevel 1 (
            set "END_MSG=[ERROR] No se pudo instalar Visual Studio Code."
            set "END_MSG2=Instalalo manualmente desde https://code.visualstudio.com y vuelve a ejecutar este BAT."
            goto :end_error
        )

        call :detect_code

        if not defined CODE_CMD (
            set "END_MSG=[ERROR] Visual Studio Code se instalo, pero no se encontro su ejecutable."
            set "END_MSG2=Cierra esta ventana y vuelve a ejecutar este BAT."
            goto :end_error
        )

        set "HAS_VSC=1"
        echo [OK] Visual Studio Code instalado correctamente.
        echo [INFO] No se abrira ahora. Se abrira al final del proceso.
    )
)


rem ============================================
rem  VISUAL STUDIO CODE - DEBE ESTAR CERRADO
rem ============================================
echo.
echo === Validando que Visual Studio Code este cerrado ===

if "!HAS_VSC!"=="1" (
    echo [INFO] Validando que Visual Studio Code no este en ejecucion...

    tasklist /FI "IMAGENAME eq Code.exe" 2>nul | find /I "Code.exe" >nul

    if errorlevel 1 (
        echo [OK] Visual Studio Code esta cerrado.
    ) else (
        echo [AVISO] Visual Studio Code esta abierto.
        echo         Debe cerrarse para continuar y que las extensiones se instalen correctamente.
        echo         Guarda tu trabajo antes de responder.
        echo         Ejecuta este BAT desde el Explorador de archivos, no desde la terminal de VS Code.
        echo.
        choice /C SN /M "Deseas cerrar Visual Studio Code ahora"

        if errorlevel 2 (
            set "END_MSG=[AVISO] Proceso cancelado: Visual Studio Code debe estar cerrado para continuar."
            goto :end_error
        )

        echo.
        echo [INFO] Cerrando Visual Studio Code...
        call :close_code

        if errorlevel 1 (
            set "END_MSG=[ERROR] No se pudo cerrar Visual Studio Code."
            set "END_MSG2=Cierralo manualmente y vuelve a ejecutar este BAT."
            goto :end_error
        )

        echo [OK] Visual Studio Code cerrado.
    )
) else (
    echo [INFO] Visual Studio Code no esta instalado, no hay nada que cerrar.
    echo [INFO] Continuando con el proceso...
)


rem ============================================
rem  VISUAL STUDIO CODE - EXTENSIONES
rem ============================================
echo.
echo === Instalando extensiones de Visual Studio Code ===

if "!HAS_VSC!"=="1" (
    echo [INFO] Instalando extensiones para Python y Jupyter...

    for %%E in (%EXTENSIONS%) do (
        set "CUR_EXT=%%E"
        echo [INFO] Instalando extension %%E...
        call :run_with_retry :do_install_ext "instalar la extension %%E"

        if errorlevel 1 (
            set "END_MSG=[ERROR] No se pudo instalar la extension %%E."
            set "END_MSG2=Revisa el mensaje de arriba y tu conexion a internet."
            goto :end_error
        )

        echo [OK] Extension %%E lista.
    )

    set "EXT_OK=1"
    echo [OK] Extensiones instaladas.
) else (
    echo [AVISO] Como Visual Studio Code no esta instalado, no se instalaran
    echo         las extensiones de Python ni de Jupyter.
    echo [INFO] Continuando con el proceso...
)


rem ============================================
rem  PYTHON 3.12
rem ============================================
echo.
echo === Validando Python 3.12 ===
echo [INFO] El entorno del proyecto usa Python 3.12 por compatibilidad con sus librerias.
echo [INFO] Validando Python 3.12...

call :detect_py

if "!PY312_VERSION!"=="3.12" (
    echo [OK] Python 3.12 encontrado.
) else (
    echo [AVISO] Python 3.12 no encontrado.
    echo.
    choice /C SN /M "Deseas instalar Python 3.12"

    if errorlevel 2 (
        echo.
        echo [AVISO] Python 3.12 es necesario para este proyecto.
        echo         Las librerias del proyecto requieren esa version, por eso
        echo         no se puede continuar sin instalarlo.
        set "END_MSG=[AVISO] Proceso cancelado: se requiere Python 3.12 para continuar."
        goto :end_error
    )

    echo.
    echo [INFO] Preparando la instalacion de Python...

    where py >nul 2>&1

    if errorlevel 1 (
        echo [INFO] Instalando las herramientas necesarias de Python...
        call :run_with_retry :do_install_pymanager "instalar las herramientas de Python"

        if errorlevel 1 (
            set "END_MSG=[ERROR] No se pudieron instalar las herramientas necesarias de Python."
            set "END_MSG2=Instalalas desde https://www.python.org/downloads/latest/pymanager/ y vuelve a ejecutar este BAT."
            goto :end_error
        )

        where py >nul 2>&1

        if errorlevel 1 (
            set "END_MSG=[ERROR] Las herramientas se instalaron, pero esta ventana aun no las reconoce."
            set "END_MSG2=Cierra esta ventana y vuelve a ejecutar este BAT."
            goto :end_error
        )

        echo [OK] Herramientas de Python instaladas.
    )

    echo [INFO] Instalando Python 3.12...
    call :run_with_retry :do_install_py312 "instalar Python 3.12"

    if errorlevel 1 (
        set "END_MSG=[ERROR] No se pudo instalar Python 3.12."
        set "END_MSG2=Si tienes el launcher antiguo de python.org, desinstalalo y vuelve a ejecutar este BAT."
        goto :end_error
    )

    call :detect_py

    if not "!PY312_VERSION!"=="3.12" (
        set "END_MSG=[ERROR] Python 3.12 sigue sin estar disponible."
        set "END_MSG2=Cierra esta ventana y vuelve a ejecutar este BAT."
        goto :end_error
    )

    echo [OK] Python 3.12 instalado correctamente.
)

echo [INFO] Version detectada: !PY312_VERSION!


rem ============================================
rem  ENTORNO VIRTUAL - VALIDAR Y ELIMINAR EXISTENTE
rem ============================================
echo.
echo === Validando entorno virtual existente ===
echo [INFO] Validando requirements.txt...

if not exist "requirements.txt" (
    set "END_MSG=[ERROR] No se encontro requirements.txt."
    set "END_MSG2=Verifica que el archivo este en la misma carpeta que este BAT."
    goto :end_error
)

echo [OK] requirements.txt encontrado.
echo [INFO] Buscando entornos virtuales existentes en la raiz del repo...

set "VENV_FOUND=0"

for /d %%D in (*) do (
    if exist "%%D\pyvenv.cfg" (
        set /a VENV_FOUND+=1
        echo [AVISO] Entorno virtual encontrado: %%D
        echo [INFO] Eliminando %%D...
        rmdir /s /q "%%D"

        if exist "%%D" (
            set "END_MSG=[ERROR] No se pudo eliminar el entorno virtual %%D."
            set "END_MSG2=Cierra VS Code, los notebooks y cualquier terminal que lo use, y vuelve a ejecutar este BAT."
            goto :end_error
        )

        echo [OK] Entorno virtual %%D eliminado.
    )
)

if "!VENV_FOUND!"=="0" (
    echo [OK] No existian entornos virtuales previos.
) else (
    echo [OK] Entornos virtuales anteriores eliminados: !VENV_FOUND!
)

echo [INFO] Solo quedara el nuevo entorno %VENV_NAME%.

rem ============================================
rem  ENTORNO VIRTUAL - CREACION
rem ============================================
echo.
echo === Creando entorno virtual ===
echo [INFO] Creando entorno virtual %VENV_NAME% con Python 3.12...

call :run_with_retry :do_create_venv "crear el entorno virtual"

if errorlevel 1 (
    set "END_MSG=[ERROR] No se pudo crear el entorno virtual %VENV_NAME%."
    goto :end_error
)

echo [OK] Entorno virtual %VENV_NAME% creado correctamente.


rem ============================================
rem  DENTRO DEL ENTORNO VIRTUAL
rem ============================================
echo.
echo === Preparando el entorno virtual ===
echo [INFO] Activando el entorno virtual para la instalacion...

call "%VENV_NAME%\Scripts\activate.bat"

if errorlevel 1 (
    set "END_MSG=[ERROR] No se pudo activar el entorno virtual."
    goto :end_error
)

echo [OK] Entorno virtual activado.
echo [INFO] Interprete que se utilizara:
"%VENV_NAME%\Scripts\python.exe" --version
echo   %CD%\%VENV_NAME%\Scripts\python.exe

echo.
echo [INFO] Actualizando pip...
call :run_with_retry :do_pip "actualizar pip"

if errorlevel 1 (
    set "END_MSG=[ERROR] No se pudo actualizar pip."
    goto :end_error
)

echo [OK] pip actualizado correctamente.

echo.
echo [INFO] Instalando ipykernel...
call :run_with_retry :do_ipykernel "instalar ipykernel"

if errorlevel 1 (
    set "END_MSG=[ERROR] No se pudo instalar ipykernel."
    goto :end_error
)

echo [OK] ipykernel instalado correctamente.

echo.
echo [INFO] Instalando librerias desde requirements.txt...
echo [INFO] Esto puede tardar varios minutos, TensorFlow es una libreria pesada.
call :run_with_retry :do_requirements "instalar las librerias de requirements.txt"

if errorlevel 1 (
    set "END_MSG=[ERROR] No se pudieron instalar las librerias de requirements.txt."
    goto :end_error
)

echo [OK] Librerias instaladas correctamente.


rem ============================================
rem  VISUAL STUDIO CODE - INTERPRETE POR DEFECTO
rem ============================================
echo.
echo === Configurando el interprete en Visual Studio Code ===

if "!HAS_VSC!"=="1" (
    echo [INFO] Configurando %VENV_NAME% como interprete por defecto en VS Code...
    call :configure_vscode
) else (
    echo [AVISO] Visual Studio Code no esta instalado.
    echo         No se configurara %VENV_NAME% como interprete predeterminado.
    echo         En tu editor, selecciona manualmente:
    echo         !CD!\%VENV_NAME%\Scripts\python.exe
)


rem ============================================
rem  DESACTIVAR ENTORNO VIRTUAL
rem ============================================
echo.
echo === Desactivando entorno virtual ===
echo [INFO] El entorno virtual no se usara en esta terminal. Desactivando...

call "%VENV_NAME%\Scripts\deactivate.bat" >nul 2>&1

echo [OK] Entorno virtual desactivado.


rem ============================================
rem  VERIFICACION Y RESUMEN
rem ============================================
echo.
echo === Verificando instalacion ===
echo [INFO] Verificando Python y librerias en %VENV_NAME%...

"%VENV_NAME%\Scripts\python.exe" -c "import importlib, sys; print('  Python:', sys.version.split()[0]); print('  Interprete:', sys.executable); [print('  ' + m + ':', getattr(importlib.import_module(m), '__version__', 'ok')) for m in sys.argv[1:]]" %VERIFY_MODULES%

if errorlevel 1 (
    set "END_MSG=[ERROR] Fallo la verificacion del entorno."
    set "END_MSG2=Alguna libreria no se pudo importar. Revisa el mensaje de arriba."
    goto :end_error
)

echo [OK] Verificacion completada.

echo.
echo ==========================================
echo       RESUMEN
echo ==========================================
echo.
echo [OK] winget disponible.
if "!HAS_VSC!"=="1" (echo [OK] Visual Studio Code disponible.) else (echo [AVISO] Visual Studio Code no instalado.)
if "!EXT_OK!"=="1" (echo [OK] Extensiones de Python y Jupyter instaladas.) else (echo [AVISO] Extensiones no instaladas.)
echo [OK] Python !PY312_VERSION! disponible.
echo [OK] Entorno virtual: %VENV_NAME%
echo [OK] pip actualizado, ipykernel y librerias instaladas.
if "!VSC_CONFIGURED!"=="1" (echo [OK] VS Code usa %VENV_NAME% como interprete por defecto.) else (echo [AVISO] Interprete por defecto no configurado en VS Code.)
echo [OK] El entorno virtual quedo desactivado en esta terminal.


rem ============================================
rem  ABRIR VISUAL STUDIO CODE
rem ============================================
echo.
echo === Abriendo el proyecto ===

if "!HAS_VSC!"=="1" (
    echo [INFO] Abriendo el repositorio en Visual Studio Code en modo de confianza...
    call "!CODE_CMD!" --disable-workspace-trust "!CD!"

    if errorlevel 1 (
        echo [AVISO] No se pudo abrir VS Code automaticamente.
        echo         Abrelo y usa Archivo - Abrir carpeta para elegir esta carpeta.
    ) else (
        echo [OK] Visual Studio Code abierto en: !CD!
        echo [INFO] El proyecto se abrio sin Restricted Mode solo para esta sesion.
    )
) else (
    echo [INFO] Visual Studio Code no esta instalado, el proyecto no se abrira.
)

echo.
echo ==========================================
echo       PROCESO FINALIZADO
echo ==========================================
echo.
echo Presiona cualquier tecla para cerrar esta ventana...
pause >nul
exit /b 0


rem ============================================
rem  FIN CON ERROR O CANCELACION
rem ============================================
:end_error
echo.
echo !END_MSG!
if defined END_MSG2 echo !END_MSG2!
echo.
echo El proceso se ha detenido.
echo Presiona cualquier tecla para cerrar esta ventana...
pause >nul
exit /b 1


rem ============================================
rem  SUBRUTINAS
rem ============================================

rem Ejecuta una subrutina y, si falla, la reintenta una sola vez.
rem %1 = etiqueta de la subrutina   %2 = descripcion para el mensaje
:run_with_retry
call %~1
if not errorlevel 1 exit /b 0
echo [AVISO] Fallo al %~2. Reintentando una vez en 3 segundos...
timeout /t 3 /nobreak >nul
call %~1
if not errorlevel 1 exit /b 0
exit /b 1

:detect_code
set "CODE_CMD="
for /f "delims=" %%C in ('where code.cmd 2^>nul') do if not defined CODE_CMD set "CODE_CMD=%%C"
if defined CODE_CMD exit /b 0
if exist "%LocalAppData%\Programs\Microsoft VS Code\bin\code.cmd" set "CODE_CMD=%LocalAppData%\Programs\Microsoft VS Code\bin\code.cmd"
if defined CODE_CMD exit /b 0
if exist "%ProgramFiles%\Microsoft VS Code\bin\code.cmd" set "CODE_CMD=%ProgramFiles%\Microsoft VS Code\bin\code.cmd"
exit /b 0

:do_install_code
winget install -e --id Microsoft.VisualStudioCode --scope user --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 exit /b 1
exit /b 0

:close_code
taskkill /IM Code.exe >nul 2>&1
set "WAIT_N=0"
:close_wait
timeout /t 1 /nobreak >nul
tasklist /FI "IMAGENAME eq Code.exe" 2>nul | find /I "Code.exe" >nul
if errorlevel 1 exit /b 0
set /a WAIT_N+=1
if !WAIT_N! lss 10 goto :close_wait
echo [AVISO] Visual Studio Code no respondio. Forzando cierre...
taskkill /F /IM Code.exe >nul 2>&1
timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq Code.exe" 2>nul | find /I "Code.exe" >nul
if errorlevel 1 exit /b 0
exit /b 1

:do_install_ext
set "EXT_LOG=%TEMP%\vscode_ext_%CUR_EXT%.log"
call "%CODE_CMD%" --install-extension %CUR_EXT% > "%EXT_LOG%" 2>&1
findstr /i /c:"successfully installed" /c:"already installed" "%EXT_LOG%" >nul
if not errorlevel 1 exit /b 0
type "%EXT_LOG%"
exit /b 1

:detect_py
set "PY312_VERSION="
for /f "tokens=1,2" %%A in ('py -3.12 -c "import sys; print(sys.version_info[0], sys.version_info[1])" 2^>nul') do set "PY312_VERSION=%%A.%%B"
exit /b 0

:do_install_pymanager
winget install 9NQ7512CXL7T --source msstore --accept-package-agreements --accept-source-agreements
if errorlevel 1 exit /b 1
exit /b 0

:do_install_py312
py install --yes 3.12
if errorlevel 1 exit /b 1
exit /b 0

:do_create_venv
py -3.12 -m venv "%VENV_NAME%"
if errorlevel 1 exit /b 1
if not exist "%VENV_NAME%\Scripts\python.exe" exit /b 1
exit /b 0

:do_pip
"%VENV_NAME%\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
exit /b 0

:do_ipykernel
"%VENV_NAME%\Scripts\python.exe" -m pip install ipykernel
if errorlevel 1 exit /b 1
exit /b 0

:do_requirements
"%VENV_NAME%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
exit /b 0

rem Crea o actualiza .vscode\settings.json para que el interprete por defecto sea el nuevo entorno.
:configure_vscode
set "SETTINGS=.vscode\settings.json"
if not exist ".vscode" mkdir ".vscode"
if not exist "%SETTINGS%" goto :cfg_write
findstr /c:"%VENV_NAME%" "%SETTINGS%" >nul
if not errorlevel 1 (
    echo [OK] .vscode\settings.json ya apunta a %VENV_NAME%.
    set "VSC_CONFIGURED=1"
    exit /b 0
)
set "SET_LINES=0"
for /f %%N in ('find /c /v "" ^< "%SETTINGS%"') do set "SET_LINES=%%N"
if %SET_LINES% leq 3 goto :cfg_write
echo [AVISO] Ya existe .vscode\settings.json con otra configuracion. No se modifica.
echo         Actualiza a mano python.defaultInterpreterPath a:
echo         ${workspaceFolder}/%VENV_NAME%/Scripts/python.exe
exit /b 0
:cfg_write
> "%SETTINGS%" echo {
>> "%SETTINGS%" echo     "python.defaultInterpreterPath": "${workspaceFolder}/%VENV_NAME%/Scripts/python.exe"
>> "%SETTINGS%" echo }
echo [OK] .vscode\settings.json configurado con %VENV_NAME% como interprete por defecto.
set "VSC_CONFIGURED=1"
exit /b 0