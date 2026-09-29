# services/excel_lock.py
"""
Utilidades para detectar y cerrar libros de Excel que bloqueen archivos.

ESTRATEGIA CRÍTICA:
  - Antes de llamar a COM (win32com), verificar con tasklist si EXCEL.EXE
    está corriendo. Si no lo está, saltar el paso COM completamente.
  - Esto evita el cuelgue de 30-60s que produce GetActiveObject cuando
    Excel no está abierto.
"""

import logging
import os
import subprocess
import time

log = logging.getLogger(__name__)

try:
    import win32com.client
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


# ====================================================================
# DETECCIÓN POR LOCK FILE
# ====================================================================

def _ruta_lock_file(ruta_archivo: str) -> str:
    directorio = os.path.dirname(os.path.abspath(ruta_archivo))
    nombre = os.path.basename(ruta_archivo)
    return os.path.join(directorio, "~${}".format(nombre))


def esta_bloqueado_por_excel(ruta_archivo: str) -> bool:
    try:
        return os.path.exists(_ruta_lock_file(ruta_archivo))
    except Exception:
        return False


def puede_escribirse(ruta_archivo: str) -> bool:
    if not os.path.exists(ruta_archivo):
        return True
    try:
        with open(ruta_archivo, "ab"):
            return True
    except (PermissionError, OSError):
        return False


# ====================================================================
# DETECCIÓN DE EXCEL CORRIENDO (con flags anti-cuelgue)
# ====================================================================

def _excel_esta_corriendo() -> bool:
    """
    Comprueba con tasklist si EXCEL.EXE está corriendo.
    Usa CREATE_NO_WINDOW para evitar abrir consola y tiene timeout duro.
    """
    try:
        # CREATE_NO_WINDOW = 0x08000000 (evita que salga una consola)
        creationflags = 0
        startupinfo = None
        if os.name == "nt":
            creationflags = 0x08000000  # CREATE_NO_WINDOW
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        resultado = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq EXCEL.EXE", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
        salida = (resultado.stdout or "").upper()
        return "EXCEL.EXE" in salida
    except subprocess.TimeoutExpired:
        log.warning("⏱️ tasklist tardó más de 5s. Asumiendo que Excel NO está abierto.")
        return False
    except FileNotFoundError:
        log.warning("tasklist no encontrado. Saltando verificación de Excel.")
        return False
    except Exception as e:
        log.debug("Error comprobando Excel: %s", e)
        return False


# ====================================================================
# CIERRE VÍA COM
# ====================================================================

def _intentar_cerrar_via_win32(nombres_objetivo: set) -> int:
    if not WIN32_AVAILABLE:
        return 0

    # 👇 CRÍTICO: verificación rápida ANTES de tocar COM
    if not _excel_esta_corriendo():
        log.debug("Excel no está corriendo. Se omite el cierre vía COM.")
        return 0

    try:
        excel_app = win32com.client.GetActiveObject("Excel.Application")
    except Exception as e:
        log.debug("Excel no accesible vía COM: %s", e)
        return 0

    cerrados = 0
    try:
        a_cerrar = []
        for i in range(1, excel_app.Workbooks.Count + 1):
            try:
                wb = excel_app.Workbooks(i)
            except Exception:
                continue
            if wb.Name.lower() in nombres_objetivo:
                a_cerrar.append(wb)

        for wb in a_cerrar:
            log.warning("El libro '%s' está abierto. Cerrando vía COM…", wb.Name)
            try:
                wb.Close(SaveChanges=False)
                cerrados += 1
            except Exception as e:
                log.warning("   No se pudo cerrar '%s': %s", wb.Name, e)
    except Exception as e:
        log.warning("Error al cerrar Excel vía COM: %s", e)

    return cerrados


# ====================================================================
# API PÚBLICA
# ====================================================================

def cerrar_libros_excel_especificos(*nombres_archivos: str) -> int:
    """Cierra los libros indicados si Excel los tiene abiertos."""
    if not nombres_archivos:
        return 0

    t0 = time.time()
    objetivos = {os.path.basename(f).lower() for f in nombres_archivos}
    log.debug("🔍 Cerrando libros Excel: %s", objetivos)

    # Chequeo rápido: si no hay lock files, no hay nada que cerrar
    hay_lock = False
    for nombre in nombres_archivos:
        if os.path.exists(nombre) and esta_bloqueado_por_excel(nombre):
            hay_lock = True
            break

    if not hay_lock:
        # No hay lock files: no hace falta tocar Excel
        log.debug("Sin lock files. Saltando cierre de Excel.")
        return 0

    # Hay lock files → intentamos cerrar vía COM
    cerrados = _intentar_cerrar_via_win32(objetivos)

    if cerrados:
        time.sleep(0.5)

    log.debug("Cierre de Excel completado en %.2fs (cerrados: %s)",
              time.time() - t0, cerrados)
    return cerrados


def esperar_desbloqueo(ruta_archivo: str, timeout: float = 5.0) -> bool:
    inicio = time.time()
    while time.time() - inicio < timeout:
        if not esta_bloqueado_por_excel(ruta_archivo) and \
                puede_escribirse(ruta_archivo):
            return True
        time.sleep(0.3)
    return False


def asegurar_archivo_libre(ruta_archivo: str, forzar: bool = False) -> bool:
    if not os.path.exists(ruta_archivo):
        return True
    if not esta_bloqueado_por_excel(ruta_archivo) and \
            puede_escribirse(ruta_archivo):
        return True

    log.info("🔒 Detectado bloqueo por Excel en %s. Intentando cerrar…",
             os.path.basename(ruta_archivo))

    cerrar_libros_excel_especificos(ruta_archivo)
    if esperar_desbloqueo(ruta_archivo, timeout=3.0):
        log.info("✅ Archivo liberado.")
        return True

    log.warning("❌ No se pudo liberar el archivo: %s",
                os.path.basename(ruta_archivo))
    return False