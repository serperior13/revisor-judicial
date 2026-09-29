# gui/views/escaneo_view.py
"""
Vista principal del escaneo. Ejecuta las consultas en fases separadas.

Incluye:
  - Verificación previa de Excel abiertos.
  - Reciclado de driver (rotación, errores de red seguidos, driver muerto).
  - Rotación de IP vía Cloudflare WARP o proxies gratuitos.
  - Desconexión de WARP al terminar (si nosotros lo conectamos).
  - Control del flag global de capturas según configuración.
  - Logs de diagnóstico detallados para identificar bloqueos.
"""

import logging
import os
import random
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta
from tkinter import messagebox

import customtkinter as ctk

from core.constantes import (
    ARCHIVO_EXCEL,
    ARCHIVO_ENTRADA_SAMAI,
    ARCHIVO_SALIDA,
    ARCHIVO_SALIDA_SAMAI,
    BASE_DIR,
    COLUMNA_RADICADO,
    COLUMNA_RADICADO_SAMAI,
    COLUMNAS_SALIDA,
    ESPERA_ANTES_REINTENTOS,
    ESPERA_ENTRE_CONSULTAS_MAX,
    ESPERA_ENTRE_CONSULTAS_MIN,
    ESPERA_TRAS_ROTAR_IP,
    MAX_CONSULTAS_POR_DRIVER,
    MAX_NETWORK_ERRORS_SEGUIDOS,
    RESPALDAR_ANTES_DE_ESCANEAR,
    UMBRAL_NETWORK_ERRORS_PARA_ROTAR_IP,
)
from core.consulta_unificada import consultar_proceso
from core.excel_generator import preparar_dataframe
from core.modelos import Estadisticas
from core.scraper import (
    crear_driver,
    driver_sigue_vivo,
    cerrar_driver_seguro,
    _set_guardar_capturas,
)
from data.database import Database
from gui.widgets.controles_escaneo import ControlesEscaneo
from gui.widgets.filtro_actuaciones import FiltroActuaciones
from gui.widgets.panel_progreso import PanelProgreso
from gui.widgets.tarjetas import PanelEstadisticas
from gui.widgets.terminal import TerminalLogs
from services.excel_lock import (
    cerrar_libros_excel_especificos,
    esta_bloqueado_por_excel,
)
from services.ip_rotator import IPRotator
from services.save_excel import (
    intentar_guardar_excel,
    respaldar_busqueda_anterior,
)

log = logging.getLogger(__name__)


# ====================================================================
# HELPERS
# ====================================================================

def limpiar_radicado(numero):
    return re.sub(r"\D", "", str(numero or "")).strip()


def _espera_humana():
    time.sleep(random.uniform(ESPERA_ENTRE_CONSULTAS_MIN,
                              ESPERA_ENTRE_CONSULTAS_MAX))


def _a_formato_excel(resultado, dias_umbral):
    fecha = resultado.get("fecha_ultima_actuacion") or ""
    return {
        "Radicado": resultado.get("radicado", ""),
        "Estado": resultado.get("estado", ""),
        "Fecha_Ultima_Actuacion": fecha,
        "Observacion": resultado.get("observacion", ""),
        "Resumen de Actuacion": resultado.get("resumen", ""),
        "Despacho": resultado.get("despacho", ""),
        "Demandante": resultado.get("demandante", ""),
        "Demandado": resultado.get("demandado", ""),
        "Apoderado": resultado.get("apoderado", ""),
        "Captura": resultado.get("captura", ""),
        "Captura_Actuaciones": resultado.get("captura_actuaciones", ""),
        "_lineas_resumen": resultado.get("_lineas_resumen", []),
    }


# ====================================================================
# VISTA
# ====================================================================

