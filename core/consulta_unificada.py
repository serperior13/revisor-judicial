"""
core/consulta_unificada.py
==========================
Orquestador central de consultas judiciales.

Detecta automáticamente si un radicado pertenece a:
  - SAMAI (Consejo de Estado / Contencioso Administrativo)
  - Rama Judicial (Jurisdicción Ordinaria)

Y llama al scraper correspondiente, con fallback automático SOLO cuando
el radicado podría pertenecer a la otra jurisdicción.
"""

import logging
import re

from services import samai_scraper
from . import scraper as rama_judicial_scraper


logger = logging.getLogger("consulta_unificada")


# ====================================================================
# DETECCIÓN DE JURISDICCIÓN
# ====================================================================

CODIGOS_SAMAI = {"03", "23", "33"}
LONGITUD_RADICADO = 23


def limpiar_radicado(numero):
    """Quita puntos, guiones, espacios y deja solo dígitos."""
    return re.sub(r"\D", "", str(numero or "")).strip()


def detectar_jurisdiccion(radicado):
    """
    Devuelve 'SAMAI' o 'RAMA' según el radicado.
    Criterio: 23 dígitos y especialidad (dígitos 6-7) en {03, 23, 33}.
    """
    rad = limpiar_radicado(radicado)
    if len(rad) != LONGITUD_RADICADO:
        return "RAMA"
    especialidad = rad[5:7]
    if especialidad in CODIGOS_SAMAI:
        return "SAMAI"
    return "RAMA"


def _podria_ser_de(jurisdiccion, radicado):
    """Verifica si un radicado podría pertenecer a una jurisdicción."""
    rad = limpiar_radicado(radicado)
    if len(rad) != LONGITUD_RADICADO:
        return False
    especialidad = rad[5:7]
    if jurisdiccion == "SAMAI":
        return especialidad in CODIGOS_SAMAI
    return especialidad not in CODIGOS_SAMAI


# ====================================================================
# NORMALIZACIÓN DE RESULTADOS
# ====================================================================

_MAPEO_RAMA_A_ESTANDAR = {
    "Radicado": "radicado",
    "Estado": "estado",
    "Fecha_Ultima_Actuacion": "fecha_ultima_actuacion",
    "Observacion": "observacion",
    "Resumen de Actuacion": "resumen",
    "Despacho": "despacho",
    "Demandante": "demandante",
    "Demandado": "demandado",
    "Apoderado": "apoderado",
    "Captura": "captura",
    "Captura_Actuaciones": "captura_actuaciones",
    "_lineas_resumen": "_lineas_resumen",
}


def _normalizar_desde_rama(registro, radicado, jurisdiccion="RAMA"):
    """Convierte un registro del scraper de RAMA al formato estándar."""
    estandar = {
        "radicado": radicado,
        "jurisdiccion": jurisdiccion,
        "estado": "",
        "fecha_ultima_actuacion": "",
        "observacion": "",
        "despacho": "",
        "demandante": "",
        "demandado": "",
        "apoderado": "",
        "procurador": "",
        "resumen": "",
        "captura": "",
        "captura_actuaciones": "",
        "ponente": "",
        "clase": "",
        "vigente": "",
        "ubicacion": "",
        "etapa": "",
        "error": None,
    }
    if not isinstance(registro, dict):
        return estandar
    for clave_rama, clave_est in _MAPEO_RAMA_A_ESTANDAR.items():
        if clave_rama in registro:
            estandar[clave_est] = registro[clave_rama] or ""
    if not estandar["radicado"]:
        estandar["radicado"] = radicado
    return estandar


def _normalizar_desde_samai(registro, radicado):
    """Garantiza que el resultado de SAMAI tenga todas las claves estándar."""
    estandar = {
        "radicado": radicado,
        "jurisdiccion": "SAMAI",
        "estado": "",
        "fecha_ultima_actuacion": "",
        "observacion": "",
        "despacho": "",
        "demandante": "",
        "demandado": "",
        "apoderado": "",
        "procurador": "",
        "resumen": "",
        "captura": "",
        "captura_actuaciones": "",
        "ponente": "",
        "clase": "",
        "vigente": "",
        "ubicacion": "",
        "etapa": "",
        "error": None,
    }
    if not isinstance(registro, dict):
        return estandar
    for clave in estandar:
        if clave in registro and registro[clave] is not None:
            estandar[clave] = registro[clave]
    return estandar


