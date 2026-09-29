# core/constantes.py
"""
Constantes globales del Revisor Judicial.

Estructura de rutas:
  - APP_DIR:       Carpeta donde vive el .exe (o el script en desarrollo).
  - BASE_DIR:      Carpeta donde van los DATOS del usuario (config, db, Excel).
                   Si APP_DIR es escribible → APP_DIR.
                   Si APP_DIR NO es escribible (Program Files) → %LOCALAPPDATA%.
  - RESOURCES_DIR: Carpeta donde están los recursos bundled (icono, guías).
                   En PyInstaller 6.x apunta a `_internal/`.
"""

import os
import sys
from datetime import datetime


# ====================================================================
# UTILIDADES DE RUTAS
# ====================================================================

def _es_escribible(ruta: str) -> bool:
    """Comprueba si podemos escribir en una carpeta."""
    try:
        os.makedirs(ruta, exist_ok=True)
        test_file = os.path.join(ruta, ".test_write_tmp")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True
    except (PermissionError, OSError):
        return False


def _obtener_app_dir() -> str:
    """
    Carpeta donde vive el .exe (o el script en desarrollo).
    Contiene los recursos de solo lectura: icono, código, etc.
    """
    if getattr(sys, "frozen", False):
        # Empaquetado con PyInstaller: carpeta del .exe
        return os.path.dirname(os.path.abspath(sys.executable))
    # Desarrollo: raíz del proyecto (sube un nivel desde core/)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _obtener_base_dir() -> str:
    """
    Carpeta donde van los datos del usuario (config, db, logs, Excel).

    - Si APP_DIR es escribible (dev, instalación personal) → APP_DIR.
    - Si APP_DIR NO es escribible (Program Files) → %LOCALAPPDATA%\\Revisor Judicial.
    """
    app_dir = _obtener_app_dir()

    # 1) Intento: usar la carpeta de la app (dev, instalación personal)
    if _es_escribible(app_dir):
        return app_dir

    # 2) Fallback: carpeta del usuario en LOCALAPPDATA
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        user_dir = os.path.join(local_appdata, "Revisor Judicial")
        try:
            os.makedirs(user_dir, exist_ok=True)
            return user_dir
        except Exception:
            pass

    # 3) Último fallback: carpeta actual
    return os.getcwd()


def _obtener_resources_dir() -> str:
    """
    Directorio donde están los recursos bundled (icono, guías).

    En PyInstaller 6.x los recursos van dentro de `_internal/`, no
    junto al .exe. Buscamos en todos los lugares posibles.
    """
    if getattr(sys, "frozen", False):
        # 1) PyInstaller 6.x: sys._MEIPASS apunta a la carpeta _internal/
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.isdir(os.path.join(meipass, "resources")):
            return meipass

        # 2) Fallback: junto al .exe (instalación normal sin _internal)
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.isdir(os.path.join(exe_dir, "resources")):
            return exe_dir

        # 3) Fallback: dentro de _internal/ junto al .exe
        if os.path.isdir(os.path.join(exe_dir, "_internal", "resources")):
            return os.path.join(exe_dir, "_internal")

        # 4) Último recurso: la carpeta del .exe tal cual
        return exe_dir

    # Desarrollo: raíz del proyecto
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ====================================================================
# RUTAS PRINCIPALES
# ====================================================================

APP_DIR = _obtener_app_dir()
BASE_DIR = _obtener_base_dir()
RESOURCES_DIR = _obtener_resources_dir()


# ====================================================================
# CARPETAS DE DATOS (en BASE_DIR, escribibles)
# ====================================================================

CARPETA_LOGS = os.path.join(BASE_DIR, "logs")
CARPETA_RESPALDOS = os.path.join(BASE_DIR, "busquedas_anteriores")
CARPETA_CAPTURAS = os.path.join(BASE_DIR, "capturas")
CARPETA_RESPALDOS_RADICADOS = os.path.join(BASE_DIR, "respaldos_radicados")
CARPETA_PENDIENTES = os.path.join(BASE_DIR, "excels_pendientes")


# ====================================================================
# ARCHIVOS DE DATOS (en BASE_DIR, escribibles)
# ====================================================================

ARCHIVO_EXCEL = os.path.join(BASE_DIR, "Procesos.xlsx")
ARCHIVO_SALIDA = os.path.join(BASE_DIR, "resultados_actuaciones.xlsx")
ARCHIVO_CONFIG = os.path.join(BASE_DIR, "config.json")


# ====================================================================
# CREAR CARPETAS (con manejo de errores)
# ====================================================================

for _carpeta in (
    CARPETA_LOGS,
    CARPETA_RESPALDOS,
    CARPETA_CAPTURAS,
    CARPETA_RESPALDOS_RADICADOS,
    CARPETA_PENDIENTES,
):
    try:
        os.makedirs(_carpeta, exist_ok=True)
    except Exception:
        pass


# ====================================================================
# LOG DE LA SESIÓN
# ====================================================================

ARCHIVO_LOG = os.path.join(
    CARPETA_LOGS,
    "log_escaneo_{}.txt".format(datetime.now().strftime("%Y%m%d_%H%M%S")),
)


# ====================================================================
# NOMBRES DE COLUMNAS
# ====================================================================

