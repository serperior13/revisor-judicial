# core/modelos.py
"""Modelos de datos del Revisor Judicial."""

from dataclasses import dataclass, field
from typing import Optional

from core.constantes import COLUMNA_LINEAS_INTERNA, COLUMNA_RESUMEN


@dataclass
class RegistroResultado:
    """Un registro individual de un radicado consultado."""
    radicado: str = ""
    estado: str = ""
    fecha_ultima_actuacion: str = ""
    observacion: str = ""
    despacho: str = ""
    demandante: str = "Sin demandante"
    demandado: str = "Sin demandado"
    apoderado: str = "Sin apoderado"
    resumen: str = ""
    captura: str = ""
    captura_actuaciones: str = ""
    lineas_resumen: list = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convierte a dict con el formato exacto que espera el Excel."""
        return {
            "Radicado": self.radicado,
            "Estado": self.estado,
            "Fecha_Ultima_Actuacion": self.fecha_ultima_actuacion,
            "Observacion": self.observacion,
            COLUMNA_RESUMEN: self.resumen,
            "Despacho": self.despacho,
            "Demandante": self.demandante,
            "Demandado": self.demandado,
            "Apoderado": self.apoderado,
            "Captura": self.captura,
            "Captura_Actuaciones": self.captura_actuaciones,
            COLUMNA_LINEAS_INTERNA: self.lineas_resumen,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RegistroResultado":
        """Construye un RegistroResultado desde un dict."""
        return cls(
            radicado=d.get("Radicado", ""),
            estado=d.get("Estado", ""),
            fecha_ultima_actuacion=d.get("Fecha_Ultima_Actuacion", ""),
            observacion=d.get("Observacion", ""),
            despacho=d.get("Despacho", ""),
            demandante=d.get("Demandante", "Sin demandante"),
            demandado=d.get("Demandado", "Sin demandado"),
            apoderado=d.get("Apoderado", "Sin apoderado"),
            resumen=d.get(COLUMNA_RESUMEN, ""),
            captura=d.get("Captura", ""),
            captura_actuaciones=d.get("Captura_Actuaciones", ""),
            lineas_resumen=d.get(COLUMNA_LINEAS_INTERNA, []) or [],
        )


@dataclass
class ConfiguracionEscaneo:
    """Parámetros con los que se lanza un escaneo."""
    desde_indice: int = 1
    dias_umbral: int = 10
    modo_actuaciones: str = "personalizado"     # "todas" | "15dias" | "1mes" | "personalizado"
    cantidad_actuaciones: int = 5

    def to_dict(self) -> dict:
        return {
            "desde_indice": self.desde_indice,
            "dias_umbral": self.dias_umbral,
            "modo_actuaciones": self.modo_actuaciones,
            "cantidad_actuaciones": self.cantidad_actuaciones,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConfiguracionEscaneo":
        return cls(
            desde_indice=int(d.get("desde_indice", 1)),
            dias_umbral=int(d.get("dias_umbral", 10)),
            modo_actuaciones=str(d.get("modo_actuaciones", "personalizado")),
            cantidad_actuaciones=int(d.get("cantidad_actuaciones", 5)),
        )


@dataclass
class Estadisticas:
    """Contadores para las tarjetas del GUI."""
    revisar: int = 0
    fuera: int = 0
    sin_fecha: int = 0
    privados: int = 0
    errores: int = 0

    def reiniciar(self) -> None:
        self.revisar = 0
        self.fuera = 0
        self.sin_fecha = 0
        self.privados = 0
        self.errores = 0

    def clasificar(self, estado: str) -> None:
        if estado == "Revisar":
            self.revisar += 1
        elif "fuera de búsqueda" in estado:
            self.fuera += 1
        elif estado == "Proceso Privado":
            self.privados += 1
        elif "⚠️" in estado or "Error" in estado:
            self.errores += 1
        else:
            self.sin_fecha += 1

    def to_dict(self) -> dict:
        return {
            "revisar": self.revisar,
            "fuera": self.fuera,
            "sin_fecha": self.sin_fecha,
            "privados": self.privados,
            "errores": self.errores,
        }