@echo off
REM ============================================================
REM build.bat - Compila Revisor Judicial con WARP embebido
REM ============================================================

setlocal

echo.
echo ============================================================
echo   Revisor Judicial - Build de produccion (con WARP)
echo ============================================================
echo.

REM --- Paso 1: Verificar entorno virtual ---
if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] No se encontro el entorno virtual .venv
    echo        Crea uno con:  python -m venv .venv
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat

REM --- Paso 2: Verificar WARP MSI ---
if not exist "resources\warp\Cloudflare_WARP_Release-x64.msi" (
    echo [ADVERTENCIA] No se encontro el MSI de Cloudflare WARP.
    echo.
    echo   Ruta esperada:
    echo     resources\warp\Cloudflare_WARP_Release-x64.msi
    echo.
    echo   El instalador se generara SIN WARP embebido.
    echo.
    pause
) else (
    echo [OK] WARP MSI encontrado.
)

REM --- Paso 3: Limpiar builds anteriores ---
echo.
echo [1/4] Limpiando builds anteriores...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "Output" rmdir /s /q "Output"
echo       OK
echo.

REM --- Paso 4: PyInstaller ---
echo [2/4] Compilando con PyInstaller...
pyinstaller RevisorJudicial.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller fallo.
    pause
    exit /b 1
)
echo       OK - dist\RevisorJudicial\
echo.

REM --- Paso 5: Inno Setup ---
echo [3/4] Generando instalador con Inno Setup...

set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
) else (
    where iscc.exe >nul 2>&1
    if not errorlevel 1 set "ISCC=iscc.exe"
)

if "%ISCC%"=="" (
    echo [ADVERTENCIA] No se encontro Inno Setup (ISCC.exe)
    echo               Descargalo gratis desde https://jrsoftware.org/isdl.php
    echo.
    pause
    exit /b 0
)

"%ISCC%" RevisorJudicial_Installer.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup fallo.
    pause
    exit /b 1
)
echo       OK - Output\
echo.

REM --- Paso 6: Resumen ---
echo [4/4] ============================================================
echo       BUILD COMPLETADO
echo ============================================================
echo.
echo   Instalador generado en:
echo     Output\RevisorJudicial_Setup_v1.0.0.exe
echo.

pause
endlocal