# ====================================================================
# VALIDACIÓN
# ====================================================================

def _tiene_datos_utiles(resultado):
    """Determina si un resultado trae información aprovechable."""
    if not resultado or not isinstance(resultado, dict):
        return False
    if resultado.get("error"):
        return False
    demandante = (resultado.get("demandante") or "").strip()
    demandado = (resultado.get("demandado") or "").strip()
    tiene_partes = (
        (demandante and demandante not in ("Sin demandante", "Sin datos")) or
        (demandado and demandado not in ("Sin demandado", "Sin datos"))
    )
    tiene_actuacion = bool((resultado.get("fecha_ultima_actuacion") or "").strip())
    tiene_estado = bool((resultado.get("estado") or "").strip())
    tiene_despacho = bool((resultado.get("despacho") or "").strip())
    return tiene_partes or tiene_actuacion or tiene_estado or tiene_despacho


def _resultado_util(r):
    """¿El resultado tiene datos realmente útiles?"""
    if not isinstance(r, dict):
        return False
    dem = (r.get("demandante") or "").strip()
    ddo = (r.get("demandado") or "").strip()
    if dem and dem not in ("Sin demandante", "Sin datos"):
        return True
    if ddo and ddo not in ("Sin demandado", "Sin datos"):
        return True
    if (r.get("fecha_ultima_actuacion") or "").strip():
        return True
    if (r.get("resumen") or "").strip():
        return True
    return False


def _es_estado_de_error(estado):
    """Determina si un Estado contiene señales de fallo que ameritan reintento."""
    if not estado:
        return False
    estado_low = estado.lower()
    marcadores = (
        "⚠", "error", "no respondió", "no generó resultados",
        "sin resultado /", "fallo de red", "network error",
    )
    return any(m in estado or m in estado_low for m in marcadores)


# ====================================================================
# LLAMADA A SCRAPERS
# ====================================================================

def _llamar_scraper(jurisdiccion, radicado, driver, guardar_captura, debug,
                    cantidad_actuaciones=5, debe_pausar=None,
                    dias_umbral=10, modo_actuaciones="personalizado"):
    """Despacha la consulta al scraper correcto y devuelve el formato estándar."""
    try:
        if jurisdiccion == "SAMAI":
            crudo = samai_scraper.consultar(
                radicado, driver=driver,
                guardar_captura=guardar_captura, debug=debug,
                cantidad_actuaciones=cantidad_actuaciones,
                debe_pausar=debe_pausar,
            )
            resultado = _normalizar_desde_samai(crudo, radicado)

            if resultado.get("error"):
                return resultado

            if _es_estado_de_error(resultado.get("estado", "")):
                resultado["error"] = resultado.get("estado", "Error en SAMAI")
                return resultado

            if not _resultado_util(resultado):
                resultado["error"] = (
                    "Sin datos de sujetos/actuaciones (todos los GUIDs fallaron)"
                )
                logger.warning("⚠️ SAMAI sin datos útiles para %s", radicado)

            return resultado

        # ---------- RAMA ----------
        # 👇 AHORA SÍ le pasamos los parámetros configurables al scraper RAMA
        resultado_rama = rama_judicial_scraper.consultar_radicado_individual(
            driver=driver,
            radicado_limpio=radicado,
            i_actual=1,
            total_procesos=1,
            dias_umbral=dias_umbral,
            modo_actuaciones=modo_actuaciones,
            cantidad_actuaciones=cantidad_actuaciones,
        )

        if isinstance(resultado_rama, tuple):
            exito, registros = resultado_rama
        else:
            exito, registros = True, resultado_rama

        if not registros:
            return _dict_error(radicado, "El scraper RAMA no devolvió registros.")

        primer_registro = registros[0]
        resultado = _normalizar_desde_rama(primer_registro, radicado,
                                           jurisdiccion="RAMA")

        estado = resultado.get("estado", "") or ""
        if not exito:
            resultado["error"] = resultado.get("observacion", "Error en scraper RAMA")
            logger.warning("⚠️ Scraper RAMA reportó fallo para %s: %s",
                           radicado, resultado["error"])
        elif _es_estado_de_error(estado):
            resultado["error"] = estado
            logger.warning("⚠️ Estado de error detectado para %s: %s",
                           radicado, estado)

        return resultado

    except Exception as e:
        logger.exception("❌ Error consultando %s: %s", jurisdiccion, e)
        return _dict_error(radicado, f"Error en scraper {jurisdiccion}: {e}")


