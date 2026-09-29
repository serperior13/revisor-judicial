# services/limpieza.py
"""
Limpieza de capturas antiguas.

- Auto-limpieza al arrancar: borra capturas > N días.
- Limpieza manual: borra todas o las mayores a X días.
"""

import logging
import os
import time
from pathlib import Path

from core.constantes import CARPETA_CAPTURAS

log = logging.getLogger(__name__)


# Subcarpetas conocidas dentro de capturas/
SUBCARPETAS_CAPTURAS = ["samai"]


# ====================================================================
# UTILIDADES
# ====================================================================

def _tamano_carpeta(ruta: Path) -> tuple[int, int]:
    """
    Devuelve (cantidad_archivos, bytes_totales) de una carpeta.
    Recursivo.
    """
    total_bytes = 0
    total_archivos = 0
    try:
        for item in ruta.rglob("*"):
            if item.is_file():
                try:
                    total_bytes += item.stat().st_size
                    total_archivos += 1
                except OSError:
                    pass
    except Exception:
        pass
    return total_archivos, total_bytes


def _formatear_tamano(bytes_: int) -> str:
    """Formatea bytes a algo legible: '15.3 MB', '1.2 GB', etc."""
    for unidad in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return "{:.1f} {}".format(bytes_, unidad)
        bytes_ /= 1024.0
    return "{:.1f} TB".format(bytes_)


# ====================================================================
# ESTADÍSTICAS
# ====================================================================

def obtener_estadisticas_capturas() -> dict:
    """
    Devuelve un dict con:
      {
        "cantidad_archivos": int,
        "bytes_totales": int,
        "tamano_legible": "15.3 MB",
        "por_subcarpeta": { "samai": {"cantidad": N, "bytes": M}, ... }
      }
    """
    carpeta = Path(CARPETA_CAPTURAS)
    if not carpeta.exists():
        return {
            "cantidad_archivos": 0,
            "bytes_totales": 0,
            "tamano_legible": "0 B",
            "por_subcarpeta": {},
        }

    # Total
    total_cant, total_bytes = _tamano_carpeta(carpeta)

    # Por subcarpeta
    por_sub = {}
    for nombre in SUBCARPETAS_CAPTURAS:
        sub = carpeta / nombre
        if sub.exists():
            cant, bts = _tamano_carpeta(sub)
            por_sub[nombre] = {"cantidad": cant, "bytes": bts}

    return {
        "cantidad_archivos": total_cant,
        "bytes_totales": total_bytes,
        "tamano_legible": _formatear_tamano(total_bytes),
        "por_subcarpeta": por_sub,
    }


# ====================================================================
# LIMPIEZA
# ====================================================================

def limpiar_capturas_antiguas(dias: int = 15) -> dict:
    """
    Borra capturas con más de `dias` días de antigüedad.

    Devuelve:
      {
        "eliminados": N,
        "bytes_liberados": M,
        "tamano_legible": "12.3 MB",
        "errores": [...],
      }
    """
    if dias <= 0:
        return {
            "eliminados": 0,
            "bytes_liberados": 0,
            "tamano_legible": "0 B",
            "errores": ["Los días deben ser > 0."],
        }

    carpeta = Path(CARPETA_CAPTURAS)
    if not carpeta.exists():
        return {
            "eliminados": 0,
            "bytes_liberados": 0,
            "tamano_legible": "0 B",
            "errores": [],
        }

    limite = time.time() - (dias * 24 * 3600)

    eliminados = 0
    bytes_liberados = 0
    errores = []

    # Recorrer toda la carpeta (incluyendo subcarpetas)
    for item in carpeta.rglob("*"):
        if not item.is_file():
            continue
        try:
            mtime = item.stat().st_mtime
            if mtime >= limite:
                continue

            tam = item.stat().st_size
            item.unlink()
            eliminados += 1
            bytes_liberados += tam
        except FileNotFoundError:
            # Ya no existe, todo bien
            pass
        except Exception as e:
            errores.append("{}: {}".format(item.name, e))

    log.info(
        "🧹 Limpieza de capturas (%s días): %s archivos, %s liberados.",
        dias, eliminados, _formatear_tamano(bytes_liberados),
    )

    return {
        "eliminados": eliminados,
        "bytes_liberados": bytes_liberados,
        "tamano_legible": _formatear_tamano(bytes_liberados),
        "errores": errores,
    }


def limpiar_todas_las_capturas() -> dict:
    """Borra TODAS las capturas. Mismo formato de retorno."""
    carpeta = Path(CARPETA_CAPTURAS)
    if not carpeta.exists():
        return {
            "eliminados": 0,
            "bytes_liberados": 0,
            "tamano_legible": "0 B",
            "errores": [],
        }

    eliminados = 0
    bytes_liberados = 0
    errores = []

    for item in carpeta.rglob("*"):
        if not item.is_file():
            continue
        try:
            tam = item.stat().st_size
            item.unlink()
            eliminados += 1
            bytes_liberados += tam
        except FileNotFoundError:
            pass
        except Exception as e:
            errores.append("{}: {}".format(item.name, e))

    log.info(
        "🧹 Limpieza completa de capturas: %s archivos, %s liberados.",
        eliminados, _formatear_tamano(bytes_liberados),
    )

    return {
        "eliminados": eliminados,
        "bytes_liberados": bytes_liberados,
        "tamano_legible": _formatear_tamano(bytes_liberados),
        "errores": errores,
    }