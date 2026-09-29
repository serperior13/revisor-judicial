# main.py
"""
Entrypoint del Revisor Judicial.

Uso:
    python main.py            # desarrollo
    RevisorJudicial.exe       # producción (PyInstaller)
"""

import logging
import os
import queue
import sys
from datetime import datetime

import customtkinter as ctk

from core.bootstrap import asegurar_archivos_entrada
from core.constantes import (
    APP_DIR,
    ARCHIVO_LOG,
    BASE_DIR,
    RESOURCES_DIR,
)
from data.config import ConfigManager
from data.database import Database
from gui.main_window import MainWindow


# ====================================================================
# LOGGING
# ====================================================================

log_queue = queue.Queue()


class QueueHandler(logging.Handler):
    """Envía cada registro de logging a la cola que consume la Terminal de la GUI."""

    def emit(self, record):
        try:
            log_queue.put(self.format(record))
        except Exception:
            self.handleError(record)


def _configurar_logging() -> None:
    formato = logging.Formatter(
        "%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(ARCHIVO_LOG, encoding="utf-8")
    file_handler.setFormatter(formato)

    queue_handler = QueueHandler()
    queue_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(message)s", "%H:%M:%S"))

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formato)

    logging.basicConfig(
        level=logging.INFO,
        handlers=[file_handler, queue_handler, console_handler],
        force=True,
    )


# ====================================================================
# IDENTIDAD DE LA APP EN WINDOWS
# ====================================================================

def _fijar_app_user_model_id():
    """
    Fija un AppUserModelID único para que Windows agrupe la app
    correctamente en la barra de tareas y use el icono propio.
    """
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "CordobaAbogados.RevisorJudicial.1.0.0"
        )
    except Exception:
        pass


# ====================================================================
# ICONO
# ====================================================================