# ====================================================================
# CONSULTA PRINCIPAL
# ====================================================================

def consultar_proceso(radicado, driver=None, jurisdiccion=None,
                      jurisdicciones=None,
                      guardar_captura=True, debug=False,
                      cantidad_actuaciones=5,
                      debe_pausar=None,
                      dias_umbral=10,
                      modo_actuaciones="personalizado"):
    """Consulta un proceso judicial en la jurisdicción correspondiente."""
    radicado_limpio = limpiar_radicado(radicado)

    if not radicado_limpio:
        return _dict_error("", "Radicado vacío.")

    if jurisdiccion is not None:
        juris_set = {jurisdiccion.upper()}
    elif jurisdicciones is not None:
        juris_set = {j.upper() for j in jurisdicciones} & {"RAMA", "SAMAI"}
    else:
        juris_set = {"RAMA", "SAMAI"}

    if not juris_set:
        return _dict_error(
            radicado_limpio,
            "No se seleccionó ninguna jurisdicción para consultar."
        )

    if len(juris_set) == 1:
        principal = next(iter(juris_set))
        alternativa = None
        logger.info("🔎 Radicado %s → SOLO %s (sin fallback)",
                    radicado_limpio, principal)
    else:
        principal = detectar_jurisdiccion(radicado_limpio)
        alternativa = "RAMA" if principal == "SAMAI" else "SAMAI"
        logger.info("🔎 Radicado %s → AMBAS | principal: %s | alternativa: %s",
                    radicado_limpio, principal, alternativa)

    driver_creado_localmente = False
    if driver is None:
        logger.info("🚗 Creando Chrome temporal...")
        driver = rama_judicial_scraper.crear_driver()
        driver_creado_localmente = True
        if driver is None:
            return _dict_error(radicado_limpio, "No se pudo iniciar Chrome.")

    try:
        resultado = _llamar_scraper(
            principal, radicado_limpio, driver,
            guardar_captura=guardar_captura, debug=debug,
            cantidad_actuaciones=cantidad_actuaciones,
            debe_pausar=debe_pausar,
            dias_umbral=dias_umbral,
            modo_actuaciones=modo_actuaciones,
        )

        if alternativa is not None and not _tiene_datos_utiles(resultado):
            logger.warning(
                "⚠️ Sin datos útiles en %s. Probando fallback en %s...",
                principal, alternativa,
            )
            resultado_alt = _llamar_scraper(
                alternativa, radicado_limpio, driver,
                guardar_captura=guardar_captura, debug=debug,
                cantidad_actuaciones=cantidad_actuaciones,
                debe_pausar=debe_pausar,
                dias_umbral=dias_umbral,
                modo_actuaciones=modo_actuaciones,
            )
            if _tiene_datos_utiles(resultado_alt):
                logger.info("✅ Fallback exitoso en %s.", alternativa)
                return resultado_alt
            logger.warning("⚠️ El fallback tampoco devolvió datos útiles.")
        elif alternativa is None:
            logger.info(
                "ℹ️ Solo se seleccionó %s. No se intenta fallback.", principal
            )

        return resultado
    finally:
        if driver_creado_localmente and driver is not None:
            try:
                driver.quit()
                logger.info("🚗 Chrome cerrado.")
            except Exception:
                pass


# ====================================================================
# ERRORES
# ====================================================================

def _dict_error(radicado, mensaje):
    """Diccionario de error con todas las claves estándar."""
    return {
        "radicado": radicado,
        "jurisdiccion": "",
        "estado": "",
        "fecha_ultima_actuacion": "",
        "observacion": mensaje,
        "despacho": "",
        "demandante": "",
        "demandado": "",
        "apoderado": "",
        "procurador": "",
        "resumen": "",
        "captura": "",
        "captura_actuaciones": "",
        "ponente": "",
        "clase": "",
        "vigente": "",
        "ubicacion": "",
        "etapa": "",
        "error": mensaje,
    }


# ====================================================================
# PRUEBA MANUAL
# ====================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(message)s",
    )
    radicado_prueba = input("Ingrese un radicado: ").strip()
    resultado = consultar_proceso(radicado_prueba, debug=True)
    print("\n=== RESULTADO UNIFICADO ===")
    for k, v in resultado.items():
        valor = str(v)
        if len(valor) > 200:
            valor = valor[:200] + "..."
        print(f"{k}: {valor}")