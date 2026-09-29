# services/save_excel.py
"""
Guardado del Excel con manejo de bloqueos.

Los archivos _PENDIENTE_ ahora van a la carpeta 'excels_pendientes/'.
"""

import logging
import os
import shutil
import time
from datetime import datetime

import pandas as pd

from core.constantes import (
    ARCHIVO_SALIDA,
    CARPETA_PENDIENTES,
    CARPETA_RESPALDOS,
    ESPERA_ENTRE_REINTENTOS_GUARDADO,
    MAX_REINTENTOS_GUARDADO,
    RESPALDAR_ANTES_DE_ESCANEAR,
)
from core.excel_generator import generar_excel_multihoja
from services.excel_lock import (
    asegurar_archivo_libre,
    esta_bloqueado_por_excel,
    puede_escribirse,
)

log = logging.getLogger(__name__)


# ====================================================================
# RESPALDOS
# ====================================================================

def respaldar_busqueda_anterior() -> None:
    if not os.path.exists(ARCHIVO_SALIDA):
        return
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ruta_destino = os.path.join(
            CARPETA_RESPALDOS, "busqueda_{}.xlsx".format(ts))
        shutil.move(ARCHIVO_SALIDA, ruta_destino)
        log.info("Resultado anterior respaldado en: %s", ruta_destino)
    except OSError as e:
        log.warning("No se pudo respaldar el archivo anterior: %s", e)


def respaldar_informe_anterior(ruta_archivo: str) -> bool:
    if not ruta_archivo or not os.path.exists(ruta_archivo):
        return True

    try:
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M")
        nombre_base = os.path.splitext(os.path.basename(ruta_archivo))[0]
        nombre_respaldo = "{}_{}.xlsx".format(nombre_base, ts)
        ruta_destino = os.path.join(CARPETA_RESPALDOS, nombre_respaldo)

        if os.path.exists(ruta_destino):
            ts_seg = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            nombre_respaldo = "{}_{}.xlsx".format(nombre_base, ts_seg)
            ruta_destino = os.path.join(CARPETA_RESPALDOS, nombre_respaldo)

        shutil.move(ruta_archivo, ruta_destino)
        log.info("📦 Informe anterior respaldado: %s", ruta_destino)
        return True
    except OSError as e:
        log.warning("⚠️ No se pudo respaldar el informe anterior: %s", e)
        return False


# ====================================================================
# GUARDADO
# ====================================================================

def _ruta_pendiente(filepath: str) -> str:
    """Ahora los pendientes van a CARPETA_PENDIENTES."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(os.path.basename(filepath))
    return os.path.join(CARPETA_PENDIENTES, "{}_PENDIENTE_{}{}".format(base, ts, ext))


def intentar_guardar_excel(df_resultados: pd.DataFrame, filepath: str,
                           dias_umbral: int = 10):
    """
    Guarda el Excel manejando bloqueos.

    Returns:
        (ok: bool, ruta_final: str | None)
    """
    # 1) Verificar que el archivo esté libre (cierre amable, sin force)
    if os.path.exists(filepath):
        libre = asegurar_archivo_libre(filepath, forzar=False)
        if not libre:
            log.warning("⚠️ El archivo sigue bloqueado. "
                        "Se guardará como copia alternativa.")

    # 2) Respaldar el anterior
    respaldar_informe_anterior(filepath)

    # 3) Intentar guardar
    for intento in range(1, MAX_REINTENTOS_GUARDADO + 1):
        try:
            generar_excel_multihoja(df_resultados, filepath,
                                    dias_umbral=dias_umbral)
            if intento > 1:
                log.info("✅ Guardado correcto en el intento %d", intento)
            return True, filepath
        except PermissionError as e:
            log.warning("Intento %d/%d: archivo bloqueado (%s)",
                        intento, MAX_REINTENTOS_GUARDADO, e)
            if intento < MAX_REINTENTOS_GUARDADO:
                time.sleep(ESPERA_ENTRE_REINTENTOS_GUARDADO)
        except OSError as e:
            log.warning("Error de sistema guardando: %s", e)
            break
        except Exception as e:
            log.warning("Error inesperado guardando: %s", e)
            break

    # 4) Fallback: guardar en excels_pendientes/
    ruta_alt = _ruta_pendiente(filepath)
    log.warning("⚠️ Guardando copia alternativa en excels_pendientes/: %s",
                os.path.basename(ruta_alt))

    try:
        generar_excel_multihoja(df_resultados, ruta_alt, dias_umbral=dias_umbral)
        return True, ruta_alt
    except Exception as e:
        log.error("❌ No se pudo guardar ni la copia de respaldo: %s", e)
        return False, None


__all__ = [
    "respaldar_busqueda_anterior",
    "respaldar_informe_anterior",
    "intentar_guardar_excel",
    "RESPALDAR_ANTES_DE_ESCANEAR",
]