def _aplicar_icono(ventana, log):
    """
    Aplica el icono personalizado a la ventana principal.

    En PyInstaller 6.x los recursos viven en `_internal/`, así que
    usamos RESOURCES_DIR que ya resuelve la ruta correcta.
    """
    try:
        # Construir candidatos de rutas (por si acaso)
        candidatos = [
            os.path.join(RESOURCES_DIR, "resources", "icons", "icono.ico"),
            os.path.join(RESOURCES_DIR, "icons", "icono.ico"),
            os.path.join(APP_DIR, "resources", "icons", "icono.ico"),
            os.path.join(APP_DIR, "_internal", "resources", "icons", "icono.ico"),
        ]

        ruta_ico = None
        for c in candidatos:
            if os.path.exists(c):
                ruta_ico = c
                break

        if ruta_ico is None:
            log.warning("⚠️ No se encontró el icono. Buscado en:")
            for c in candidatos:
                log.warning("   - %s", c)
            return

        # Aplicar el icono con pequeño delay por si CTk lo sobrescribe
        def _set_ico():
            try:
                # Método 1: iconbitmap (clásico)
                try:
                    ventana.iconbitmap(ruta_ico)
                except Exception:
                    pass

                # Método 2: iconphoto (mejor soporte HiDPI y taskbar)
                try:
                    from PIL import Image, ImageTk
                    img = Image.open(ruta_ico)
                    # Redimensionar a 64x64 si es muy grande
                    if img.size[0] > 64:
                        img = img.resize((64, 64), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    ventana.iconphoto(True, photo)
                    # Guardar referencia para evitar garbage collection
                    ventana._icon_photo_ref = photo
                except Exception as e:
                    log.debug("iconphoto falló: %s", e)
            except Exception as e:
                log.warning("No se pudo aplicar el icono: %s", e)

        # Aplicar después de 100ms (cuando la ventana ya está creada)
        ventana.after(100, _set_ico)
        log.info("✅ Icono aplicado: %s", ruta_ico)

    except Exception as e:
        log.warning("No se pudo aplicar el icono: %s", e)


# ====================================================================
# VERIFICACIÓN DE LICENCIA
# ====================================================================

# Días que se permite la app sin poder contactar al servidor.
DIAS_GRACIA_OFFLINE = 7


def _evaluar_gracia_offline(log):
    """
    Evalúa si la licencia local puede usarse sin conexión.

    Devuelve:
      "activa"   → sí, dentro del periodo de gracia
      "trial"    → igual pero en trial
      "invalida" → fuera del periodo o sin validación previa
    """
    try:
        from services import licencias
        estado = licencias.obtener_estado_local()
    except Exception as e:
        log.warning("No se pudo leer licencia local: %s", e)
        return "invalida"

    if not estado.get("token"):
        log.info("🔑 Sin licencia activada en esta PC.")
        return "invalida"

    # Si el servidor ya marcó la licencia como inválida, no hay gracia
    if estado.get("invalida") in ("VENCIDA", "REVOCADA", "MAQUINA_NO_ACTIVADA"):
        log.warning("❌ Licencia marcada como inválida localmente: %s",
                    estado.get("invalida"))
        return "invalida"

    ultima = estado.get("ultima_validacion_ok")
    if not ultima:
        log.warning("Modo offline sin validación previa. Bloqueado.")
        return "invalida"

    try:
        dias = (datetime.now() - datetime.fromisoformat(ultima)).days
    except Exception:
        log.warning("No se pudo interpretar 'ultima_validacion_ok'.")
        return "invalida"

    if dias <= DIAS_GRACIA_OFFLINE:
        log.info(
            "📴 Modo offline: última validación hace %s día(s). "
            "Dentro del periodo de gracia (%s días).",
            dias, DIAS_GRACIA_OFFLINE,
        )
        plan = (estado.get("plan") or "").lower()
        return "trial" if plan == "trial" else "activa"

    log.warning(
        "⏰ Periodo de gracia offline expirado (%s días sin validar). "
        "Se requiere conexión al servidor.",
        dias,
    )
    return "invalida"


def _verificar_licencia(log):
    """
    Verifica el estado de la licencia al arrancar.

    Devuelve: "activa" | "trial" | "invalida"
    """
    try:
        from services import licencias

        estado_local = licencias.obtener_estado_local()

        # Si no hay token, no hay nada que verificar
        if not estado_local.get("token"):
            log.info("🔑 Sin licencia activada en esta PC.")
            return "invalida"

        # Consultar al servidor
        log.info("🔎 Verificando licencia con el servidor...")
        resp = licencias.validar(silencioso=True)

        codigo = (resp.get("codigo") or "").strip()

        # --- Caso 1: el servidor respondió OK ---
        if resp.get("ok"):
            plan = (resp.get("plan") or "").lower()
            dias = resp.get("dias_restantes", 0)
            log.info("✅ Licencia válida. Plan: %s | Vence en %s días.",
                     plan, dias)
            return "trial" if plan == "trial" else "activa"

        # --- Caso 2: no se pudo conectar al servidor ---
        if codigo == "SIN_CONEXION":
            log.info("📴 Sin conexión al servidor de licencias. "
                     "Aplicando modo offline.")
            return _evaluar_gracia_offline(log)

        # --- Caso 3: el servidor dice que la licencia es inválida ---
        if codigo in ("VENCIDA", "REVOCADA", "MAQUINA_NO_ACTIVADA"):
            log.warning("❌ Licencia inválida: %s (%s)",
                        resp.get("error"), codigo)
            return "invalida"

        # --- Caso 4: otros errores del servidor ---
        log.warning("⚠️ Error del servidor de licencias: %s",
                    resp.get("error"))
        return _evaluar_gracia_offline(log)

    except Exception as e:
        log.warning("Excepción verificando licencia: %s", e)
        return _evaluar_gracia_offline(log)


# ====================================================================
# MAIN
# ====================================================================

def main() -> int:
    # Fijar AppUserModelID ANTES de crear la ventana (para la taskbar)
    _fijar_app_user_model_id()

    _configurar_logging()
    log = logging.getLogger(__name__)

    log.info("=" * 60)
    log.info("Revisor Judicial — Monitoreo inteligente para Rama Judicial y SAMAI")
    log.info("Carpeta de la app:   %s", APP_DIR)
    log.info("Carpeta de datos:    %s", BASE_DIR)
    log.info("Carpeta de recursos: %s", RESOURCES_DIR)
    log.info("=" * 60)

    # 1) Crear los Excel de entrada si no existen
    log.info("Verificando archivos de entrada...")
    asegurar_archivos_entrada()

    # 2) Configuración y BD
    try:
        config = ConfigManager()
    except Exception as e:
        log.exception("No se pudo cargar la configuración: %s", e)
        return 1

    # Auto-limpieza de capturas antiguas
    try:
        from services.limpieza import limpiar_capturas_antiguas
        dias_ret = int(config.get("escaneo", "dias_retencion_capturas", 15))
        if dias_ret > 0:
            resultado_limp = limpiar_capturas_antiguas(dias=dias_ret)
            if resultado_limp["eliminados"] > 0:
                log.info(
                    "🧹 Auto-limpieza: %s capturas >%s días eliminadas (%s).",
                    resultado_limp["eliminados"], dias_ret,
                    resultado_limp["tamano_legible"],
                )
    except Exception as e:
        log.warning("No se pudo limpiar capturas antiguas: %s", e)

    try:
        database = Database()
    except Exception as e:
        log.exception("No se pudo inicializar la base de datos: %s", e)
        return 1

    # 3) Tema guardado
    try:
        ctk.set_default_color_theme("blue")
        tema = config.get("usuario", "tema", "Dark")
        if tema not in ("Dark", "Light"):
            tema = "Dark"
        ctk.set_appearance_mode(tema)
        log.info("Tema aplicado: %s", tema)
    except Exception as e:
        log.warning("No se pudo aplicar el tema guardado: %s", e)
        ctk.set_appearance_mode("Dark")

    # 4) Verificar licencia
    estado_licencia = _verificar_licencia(log)
    log.info("Estado de licencia: %s", estado_licencia)

    # 5) Ventana principal
    try:
        app = MainWindow(
            log_queue=log_queue,
            config=config,
            database=database,
            estado_licencia=estado_licencia,
        )
        _aplicar_icono(app, log)

    except Exception as e:
        log.exception("No se pudo crear la ventana principal: %s", e)
        return 1

    log.info("Aplicación lista. Esperando interacción del usuario...")
    app.mainloop()

    log.info("Aplicación cerrada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())