# core/resumen.py
"""Construcción del resumen de actuaciones a partir de la lista cruda del portal."""

import re
from datetime import datetime, timedelta

from core.constantes import (
    DIAS_ACTUACIONES_RECIENTES,
    DIAS_ULTIMO_MES,
    MAX_LINEAS_RESUMEN,
)


def _sanitize_xml(texto: str) -> str:
    """Elimina caracteres de control que rompen el XML del xlsx."""
    if not texto:
        return ""
    return re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", str(texto))


def construir_resumen_actuaciones(
    actuaciones: list,
    modo: str = "personalizado",
    cantidad: int = 5,
    dias_recientes: int = DIAS_ACTUACIONES_RECIENTES,
):
    """
    Filtra y construye el texto del resumen según el modo:

      - "todas":         todas las actuaciones (limitado a MAX_LINEAS_RESUMEN)
      - "15dias":        actuaciones de los últimos `dias_recientes` días
      - "1mes":          actuaciones de los últimos 30 días
      - "personalizado": las N más recientes (1..10)

    Devuelve:
        (lineas, texto_plano)
    """
    if not actuaciones:
        return [], ""

    limite_15 = datetime.now() - timedelta(days=dias_recientes)
    limite_mes = datetime.now() - timedelta(days=DIAS_ULTIMO_MES)
    seleccionadas = []

    if modo == "todas":
        seleccionadas = list(actuaciones[:MAX_LINEAS_RESUMEN])

    elif modo == "15dias":
        for a in actuaciones:
            try:
                f = datetime.strptime(a.get("fecha", ""), "%Y-%m-%d")
                if f >= limite_15:
                    seleccionadas.append(a)
            except (ValueError, TypeError):
                continue

    elif modo == "1mes":
        for a in actuaciones:
            try:
                f = datetime.strptime(a.get("fecha", ""), "%Y-%m-%d")
                if f >= limite_mes:
                    seleccionadas.append(a)
            except (ValueError, TypeError):
                continue

    elif modo == "personalizado":
        n = max(1, min(10, int(cantidad)))
        seleccionadas = list(actuaciones[:n])

    else:
        seleccionadas = list(actuaciones[:MAX_LINEAS_RESUMEN])

    lineas = []
    for a in seleccionadas:
        partes = []
        if a.get("fecha"):
            partes.append(a["fecha"])
        if a.get("actuacion"):
            partes.append(a["actuacion"])
        if a.get("anotacion"):
            partes.append(re.sub(r"\s+", " ", a["anotacion"]).strip())
        texto_linea = " | ".join(partes)

        term = []
        if a.get("inicia_termino"):
            term.append("Inicia término: {}".format(a["inicia_termino"]))
        if a.get("finaliza_termino"):
            term.append("Finaliza término: {}".format(a["finaliza_termino"]))
        if term:
            texto_linea += "  ·  " + "  ·  ".join(term)

        texto_linea = _sanitize_xml(
            texto_linea.replace("\n", " ").replace("\r", ""))
        lineas.append((texto_linea, None))

    texto_plano = "\n".join(t for t, _ in lineas)
    return lineas, texto_plano