COLUMNA_RADICADO = "Radicado"
COLUMNA_RESUMEN = "Resumen de Actuacion"
COLUMNA_CAPTURA_ACT = "Captura_Actuaciones"
COLUMNA_LINEAS_INTERNA = "_lineas_resumen"

COLUMNAS_SALIDA = [
    "Radicado", "Estado", "Fecha_Ultima_Actuacion",
    "Observacion", COLUMNA_RESUMEN,
    "Despacho", "Demandante", "Demandado", "Apoderado",
    "Captura", COLUMNA_CAPTURA_ACT,
    COLUMNA_LINEAS_INTERNA,
]


# ====================================================================
# TIEMPOS (segundos)
# ====================================================================

TIMEOUT_CAMPO_RADICADO = 8
TIMEOUT_RESULTADOS = 30
TIMEOUT_TABLA_ACTUACIONES = 8
ESPERA_INGRESO_RADICADO = 5
ESPERA_RESULTADOS = 3

ESPERA_ENTRE_CONSULTAS_MIN = 1.5
ESPERA_ENTRE_CONSULTAS_MAX = 3.5

ESPERA_ANTES_REINTENTOS = 3
ESPERA_CLIC_ACTUACION = 3
ESPERA_CARGA_ACTUACIONES = 2
INTERVALO_TICK_ETA_MS = 1000

MAX_REINTENTOS_GUARDADO = 3
ESPERA_ENTRE_REINTENTOS_GUARDADO = 2


# ====================================================================
# REINTENTOS Y RECICLADO
# ====================================================================

BACKOFF_SEGUNDOS = [0, 3, 8, 15]
MAX_INTENTOS_INTERNOS = 3
MAX_CONSULTAS_POR_DRIVER = 10
MAX_NETWORK_ERRORS_SEGUIDOS = 3

UMBRAL_NETWORK_ERRORS_PARA_ROTAR_IP = 2
ESPERA_TRAS_ROTAR_IP = 3.0


# ====================================================================
# COMPORTAMIENTO
# ====================================================================

RESPALDAR_ANTES_DE_ESCANEAR = False
CLIC_ULTIMA_ACTUACION = True
DIAS_ACTUACIONES_RECIENTES = 15
DIAS_ULTIMO_MES = 30
MAX_LINEAS_RESUMEN = 120


# ====================================================================
# FORMATO DEL EXCEL
# ====================================================================

ALTO_FILA_PUNTOS = 168.75
ALTO_ENCABEZADO_PUNTOS = 30

ANCHOS_COLUMNAS = {
    "A": 23.57, "B": 23.57, "C": 11.43, "D": 14.29, "E": 56.43,
    "F": 14.29, "G": 14.29, "H": 14.29, "I": 14.29, "J": 14.29, "K": 14.29,
}


# ====================================================================
# URLS
# ====================================================================

URL_CONSULTA = "https://consultaprocesos.ramajudicial.gov.co/Procesos/NumeroRadicacion"


# ====================================================================
# CATEGORÍAS DE ACTUACIONES
# ====================================================================
CATEGORIAS_ACTUACIONES = [
    (r"radicaci[oó]n\s+de\s+proceso",                "Radicación de Proceso",            "7030A0", False),
    (r"\bal\s+despacho\b",                           "Al despacho",                      "0070C0", False),
    (r"auto\s+admite\s+demanda",                     "Auto admite demanda",              "00B050", False),
    (r"inadmite\s+demanda",                          "Auto inadmite demanda",            "FF0000", False),
    (r"rechaza\s+demanda",                           "Auto rechaza demanda",             "FF0000", False),
    (r"(libra|libro)\s+mandamiento\s+(de\s+)?pago",  "Auto libra mandamiento ejecutivo", "00B050", False),
    (r"(libra|libro)\s+mandamiento\s+ejecutivo",     "Auto libra mandamiento ejecutivo", "00B050", False),
    (r"inadmite\s+mandamiento",                      "Auto inadmite mandamiento",        "FF0000", False),
    (r"rechaza\s+mandamiento",                       "Auto rechaza mandamiento",         "FF0000", False),
    (r"(decreta|decret[oó]|ordena)\s+medidas?\s+cautelar", "Decreta medidas cautelares",  "00B050", False),
    (r"rechaza\s+medidas?\s+cautelar",               "Rechaza medidas cautelares",       "FF0000", False),
    (r"fijaci[oó]n\s+de?\s+estado",                  "Fijación estado",                  "ED7D31", True),
    (r"auto\s+fija\s+fecha\s+audiencia",             "Auto fija fecha audiencia",        "C000C0", True),
    (r"y/?o\s+diligencia",                           "Fija diligencia",                  "C000C0", True),
    (r"rece(p|b)ci[oó]n\s+memorial",                 "Recepción memorial",               "4472C4", True),
]


# ====================================================================
# ARCHIVOS SAMAI
# ====================================================================

ARCHIVO_ENTRADA_SAMAI = os.path.join(BASE_DIR, "Radicados_SAMAI.xlsx")
ARCHIVO_SALIDA_SAMAI = os.path.join(BASE_DIR, "resultados_samai.xlsx")
COLUMNA_RADICADO_SAMAI = "radicacion samai"