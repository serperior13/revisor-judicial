# data/config.py
"""
Gestor de configuración persistente en JSON.
"""

import json
import logging
import os
from typing import Any

from core.constantes import ARCHIVO_CONFIG

log = logging.getLogger(__name__)


DEFAULTS = {
    "usuario": {
        "tema": "Dark",
        "nombre": "",
        "email": "",
    },
    "escaneo": {
        "desde_indice": 1,
        "dias_umbral": 10,
        "modo_actuaciones": "personalizado",
        "cantidad_actuaciones": 5,
        # 👇 NUEVO: por defecto NO guardamos capturas
        "guardar_capturas": False,
        # Días que se mantienen las capturas antes de auto-borrarlas
        "dias_retencion_capturas": 15,
    },
    "ventana": {
        "ancho": 1120,
        "alto": 880,
        "x": None,
        "y": None,
    },
    "licencia": {
        "clave": "",
        "tipo": "",
        "vence": "",
    },
    "estadisticas_globales": {
        "escaneos_totales": 0,
        "radicados_procesados": 0,
        "ultimo_escaneo": "",
    },
}


class ConfigManager:
    """
    Lee y escribe configuración desde `config.json`.
    Si el archivo no existe, lo crea con valores por defecto.
    """

    def __init__(self, ruta: str = None):
        self.ruta = ruta or ARCHIVO_CONFIG
        self._data = self._cargar()

    # ------------------------------------------------------------------

    def _cargar(self) -> dict:
        if not os.path.exists(self.ruta):
            log.info("Config no encontrada. Creando con valores por defecto.")
            self._data = self._deep_copy(DEFAULTS)
            self._guardar_interno()
            return self._data

        try:
            with open(self.ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._merge_con_defaults(data)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Config corrupta (%s). Usando defaults.", e)
            return self._deep_copy(DEFAULTS)

    def _merge_con_defaults(self, data: dict) -> dict:
        resultado = self._deep_copy(DEFAULTS)

        def _merge(dst: dict, src: dict) -> None:
            for k, v in src.items():
                if k in dst and isinstance(dst[k], dict) and isinstance(v, dict):
                    _merge(dst[k], v)
                else:
                    dst[k] = v

        if isinstance(data, dict):
            _merge(resultado, data)
        return resultado

    @staticmethod
    def _deep_copy(d: dict) -> dict:
        return json.loads(json.dumps(d))

    def _guardar_interno(self) -> None:
        try:
            with open(self.ruta, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            log.error("No se pudo guardar config: %s", e)

    def guardar(self) -> None:
        self._guardar_interno()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def get(self, seccion: str, clave: str, default: Any = None) -> Any:
        return self._data.get(seccion, {}).get(clave, default)

    def set(self, seccion: str, clave: str, valor: Any,
            auto_guardar: bool = True) -> None:
        if seccion not in self._data:
            self._data[seccion] = {}
        self._data[seccion][clave] = valor
        if auto_guardar:
            self.guardar()

    def get_seccion(self, seccion: str) -> dict:
        return dict(self._data.get(seccion, {}))

    def set_seccion(self, seccion: str, valores: dict,
                    auto_guardar: bool = True) -> None:
        if seccion not in self._data:
            self._data[seccion] = {}
        self._data[seccion].update(valores)
        if auto_guardar:
            self.guardar()

    # ------------------------------------------------------------------
    # Helpers específicos
    # ------------------------------------------------------------------

    def registrar_escaneo(self, radicados_procesados: int) -> None:
        from datetime import datetime
        est = self._data.setdefault("estadisticas_globales", {})
        est["escaneos_totales"] = int(est.get("escaneos_totales", 0)) + 1
        est["radicados_procesados"] = (
            int(est.get("radicados_procesados", 0)) + int(radicados_procesados)
        )
        est["ultimo_escaneo"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.guardar()