class EscaneoView(ctk.CTkFrame):
    """Vista completa de la pantalla de escaneo (flujo de dos fases)."""

    def __init__(self, parent, log_queue, config, database: Database):
        super().__init__(parent, fg_color="transparent")
        self.log_queue = log_queue
        self.config = config
        self.database = database

        self.ejecutando = False
        self._pausa_event = threading.Event()
        self._cancel_event = threading.Event()
        self._worker_thread = None
        self.driver = None

        self._consultas_desde_reciclado = 0
        self._network_errors_seguidos = 0

        self.ip_rotator = IPRotator()
        self._warp_estaba_conectado_al_inicio = False

        self.stats = Estadisticas()
        self.on_escaneo_terminado = None
        self._todos_resultados = []

        self._crear_layout()
        self._cargar_config()

        log.info("🌐 Rotador de IP: %s", self.ip_rotator.resumen())

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _crear_layout(self) -> None:
        header = ctk.CTkFrame(
            self, corner_radius=12, fg_color=("gray90", "#2B2B2B"))
        header.pack(fill="x", padx=14, pady=(10, 6))
        ctk.CTkLabel(
            header,
            text="⚡ Consulta Automática de Procesos Judiciales",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        ).pack(side="left", padx=16, pady=10)

        self.controles = ControlesEscaneo(
            self,
            on_iniciar=self.iniciar_proceso,
            on_pausar=self.alternar_pausa,
            on_detener=self.solicitar_detencion,
            on_abrir_carpeta=self.abrir_carpeta_resultados,
        )

        self.filtro = FiltroActuaciones(self)
        self.panel_stats = PanelEstadisticas(self)
        self.panel_progreso = PanelProgreso(self)

        self.terminal = TerminalLogs(self, self.log_queue)
        self.terminal.pack(fill="both", expand=True, padx=14, pady=(4, 10))
        self.terminal.iniciar()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _cargar_config(self) -> None:
        try:
            escaneo_cfg = self.config.get_seccion("escaneo") or {}
        except AttributeError:
            escaneo_cfg = (self.config or {}).get("escaneo", {}) or {}

        if isinstance(escaneo_cfg, dict):
            self.controles.set_indice_inicio(escaneo_cfg.get("desde_indice", 1))
            self.controles.set_dias_umbral(escaneo_cfg.get("dias_umbral", 10))
            self.controles.set_jurisdicciones(
                escaneo_cfg.get("jurisdicciones", ["RAMA", "SAMAI"]))
            self.filtro.set_modo(
                escaneo_cfg.get("modo_actuaciones", "personalizado"))
            self.filtro.set_cantidad(
                escaneo_cfg.get("cantidad_actuaciones", 5))

    def _guardar_config(self, indice, dias, modo, cantidad,
                        jurisdicciones=None):
        valores = {
            "desde_indice": indice,
            "dias_umbral": dias,
            "modo_actuaciones": modo,
            "cantidad_actuaciones": cantidad,
            "jurisdicciones": sorted(list(jurisdicciones or {"RAMA", "SAMAI"})),
        }
        try:
            if hasattr(self.config, "set_seccion"):
                self.config.set_seccion("escaneo", valores)
            else:
                self.config.setdefault("escaneo", {}).update(valores)
        except Exception as e:
            log.warning("No se pudo guardar la config: %s", e)

    # ------------------------------------------------------------------
    # Acciones UI
    # ------------------------------------------------------------------

    def abrir_carpeta_resultados(self) -> None:
        try:
            os.startfile(BASE_DIR)
        except AttributeError:
            subprocess.Popen(["xdg-open", BASE_DIR])

    def alternar_pausa(self) -> None:
        if not self._pausa_event.is_set():
            self._pausa_event.set()
            self.controles.marcar_pausado(True)
            log.info("Ejecución pausada por el usuario...")
        else:
            self._pausa_event.clear()
            self.controles.marcar_pausado(False)
            log.info("Ejecución reanudada...")

    def solicitar_detencion(self) -> None:
        if messagebox.askyesno(
            "Confirmar cancelación",
            "¿Deseas detener el escaneo actual? "
            "Se guardará el progreso obtenido.",
        ):
            self._cancel_event.set()
            log.info("Solicitud de cancelación recibida...")

    # ------------------------------------------------------------------
    # Verificación previa de Excel
    # ------------------------------------------------------------------

    def _archivos_salida_a_verificar(self, jurisdicciones) -> list:
        archivos = []
        if "RAMA" in jurisdicciones:
            archivos.append(ARCHIVO_SALIDA)
        if "SAMAI" in jurisdicciones:
            archivos.append(ARCHIVO_SALIDA_SAMAI)
        return archivos

    def _verificar_excel_libre(self, jurisdicciones) -> bool:
        archivos = self._archivos_salida_a_verificar(jurisdicciones)
        if not archivos:
            return True

        while True:
            bloqueados = [
                f for f in archivos
                if os.path.exists(f) and esta_bloqueado_por_excel(f)
            ]

            if not bloqueados:
                return True

            log.info("🔒 Archivos bloqueados por Excel: %s. "
                     "Intentando cerrar…",
                     ", ".join(os.path.basename(f) for f in bloqueados))
            cerrar_libros_excel_especificos(*bloqueados)
            time.sleep(1.0)

            bloqueados = [
                f for f in archivos
                if os.path.exists(f) and esta_bloqueado_por_excel(f)
            ]
            if not bloqueados:
                log.info("✅ Archivos liberados automáticamente.")
                return True

            lista_nombres = "\n".join(
                "  • " + os.path.basename(f) for f in bloqueados
            )
            respuesta = messagebox.askretrycancel(
                "Archivo abierto en Excel",
                "Los siguientes archivos están abiertos en Excel:\n\n"
                f"{lista_nombres}\n\n"
                "Ciérralos y pulsa REINTENTAR para continuar.\n"
                "O pulsa CANCELAR para detener el escaneo.",
                parent=self,
            )

            if not respuesta:
                log.info("Escaneo cancelado por el usuario (Excel abierto).")
                return False

    # ------------------------------------------------------------------
    # Inicio del proceso
    # ------------------------------------------------------------------

    def iniciar_proceso(self) -> None:
        log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log.info("▶️ INICIANDO PROCESO DE ESCANEO")
        log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        self.ejecutando = True
        self._pausa_event.clear()
        self._cancel_event.clear()
        self._todos_resultados = []
        self._consultas_desde_reciclado = 0
        self._network_errors_seguidos = 0
        self.ip_rotator.limpiar_proxy()

        indice_inicio = self.controles.get_indice_inicio()
        dias_umbral = self.controles.get_dias_umbral()
        modo = self.filtro.get_modo()
        cantidad = self.filtro.get_cantidad()
        jurisdicciones = self.controles.get_jurisdicciones()

        log.info("📋 Configuración leída de la UI:")
        log.info("   • Desde índice: %s", indice_inicio)
        log.info("   • Días umbral: %s", dias_umbral)
        log.info("   • Modo actuaciones: %s", modo)
        log.info("   • Cantidad actuaciones: %s", cantidad)
        log.info("   • Jurisdicciones: %s", sorted(jurisdicciones))

        if not jurisdicciones:
            messagebox.showwarning(
                "Sin jurisdicción",
                "Debes marcar al menos una jurisdicción:\n"
                "  • Rama Judicial\n  • SAMAI (Consejo de Estado)"
            )
            self.ejecutando = False
            return

        log.info("🔍 Verificando archivos Excel abiertos…")
        if not self._verificar_excel_libre(jurisdicciones):
            self.ejecutando = False
            log.warning("❌ Escaneo cancelado (Excel abierto).")
            return
        log.info("✅ Verificación de Excel OK.")

        # Guardar estado inicial de WARP antes de empezar
        self._warp_estaba_conectado_al_inicio = (
            self.ip_rotator.warp_disponible()
            and self.ip_rotator.warp_estado() == "conectado"
        )
        if self._warp_estaba_conectado_al_inicio:
            log.info("ℹ️ WARP estaba conectado antes del escaneo. "
                     "Se dejará conectado al terminar.")

        log.info("Modo de actuaciones: %s (cantidad=%s)", modo, cantidad)
        log.info("Jurisdicciones: %s", ", ".join(sorted(jurisdicciones)))

        self._guardar_config(indice_inicio, dias_umbral, modo, cantidad,
                             jurisdicciones)

        self.stats.reiniciar()
        self.panel_stats.actualizar_todo(self.stats)
        self.panel_progreso.iniciar(datetime.now())

        self.controles.bloquear()
        self.filtro.bloquear()

        log.info("🚀 Lanzando hilo de scraping…")
        self._worker_thread = threading.Thread(
            target=self._hilo_scraping,
            args=(indice_inicio, dias_umbral, modo, cantidad, jurisdicciones),
            daemon=True,
        )
        self._worker_thread.start()
        log.info("✅ Hilo lanzado. Esperando progreso…")

    def finalizar_proceso_gui(self) -> None:
        self.ejecutando = False
        self.panel_progreso.detener()
        self.controles.desbloquear()
        self.filtro.desbloquear()
        if callable(self.on_escaneo_terminado):
            try:
                self.on_escaneo_terminado()
            except Exception as e:
                log.warning("Callback on_escaneo_terminado falló: %s", e)

    # ------------------------------------------------------------------
    # Pausa / cancelación
    # ------------------------------------------------------------------

    def _esperar_si_pausado(self) -> bool:
        while self._pausa_event.is_set():
            if self._cancel_event.is_set():
                return True
            self._pausa_event.wait(timeout=0.25)
        return self._cancel_event.is_set()

    def _clasificar_estado_y_contar(self, estado: str) -> None:
        self.after(0, self._inc_stat_en_main, estado)

    def _inc_stat_en_main(self, estado: str) -> None:
        self.stats.clasificar(estado)
        self.panel_stats.actualizar_todo(self.stats)

    # ------------------------------------------------------------------
    # Reciclado de driver
    # ------------------------------------------------------------------

    def _reciclar_driver(self, motivo: str = "") -> bool:
        if motivo:
            log.info("♻️ Reciclando driver (%s).", motivo)

        cerrar_driver_seguro(self.driver)
        self.driver = None
        time.sleep(random.uniform(2.0, 4.0))

        proxy = self.ip_rotator.get_proxy_actual()
        self.driver = crear_driver(proxy=proxy)
        self._consultas_desde_reciclado = 0
        self._network_errors_seguidos = 0

        if self.driver is None:
            log.error("❌ No se pudo recrear el driver de Chrome.")
            return False

        log.info("✅ Driver reciclado correctamente.")
        return True

    def _necesita_reciclar(self) -> str:
        if self.driver is None:
            return "driver ausente"
        if not driver_sigue_vivo(self.driver):
            return "driver muerto"
        if self._consultas_desde_reciclado >= MAX_CONSULTAS_POR_DRIVER:
            return "rotación preventiva ({} consultas)".format(
                self._consultas_desde_reciclado)
        if self._network_errors_seguidos >= MAX_NETWORK_ERRORS_SEGUIDOS:
            return "{} errores de red seguidos".format(
                self._network_errors_seguidos)
        return ""

    # ------------------------------------------------------------------
    # Rotación de IP
    # ------------------------------------------------------------------

    def _rotar_ip(self) -> bool:
        log.info("🌐 Iniciando rotación de IP...")
        resultado = self.ip_rotator.rotar()

        if not resultado.get("ok"):
            log.warning("⚠️ No se pudo rotar la IP: %s",
                        resultado.get("mensaje"))
            return False

        log.info("✅ %s", resultado.get("mensaje"))
        time.sleep(ESPERA_TRAS_ROTAR_IP)

        cerrar_driver_seguro(self.driver)
        self.driver = None
        time.sleep(1.0)

        proxy = self.ip_rotator.get_proxy_actual()
        self.driver = crear_driver(proxy=proxy)
        self._consultas_desde_reciclado = 0
        self._network_errors_seguidos = 0

        if self.driver is None:
            log.error("❌ No se pudo recrear el driver tras rotar IP.")
            return False

        log.info("✅ Driver recreado con nueva IP.")
        return True

    def _restaurar_estado_warp(self) -> None:
        if not self.ip_rotator.warp_disponible():
            return
        try:
            if self._warp_estaba_conectado_al_inicio:
                return

            estado_actual = self.ip_rotator.warp_estado()
            if estado_actual == "conectado":
                log.info("🔌 Desconectando WARP al terminar el escaneo "
                         "(estaba desconectado antes).")
                self.ip_rotator.desconectar_warp()
        except Exception as e:
            log.warning("No se pudo restaurar el estado de WARP: %s", e)

    # ------------------------------------------------------------------
    # Worker principal
    # ------------------------------------------------------------------

    def _hilo_scraping(self, desde_indice, dias_umbral,
                       modo_actuaciones, cantidad_actuaciones,
                       jurisdicciones):

        try:
            log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            log.info("🧵 HILO DE SCRAPING INICIADO")
            log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            # Control del flag global de capturas
            try:
                guardar_capturas = bool(
                    self.config.get("escaneo", "guardar_capturas", False))
            except Exception:
                guardar_capturas = False

            _set_guardar_capturas(guardar_capturas)

            if guardar_capturas:
                log.info("📸 Capturas ACTIVADAS (se guardarán en capturas/).")
            else:
                log.info("📸 Capturas DESACTIVADAS por configuración.")

            log.info("🔍 Verificando si hay Excel abiertos…")
            try:
                cerrar_libros_excel_especificos(
                    ARCHIVO_EXCEL, ARCHIVO_ENTRADA_SAMAI,
                    ARCHIVO_SALIDA, ARCHIVO_SALIDA_SAMAI,
                )
                log.info("✅ Verificación de Excel completada.")
            except Exception as e:
                log.warning("⚠️ Error verificando Excel (no crítico): %s", e)

            if RESPALDAR_ANTES_DE_ESCANEAR:
                log.info("📦 Respaldando búsqueda anterior…")
                respaldar_busqueda_anterior()
                log.info("✅ Respaldo completado.")

            log.info("🚗 Creando driver de Chrome…")
            proxy = self.ip_rotator.get_proxy_actual()
            self.driver = crear_driver(proxy=proxy)

            if self.driver is None:
                log.error("❌ No se pudo crear el driver. Abortando.")
                self.after(0, self.finalizar_proceso_gui)
                return

            log.info("✅ Driver creado correctamente.")

            self._consultas_desde_reciclado = 0
            self._network_errors_seguidos = 0

            # ========================================================
            # FASE 1: RAMA
            # ========================================================
            if "RAMA" in jurisdicciones:
                if self._esperar_si_pausado():
                    log.info("⏸️ Pausa/cancelación detectada antes de fase RAMA.")
                    return
                log.info("\n" + "=" * 60)
                log.info("🟧 FASE 1: RAMA JUDICIAL")
                log.info("=" * 60)
                self._procesar_fase(
                    jurisdiccion="RAMA",
                    archivo_entrada=ARCHIVO_EXCEL,
                    columna_entrada=COLUMNA_RADICADO,
                    archivo_salida=ARCHIVO_SALIDA,
                    desde_indice=desde_indice,
                    dias_umbral=dias_umbral,
                    modo_actuaciones=modo_actuaciones,
                    cantidad_actuaciones=cantidad_actuaciones,
                )

            # ========================================================
            # FASE 2: SAMAI
            # ========================================================
            if "SAMAI" in jurisdicciones:
                if self._esperar_si_pausado():
                    log.info("⏸️ Pausa/cancelación detectada antes de fase SAMAI.")
                    return
                log.info("\n" + "=" * 60)
                log.info("🟦 FASE 2: SAMAI (Consejo de Estado)")
                log.info("=" * 60)
                self._procesar_fase(
                    jurisdiccion="SAMAI",
                    archivo_entrada=ARCHIVO_ENTRADA_SAMAI,
                    columna_entrada=COLUMNA_RADICADO_SAMAI,
                    archivo_salida=ARCHIVO_SALIDA_SAMAI,
                    desde_indice=desde_indice,
                    dias_umbral=dias_umbral,
                    modo_actuaciones=modo_actuaciones,
                    cantidad_actuaciones=cantidad_actuaciones,
                )

        except Exception as e:
            log.exception("💥 Error no controlado en hilo de scraping: %s", e)

        finally:
            log.info("🧹 Limpiando recursos del escaneo…")
            try:
                cerrar_driver_seguro(self.driver)
                self.driver = None
                log.info("Navegador cerrado.")
            except Exception as e:
                log.warning("Error cerrando driver: %s", e)

            # Restaurar WARP
            try:
                self._restaurar_estado_warp()
            except Exception as e:
                log.warning("Error restaurando WARP: %s", e)

            # Restaurar el flag de capturas
            try:
                _set_guardar_capturas(True)
            except Exception:
                pass

            try:
                self.after(0, self._recalcular_stats,
                           list(self._todos_resultados))
                self.after(0, self.finalizar_proceso_gui)
            except Exception as e:
                log.warning("Error finalizando GUI: %s", e)

            log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            log.info("🏁 HILO DE SCRAPING FINALIZADO")
            log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # ------------------------------------------------------------------
    # Procesamiento de UNA fase
    # ------------------------------------------------------------------

    def _procesar_fase(self, jurisdiccion, archivo_entrada, columna_entrada,
                       archivo_salida, desde_indice, dias_umbral,
                       modo_actuaciones, cantidad_actuaciones):

        log.info("📂 [%s] Iniciando procesamiento de fase…", jurisdiccion)

        if not os.path.exists(archivo_entrada):
            log.error("❌ No existe el archivo de entrada: %s", archivo_entrada)
            return

        try:
            log.info("📖 [%s] Leyendo archivo Excel: %s",
                     jurisdiccion, archivo_entrada)
            import pandas as pd
            df = pd.read_excel(archivo_entrada, dtype=str)
            log.info("✅ [%s] Excel leído. Filas: %s, Columnas: %s",
                     jurisdiccion, len(df), list(df.columns))

            if columna_entrada not in df.columns:
                log.error("❌ Falta la columna '%s' en %s",
                          columna_entrada, archivo_entrada)
                return

            df = df.dropna(subset=[columna_entrada])
            radicados = [
                str(r).strip() for r in df[columna_entrada].tolist()
                if r and str(r).strip().lower() != "nan"
            ]
            radicados = [r for r in radicados
                         if "borra esta fila" not in r.lower()]
            log.info("📄 [%s] %s radicados encontrados.",
                     jurisdiccion, len(radicados))
        except Exception as e:
            log.exception("❌ [%s] Error leyendo %s: %s",
                          jurisdiccion, archivo_entrada, e)
            return

        if not radicados:
            log.warning("⚠️ [%s] No hay radicados. Saltando fase.", jurisdiccion)
            return

        idx_inicio = max(0, desde_indice - 1)
        radicados = radicados[idx_inicio:]
        if not radicados:
            log.warning("⚠️ [%s] No hay radicados en el rango indicado.",
                        jurisdiccion)
            return

        log.info("📊 [%s] Procesando %s radicados (desde índice %s).",
                 jurisdiccion, len(radicados), desde_indice)

        escaneo_id = None
        try:
            escaneo_id = self.database.iniciar_escaneo(
                modo_actuaciones=modo_actuaciones,
                dias_umbral=dias_umbral,
                cantidad_actuaciones=cantidad_actuaciones,
                total_radicados=len(radicados),
                jurisdiccion=jurisdiccion,
            )
            log.info("💾 [%s] Escaneo registrado en BD con ID: %s",
                     jurisdiccion, escaneo_id)
        except Exception as e:
            log.warning("⚠️ [%s] No se pudo registrar el escaneo en BD: %s",
                        jurisdiccion, e)

        resultados = []
        pendientes_reintento = []

        def _debe_pausar():
            return self._pausa_event.is_set() or self._cancel_event.is_set()

        # ============================================================
        # PASADA 1
        # ============================================================
        log.info("\n--- PASADA 1 (%s) ---", jurisdiccion)
        for i_rel, radicado in enumerate(radicados):
            if self._esperar_si_pausado():
                log.info("⏸️ [%s] Pausa detectada. Abortando pasada 1.",
                         jurisdiccion)
                break

            radicado_limpio = limpiar_radicado(radicado)
            log.info("🔎 [%s] (%s/%s) Procesando radicado: %s",
                     jurisdiccion, i_rel + 1, len(radicados), radicado_limpio)

            self.panel_progreso.set_progreso(i_rel + 1, len(radicados))

            motivo = self._necesita_reciclar()
            if motivo and jurisdiccion == "RAMA":
                log.info("♻️ Reciclando driver: %s", motivo)
                if self._network_errors_seguidos >= UMBRAL_NETWORK_ERRORS_PARA_ROTAR_IP:
                    log.info("🌐 Rotando IP (network errors seguidos).")
                    if not self._rotar_ip():
                        log.warning("Rotación falló. Reintentando reciclado normal…")
                        if not self._reciclar_driver(motivo):
                            break
                else:
                    if not self._reciclar_driver(motivo):
                        break

            t0 = time.time()
            try:
                log.info("🌐 [%s] Consultando radicado %s…",
                         jurisdiccion, radicado_limpio)
                resultado = consultar_proceso(
                    radicado_limpio,
                    driver=self.driver,
                    jurisdiccion=jurisdiccion,
                    guardar_captura=True,
                    debug=False,
                    cantidad_actuaciones=cantidad_actuaciones,
                    debe_pausar=_debe_pausar,
                    dias_umbral=dias_umbral,
                    modo_actuaciones=modo_actuaciones,
                )
                data = [_a_formato_excel(resultado, dias_umbral)]
                exito = not resultado.get("error")
                observacion = (resultado.get("observacion") or "")
                log.info("✅ [%s] Consulta completada: %s",
                         jurisdiccion, radicado_limpio)
            except Exception as e:
                log.exception("❌ [%s] Error consultando %s: %s",
                              jurisdiccion, radicado_limpio, e)
                data = [_fila_error(radicado_limpio, str(e))]
                exito = False
                observacion = str(e)

            self._consultas_desde_reciclado += 1
            if not exito and ("Network" in observacion
                              or "Error Red" in observacion
                              or "Fallo de red" in observacion
                              or "Conexión caída" in observacion):
                self._network_errors_seguidos += 1
                log.info("   📉 Network errors seguidos: %s/%s "
                         "(umbral rotar: %s)",
                         self._network_errors_seguidos,
                         MAX_NETWORK_ERRORS_SEGUIDOS,
                         UMBRAL_NETWORK_ERRORS_PARA_ROTAR_IP)
            else:
                self._network_errors_seguidos = 0

            self.panel_progreso.registrar_consulta(time.time() - t0)
            resultados.extend(data)
            for d in data:
                self._clasificar_estado_y_contar(d.get("Estado", ""))
            if not exito:
                pendientes_reintento.append((radicado_limpio, data))
            _espera_humana()

        # ============================================================
        # PASADA 2: reintentos
        # ============================================================
        if pendientes_reintento and not self._cancel_event.is_set():
            log.info("\n--- PASADA 2 (%s): %s reintentos ---",
                     jurisdiccion, len(pendientes_reintento))
            time.sleep(ESPERA_ANTES_REINTENTOS)

            if jurisdiccion == "RAMA" and self._network_errors_seguidos > 0:
                log.info("🔄 Rotando IP antes de la pasada 2…")
                self._rotar_ip()
            elif jurisdiccion == "RAMA":
                self._reciclar_driver("inicio de pasada 2")

            for radicado_limpio, datos_previos in pendientes_reintento:
                if self._esperar_si_pausado():
                    break
                for d in datos_previos:
                    try:
                        resultados.remove(d)
                    except ValueError:
                        pass

                motivo = self._necesita_reciclar()
                if motivo and jurisdiccion == "RAMA":
                    if self._network_errors_seguidos >= UMBRAL_NETWORK_ERRORS_PARA_ROTAR_IP:
                        self._rotar_ip()
                    else:
                        if not self._reciclar_driver(motivo):
                            break

                try:
                    log.info("🔁 [%s] Reintentando %s…",
                             jurisdiccion, radicado_limpio)
                    resultado = consultar_proceso(
                        radicado_limpio,
                        driver=self.driver,
                        jurisdiccion=jurisdiccion,
                        guardar_captura=True,
                        debug=False,
                        cantidad_actuaciones=cantidad_actuaciones,
                        debe_pausar=_debe_pausar,
                        dias_umbral=dias_umbral,
                        modo_actuaciones=modo_actuaciones,
                    )
                    data = [_a_formato_excel(resultado, dias_umbral)]
                    if resultado.get("error"):
                        for d in data:
                            d["Observacion"] += " (Falló en 2do intento)"
                except Exception as e:
                    data = [_fila_error(radicado_limpio,
                                        "Reintento: {}".format(e))]
                resultados.extend(data)
                _espera_humana()

        self._todos_resultados.extend(resultados)
        self.after(0, self._recalcular_stats, list(self._todos_resultados))

        # ============================================================
        # GUARDAR EXCEL
        # ============================================================
        if resultados:
            log.info("💾 [%s] Guardando informe Excel…", jurisdiccion)
            ruta_final = None
            try:
                df_resultados = preparar_dataframe(resultados, COLUMNAS_SALIDA)
                ok, ruta_final = intentar_guardar_excel(
                    df_resultados, archivo_salida, dias_umbral=dias_umbral)
                if ok:
                    log.info("✅ Informe %s guardado en: %s",
                             jurisdiccion, ruta_final)
                else:
                    log.error("❌ No se pudo guardar el informe %s", jurisdiccion)
            except Exception as e:
                log.error("❌ Error guardando informe %s: %s", jurisdiccion, e)
                ruta_final = None

            if escaneo_id is not None:
                try:
                    self.database.guardar_resultados(escaneo_id, resultados)
                    self.database.finalizar_escaneo(
                        escaneo_id, ruta_final or archivo_salida)
                    log.info("✅ Resultados guardados en BD.")
                except Exception as e:
                    log.warning("⚠️ No se pudo guardar en BD: %s", e)
        else:
            log.warning("⚠️ [%s] No hay resultados para guardar.", jurisdiccion)

    # ------------------------------------------------------------------
    # Recalcular stats / cierre
    # ------------------------------------------------------------------

    def _recalcular_stats(self, resultados):
        self.stats.reiniciar()
        for r in resultados:
            self.stats.clasificar(r.get("Estado", ""))
        self.panel_stats.actualizar_todo(self.stats)

    def detener_por_cierre(self) -> None:
        self._cancel_event.set()
        self._pausa_event.clear()
        self.terminal.detener()
        cerrar_driver_seguro(self.driver)
        self.driver = None


# ====================================================================
# HELPERS AUXILIARES
# ====================================================================

def _fila_error(radicado, mensaje):
    return {
        "Radicado": radicado,
        "Estado": "⚠️ Error de consulta",
        "Fecha_Ultima_Actuacion": "",
        "Observacion": mensaje,
        "Resumen de Actuacion": "",
        "Despacho": "", "Demandante": "", "Demandado": "",
        "Apoderado": "", "Captura": "", "Captura_Actuaciones": "",
        "_lineas_resumen": [],
    }