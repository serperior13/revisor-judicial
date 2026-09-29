# gui/views/config_view.py
"""
Vista de configuración persistente. Lee y escribe en config.json
a través de ConfigManager.
"""

import logging
import os
import subprocess
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

from core.constantes import (
    BASE_DIR,
    CARPETA_CAPTURAS,
    CARPETA_LOGS,
    CARPETA_PENDIENTES,
    CARPETA_RESPALDOS,
    CARPETA_RESPALDOS_RADICADOS,
)

log = logging.getLogger(__name__)


class ConfigView(ctk.CTkFrame):
    """Vista de preferencias de la aplicación."""

    def __init__(self, parent, config):
        super().__init__(parent, fg_color="transparent")
        self.config = config

        self._crear_layout()
        self._cargar_valores()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _crear_layout(self):
        # --- Header ---
        header = ctk.CTkFrame(
            self, corner_radius=12, fg_color=("gray90", "#2B2B2B"))
        header.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            header, text="⚙️ Configuración",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).pack(side="left", padx=16, pady=10)

        ctk.CTkButton(
            header, text="💾  Guardar cambios", width=180, height=34,
            fg_color="#0066FF", hover_color="#0052CC",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._guardar,
        ).pack(side="right", padx=(4, 16), pady=10)

        ctk.CTkButton(
            header, text="↺  Restaurar", width=130, height=34,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=12),
            command=self._restaurar_defaults,
        ).pack(side="right", padx=4, pady=10)

        # --- Cuerpo con scroll ---
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        self._seccion_usuario(scroll)
        self._seccion_apariencia(scroll)
        self._seccion_escaneo(scroll)
        self._seccion_warp(scroll)
        self._seccion_capturas(scroll)
        self._seccion_rutas(scroll)
        self._seccion_estadisticas(scroll)

    # ------------------------------------------------------------------
    # Sección: Usuario
    # ------------------------------------------------------------------

    def _seccion_usuario(self, parent):
        box = self._crear_seccion(
            parent, "👤 Información del usuario",
            "Estos datos aparecerán en los documentos que generes.")

        grid = ctk.CTkFrame(box, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=10)
        grid.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(grid, text="Nombre completo:",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w",
                                      padx=(0, 12), pady=6)

        self.entry_nombre = ctk.CTkEntry(
            grid, height=32, placeholder_text="Ej: Andrés Córdoba")
        self.entry_nombre.grid(row=0, column=1, sticky="ew", pady=6)

        ctk.CTkLabel(grid, text="Correo electrónico:",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=1, column=0, sticky="w",
                                      padx=(0, 12), pady=6)

        self.entry_email = ctk.CTkEntry(
            grid, height=32, placeholder_text="Ej: abogado@correo.com")
        self.entry_email.grid(row=1, column=1, sticky="ew", pady=6)

    # ------------------------------------------------------------------
    # Sección: Apariencia
    # ------------------------------------------------------------------

    def _seccion_apariencia(self, parent):
        box = self._crear_seccion(
            parent, "🎨 Apariencia", "Tema visual de la aplicación.")

        fila = ctk.CTkFrame(box, fg_color="transparent")
        fila.pack(fill="x", padx=20, pady=10)

        ctk.CTkLabel(fila, text="Tema por defecto:",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     width=160, anchor="w").pack(side="left")

        self.var_tema = ctk.StringVar(value="Dark")

        ctk.CTkRadioButton(
            fila, text="Oscuro", variable=self.var_tema, value="Dark",
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=8)

        ctk.CTkRadioButton(
            fila, text="Claro", variable=self.var_tema, value="Light",
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            fila, text="Aplicar ahora", width=130, height=30,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=11),
            command=self._aplicar_tema_ahora,
        ).pack(side="right")

    # ------------------------------------------------------------------
    # Sección: Escaneo
    # ------------------------------------------------------------------

    def _seccion_escaneo(self, parent):
        box = self._crear_seccion(
            parent, "🚀 Valores por defecto del escaneo",
            "Se aplicarán al abrir la app.")

        grid = ctk.CTkFrame(box, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=10)
        grid.grid_columnconfigure(1, weight=0)
        grid.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(grid, text="Días umbral:",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=0, column=0, sticky="w",
                                      padx=(0, 12), pady=6)

        self.entry_dias = ctk.CTkEntry(grid, width=80, height=32,
                                       justify="center")
        self.entry_dias.grid(row=0, column=1, sticky="w", pady=6)

        ctk.CTkLabel(grid,
                     text="Días hacia atrás para clasificar como 'Revisar'",
                     font=ctk.CTkFont(size=10),
                     text_color=("gray40", "gray60"),
                     anchor="w").grid(row=0, column=2, columnspan=2,
                                      sticky="w", padx=12, pady=6)

        ctk.CTkLabel(grid, text="Modo actuaciones:",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=1, column=0, sticky="w",
                                      padx=(0, 12), pady=6)

        self.var_modo = ctk.StringVar(value="personalizado")
        self.opt_modo = ctk.CTkOptionMenu(
            grid,
            values=["todas", "15dias", "1mes", "personalizado"],
            variable=self.var_modo,
            width=160, height=32,
            font=ctk.CTkFont(size=12),
            command=lambda _: self._actualizar_estado_cantidad(),
        )
        self.opt_modo.grid(row=1, column=1, sticky="w", pady=6)

        ctk.CTkLabel(grid,
                     text="Cómo filtrar las actuaciones del informe",
                     font=ctk.CTkFont(size=10),
                     text_color=("gray40", "gray60"),
                     anchor="w").grid(row=1, column=2, columnspan=2,
                                      sticky="w", padx=12, pady=6)

        ctk.CTkLabel(grid, text="Cantidad actuaciones:",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=2, column=0, sticky="w",
                                      padx=(0, 12), pady=6)

        self.entry_cantidad = ctk.CTkEntry(
            grid, width=80, height=32, justify="center")
        self.entry_cantidad.grid(row=2, column=1, sticky="w", pady=6)

        ctk.CTkLabel(grid,
                     text="Solo aplica cuando el modo es 'personalizado'",
                     font=ctk.CTkFont(size=10),
                     text_color=("gray40", "gray60"),
                     anchor="w").grid(row=2, column=2, columnspan=2,
                                      sticky="w", padx=12, pady=6)

    def _actualizar_estado_cantidad(self):
        if self.var_modo.get() == "personalizado":
            self.entry_cantidad.configure(state="normal")
        else:
            self.entry_cantidad.configure(state="disabled")

    # ------------------------------------------------------------------
    # Sección: WARP
    # ------------------------------------------------------------------

    def _seccion_warp(self, parent):
        box = self._crear_seccion(
            parent, "🌐 Estabilidad de consultas",
            "Mejora opcional para evitar bloqueos del portal de la Rama.")

        # Detectar WARP
        try:
            from services.ip_rotator import IPRotator
            rotator = IPRotator()
            estado_warp = rotator.warp_estado()
        except Exception as e:
            log.warning("No se pudo consultar WARP: %s", e)
            estado_warp = "desconocido"

        # Estado actual
        if estado_warp == "no-instalado":
            texto_estado = "⚠️  WARP no está instalado (la app funciona igual)"
            color_estado = ("#D97706", "#FBBF24")
        elif estado_warp == "conectado":
            texto_estado = "✅  WARP instalado y conectado"
            color_estado = ("#059669", "#34D399")
        elif estado_warp == "desconectado":
            texto_estado = "ℹ️  WARP instalado (se activa solo cuando hace falta)"
            color_estado = ("#0066FF", "#93C5FD")
        else:
            texto_estado = "❔  No se pudo determinar el estado de WARP"
            color_estado = ("gray40", "gray60")

        ctk.CTkLabel(
            box,
            text=texto_estado,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=color_estado,
        ).pack(anchor="w", padx=20, pady=(12, 6))

        ctk.CTkLabel(
            box,
            text=(
                "Cloudflare WARP es una herramienta GRATUITA que cambia tu IP\n"
                "automáticamente cuando el portal de la Rama bloquea la conexión.\n\n"
                "No requiere crear cuenta ni iniciar sesión. Solo se instala y ya.\n"
                "La app lo detecta automáticamente y lo usa solo si hace falta."
            ),
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
            justify="left", anchor="w",
        ).pack(anchor="w", padx=20, pady=(0, 12))

        botones = ctk.CTkFrame(box, fg_color="transparent")
        botones.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkButton(
            botones,
            text="🌐  Abrir página de descarga de WARP",
            width=280, height=36,
            fg_color=("#3B82F6", "#1E3A8A"),
            hover_color=("#2563EB", "#1D4ED8"),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: webbrowser.open("https://1.1.1.1/"),
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            botones,
            text="🔄  Verificar de nuevo",
            width=180, height=36,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=12),
            command=self._reconstruir_vista,
        ).pack(side="left")

        ctk.CTkLabel(
            box,
            text=(
                "📝 Cómo instalar WARP (1 minuto):\n"
                "  1. Pulsa el botón azul de arriba.\n"
                "  2. Descarga y ejecuta el instalador.\n"
                "  3. En la primera pantalla elige «Navegación privada (1.1.1.1)».\n"
                "  4. Acepta los términos y listo. No necesitas iniciar sesión."
            ),
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
            justify="left", anchor="w",
        ).pack(anchor="w", padx=20, pady=(0, 16))

    def _reconstruir_vista(self):
        """Recarga la vista para refrescar el estado de WARP."""
        messagebox.showinfo(
            "Verificación de WARP",
            "Si acabas de instalar WARP, ciérralo completamente y vuelve\n"
            "a pulsar esta opción. La app lo detectará automáticamente.",
            parent=self,
        )

    # ------------------------------------------------------------------
    # Sección: Capturas
    # ------------------------------------------------------------------

    def _seccion_capturas(self, parent):
        from services.limpieza import obtener_estadisticas_capturas

        box = self._crear_seccion(
            parent, "📸 Capturas de pantalla",
            "Las capturas se guardan en la carpeta /capturas.")

        # Checkbox: guardar capturas sí/no
        fila_check = ctk.CTkFrame(box, fg_color="transparent")
        fila_check.pack(fill="x", padx=20, pady=(12, 6))

        self.var_guardar_capturas = ctk.BooleanVar(
            value=bool(self.config.get("escaneo", "guardar_capturas", False)))

        ctk.CTkCheckBox(
            fila_check,
            text="Guardar capturas durante el escaneo",
            variable=self.var_guardar_capturas,
            font=ctk.CTkFont(size=12, weight="bold"),
            onvalue=True, offvalue=False,
        ).pack(side="left")

        ctk.CTkLabel(
            fila_check,
            text="(desactivado ahorra ~500 MB/mes en uso intensivo)",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
        ).pack(side="left", padx=8)

        # Retención
        fila_dias = ctk.CTkFrame(box, fg_color="transparent")
        fila_dias.pack(fill="x", padx=20, pady=(0, 6))

        ctk.CTkLabel(
            fila_dias, text="Auto-borrar capturas mayores a:",
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).pack(side="left")

        self.entry_dias_capturas = ctk.CTkEntry(
            fila_dias, width=70, height=30, justify="center")
        self.entry_dias_capturas.pack(side="left", padx=8)
        self.entry_dias_capturas.insert(
            0, str(self.config.get("escaneo",
                                    "dias_retencion_capturas", 15)))

        ctk.CTkLabel(
            fila_dias, text="días  (0 = nunca borrar)",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(side="left")

        # Estado actual
        try:
            stats = obtener_estadisticas_capturas()
            texto_stats = "📦 Uso actual: {} archivos · {}".format(
                stats["cantidad_archivos"], stats["tamano_legible"])
        except Exception as e:
            log.warning("No se pudo calcular uso de capturas: %s", e)
            texto_stats = "📦 No se pudo calcular el uso."

        ctk.CTkLabel(
            box, text=texto_stats,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#1D4ED8", "#93C5FD"),
        ).pack(anchor="w", padx=20, pady=(8, 6))

        # Botones de limpieza
        botones = ctk.CTkFrame(box, fg_color="transparent")
        botones.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkButton(
            botones,
            text="🧹  Limpiar antiguas",
            width=180, height=34,
            fg_color=("#F59E0B", "#B45309"),
            hover_color=("#D97706", "#92400E"),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._limpiar_capturas_antiguas,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            botones,
            text="🗑️  Borrar todas",
            width=160, height=34,
            fg_color=("#DC2626", "#7F1D1D"),
            hover_color=("#B91C1C", "#991B1B"),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._limpiar_todas_capturas,
        ).pack(side="left")

    def _limpiar_capturas_antiguas(self):
        from services.limpieza import (
            obtener_estadisticas_capturas,
            limpiar_capturas_antiguas,
        )

        try:
            dias = int(self.entry_dias_capturas.get())
        except ValueError:
            dias = 15

        if dias <= 0:
            messagebox.showwarning(
                "Valor inválido",
                "Los días deben ser mayores a 0.\n\n"
                "Si quieres borrar TODAS las capturas, "
                "usa el botón 'Borrar todas'.",
                parent=self,
            )
            return

        try:
            stats = obtener_estadisticas_capturas()
        except Exception:
            stats = {"cantidad_archivos": 0, "tamano_legible": "0 B"}

        if stats["cantidad_archivos"] == 0:
            messagebox.showinfo(
                "Sin capturas",
                "No hay capturas que borrar.",
                parent=self,
            )
            return

        pregunta = (
            "¿Borrar todas las capturas con más de {} días?\n\n"
            "Uso actual: {} archivos · {}\n\n"
            "Esta acción no se puede deshacer.".format(
                dias, stats["cantidad_archivos"], stats["tamano_legible"])
        )
        if not messagebox.askyesno("Confirmar limpieza", pregunta,
                                    parent=self):
            return

        try:
            resultado = limpiar_capturas_antiguas(dias=dias)
        except Exception as e:
            messagebox.showerror(
                "Error", "No se pudo limpiar:\n{}".format(e), parent=self)
            return

        self._mostrar_resultado_limpieza(resultado)

    def _limpiar_todas_capturas(self):
        from services.limpieza import (
            obtener_estadisticas_capturas,
            limpiar_todas_las_capturas,
        )

        try:
            stats = obtener_estadisticas_capturas()
        except Exception:
            stats = {"cantidad_archivos": 0, "tamano_legible": "0 B"}

        if stats["cantidad_archivos"] == 0:
            messagebox.showinfo(
                "Sin capturas",
                "No hay capturas que borrar.",
                parent=self,
            )
            return

        pregunta = (
            "¿Borrar TODAS las capturas?\n\n"
            "Uso actual: {} archivos · {}\n\n"
            "Esta acción no se puede deshacer.".format(
                stats["cantidad_archivos"], stats["tamano_legible"])
        )
        if not messagebox.askyesno("Confirmar limpieza", pregunta,
                                    parent=self):
            return

        try:
            resultado = limpiar_todas_las_capturas()
        except Exception as e:
            messagebox.showerror(
                "Error", "No se pudo limpiar:\n{}".format(e), parent=self)
            return

        self._mostrar_resultado_limpieza(resultado)

    def _mostrar_resultado_limpieza(self, resultado):
        if resultado["eliminados"] == 0:
            messagebox.showinfo(
                "Sin cambios",
                "No se encontraron capturas para borrar.",
                parent=self,
            )
            return

        mensaje = "✔ {} archivos eliminados.\n{} liberados.".format(
            resultado["eliminados"], resultado["tamano_legible"])
        if resultado.get("errores"):
            mensaje += "\n\n{} archivos no se pudieron borrar.".format(
                len(resultado["errores"]))
        messagebox.showinfo("Limpieza completa", mensaje, parent=self)

    # ------------------------------------------------------------------
    # Sección: Rutas
    # ------------------------------------------------------------------

    def _seccion_rutas(self, parent):
        box = self._crear_seccion(
            parent, "📁 Carpetas de la aplicación",
            "Ubicación de los archivos generados. Haz clic para abrirlas.")

        grid = ctk.CTkFrame(box, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=10)
        grid.grid_columnconfigure(1, weight=1)

        rutas = [
            ("Carpeta base", BASE_DIR),
            ("Capturas", CARPETA_CAPTURAS),
            ("Logs", CARPETA_LOGS),
            ("Respaldos Excel", CARPETA_RESPALDOS),
            ("Respaldos Radicados", CARPETA_RESPALDOS_RADICADOS),
            ("Pendientes", CARPETA_PENDIENTES),
        ]

        for i, (nombre, ruta) in enumerate(rutas):
            ctk.CTkLabel(grid, text=nombre + ":",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         anchor="w", width=140,
                         ).grid(row=i, column=0, sticky="w",
                                padx=(0, 12), pady=5)

            ctk.CTkLabel(grid, text=ruta,
                         font=ctk.CTkFont(size=11),
                         anchor="w", justify="left",
                         text_color=("gray40", "gray60"),
                         ).grid(row=i, column=1, sticky="ew", pady=5)

            ctk.CTkButton(
                grid, text="📂 Abrir", width=90, height=28,
                fg_color=("gray75", "#3A3A3C"),
                hover_color=("gray65", "#4A4A4C"),
                font=ctk.CTkFont(size=11),
                command=lambda r=ruta: self._abrir_carpeta(r),
            ).grid(row=i, column=2, padx=(8, 0), pady=5)

    # ------------------------------------------------------------------
    # Sección: Estadísticas
    # ------------------------------------------------------------------

    def _seccion_estadisticas(self, parent):
        box = self._crear_seccion(
            parent, "📊 Estadísticas globales",
            "Uso acumulado de la aplicación.")

        est = self.config.get_seccion("estadisticas_globales") or {}

        grid = ctk.CTkFrame(box, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=10)
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="stat")

        self._tarjeta_stat(grid, "Escaneos totales",
                           str(est.get("escaneos_totales", 0)), 0)
        self._tarjeta_stat(grid, "Radicados procesados",
                           str(est.get("radicados_procesados", 0)), 1)
        self._tarjeta_stat(grid, "Último escaneo",
                           (est.get("ultimo_escaneo") or "—")[:16], 2)

    def _tarjeta_stat(self, parent, titulo, valor, col):
        card = ctk.CTkFrame(parent, corner_radius=8,
                            fg_color=("gray90", "#242424"))
        card.grid(row=0, column=col, sticky="nsew", padx=4, pady=4)
        ctk.CTkLabel(card, text=titulo,
                     font=ctk.CTkFont(size=11),
                     text_color=("gray40", "gray60"),
                     ).pack(pady=(10, 2))
        ctk.CTkLabel(card, text=valor,
                     font=ctk.CTkFont(size=18, weight="bold"),
                     ).pack(pady=(0, 10))

    # ------------------------------------------------------------------
    # Utilidad: crear sección
    # ------------------------------------------------------------------

    def _crear_seccion(self, parent, titulo, subtitulo=""):
        contenedor = ctk.CTkFrame(parent, corner_radius=12)
        contenedor.pack(fill="x", padx=0, pady=8)

        header = ctk.CTkFrame(contenedor, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(14, 0))

        ctk.CTkLabel(
            header, text=titulo,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1D4ED8", "#93C5FD"),
        ).pack(anchor="w")

        if subtitulo:
            ctk.CTkLabel(
                header, text=subtitulo,
                font=ctk.CTkFont(size=11),
                text_color=("gray40", "gray60"),
            ).pack(anchor="w", pady=(2, 0))

        ctk.CTkFrame(contenedor, height=1,
                     fg_color=("gray70", "gray30"),
                     ).pack(fill="x", padx=20, pady=(10, 0))

        return contenedor

    # ------------------------------------------------------------------
    # Cargar / Guardar
    # ------------------------------------------------------------------

    def _cargar_valores(self):
        self.entry_nombre.insert(0, self.config.get("usuario", "nombre", ""))
        self.entry_email.insert(0, self.config.get("usuario", "email", ""))
        self.var_tema.set(self.config.get("usuario", "tema", "Dark"))

        self.entry_dias.insert(0, str(
            self.config.get("escaneo", "dias_umbral", 10)))
        self.var_modo.set(
            self.config.get("escaneo", "modo_actuaciones", "personalizado"))
        self.entry_cantidad.insert(
            0, str(self.config.get("escaneo", "cantidad_actuaciones", 5)))
        self._actualizar_estado_cantidad()

    def _guardar(self):
        try:
            self.config.set("usuario", "nombre",
                            self.entry_nombre.get().strip(),
                            auto_guardar=False)
            self.config.set("usuario", "email",
                            self.entry_email.get().strip(),
                            auto_guardar=False)
            self.config.set("usuario", "tema",
                            self.var_tema.get(), auto_guardar=False)

            try:
                dias = max(1, int(self.entry_dias.get()))
            except ValueError:
                dias = 10
            try:
                cantidad = max(1, min(20, int(self.entry_cantidad.get())))
            except ValueError:
                cantidad = 5

            self.config.set("escaneo", "dias_umbral", dias, auto_guardar=False)
            self.config.set("escaneo", "modo_actuaciones",
                            self.var_modo.get(), auto_guardar=False)
            self.config.set("escaneo", "cantidad_actuaciones",
                            cantidad, auto_guardar=False)

            # 👇 Guardar config de capturas
            try:
                self.config.set("escaneo", "guardar_capturas",
                                bool(self.var_guardar_capturas.get()),
                                auto_guardar=False)
            except Exception:
                pass

            try:
                dias_capt = max(0, int(self.entry_dias_capturas.get()))
            except (ValueError, AttributeError):
                dias_capt = 15
            try:
                self.config.set("escaneo", "dias_retencion_capturas",
                                dias_capt, auto_guardar=False)
            except Exception:
                pass

            self.config.guardar()

            messagebox.showinfo(
                "Guardado",
                "Configuración guardada correctamente.\n\n"
                "Los cambios se aplicarán al reiniciar la app,\n"
                "excepto el tema que puedes aplicar ahora mismo.",
                parent=self,
            )
            log.info("Configuración actualizada por el usuario.")
        except Exception as e:
            log.exception("Error guardando configuración: %s", e)
            messagebox.showerror("Error",
                                 "No se pudo guardar:\n{}".format(e),
                                 parent=self)

    def _restaurar_defaults(self):
        if not messagebox.askyesno(
                "Restaurar valores",
                "¿Restaurar todos los valores por defecto?\n\n"
                "Se conservarán las estadísticas globales y la licencia.",
                parent=self):
            return

        try:
            from data.config import DEFAULTS
            self.config.set_seccion("usuario", DEFAULTS["usuario"],
                                    auto_guardar=False)
            self.config.set_seccion("escaneo", DEFAULTS["escaneo"],
                                    auto_guardar=False)
            self.config.guardar()

            self.entry_nombre.delete(0, "end")
            self.entry_nombre.insert(0, DEFAULTS["usuario"]["nombre"])
            self.entry_email.delete(0, "end")
            self.entry_email.insert(0, DEFAULTS["usuario"]["email"])
            self.var_tema.set(DEFAULTS["usuario"]["tema"])
            self.entry_dias.delete(0, "end")
            self.entry_dias.insert(0,
                                    str(DEFAULTS["escaneo"]["dias_umbral"]))
            self.var_modo.set(DEFAULTS["escaneo"]["modo_actuaciones"])
            self.entry_cantidad.delete(0, "end")
            self.entry_cantidad.insert(
                0, str(DEFAULTS["escaneo"]["cantidad_actuaciones"]))

            # Restaurar capturas
            try:
                self.var_guardar_capturas.set(
                    DEFAULTS["escaneo"].get("guardar_capturas", False))
                self.entry_dias_capturas.delete(0, "end")
                self.entry_dias_capturas.insert(
                    0, str(DEFAULTS["escaneo"].get(
                        "dias_retencion_capturas", 15)))
            except Exception:
                pass

            self._actualizar_estado_cantidad()

            messagebox.showinfo(
                "Restaurado",
                "Configuración restaurada a los valores por defecto.",
                parent=self)
        except Exception as e:
            log.exception("Error restaurando defaults: %s", e)
            messagebox.showerror("Error",
                                 "No se pudo restaurar:\n{}".format(e),
                                 parent=self)

    def _aplicar_tema_ahora(self):
        try:
            ctk.set_appearance_mode(self.var_tema.get())
            self.config.set("usuario", "tema", self.var_tema.get())
            messagebox.showinfo("Tema aplicado",
                                "El tema se aplicó y guardó correctamente.",
                                parent=self)
        except Exception as e:
            messagebox.showerror("Error",
                                 "No se pudo aplicar el tema:\n{}".format(e),
                                 parent=self)

    def _abrir_carpeta(self, ruta):
        try:
            if not os.path.exists(ruta):
                os.makedirs(ruta, exist_ok=True)
            os.startfile(ruta)
        except AttributeError:
            subprocess.Popen(["xdg-open", ruta])
        except Exception as e:
            messagebox.showerror("Error",
                                 "No se pudo abrir la carpeta:\n{}".format(e),
                                 parent=self)