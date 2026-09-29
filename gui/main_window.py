# gui/main_window.py
"""
Ventana principal del Revisor Judicial con sidebar de navegación.
"""

import logging
from tkinter import messagebox

import customtkinter as ctk

from core.constantes import ARCHIVO_EXCEL, ARCHIVO_SALIDA, BASE_DIR
from core.directorio import Directorio

from gui.views.acerca_view import AcercaView
from gui.views.config_view import ConfigView
from gui.views.directorio_view import DirectorioView
from gui.views.escaneo_view import EscaneoView
from gui.views.historial_view import HistorialView
from gui.views.radicados_view import RadicadosView
from gui.views.suscripcion_view import SuscripcionView

log = logging.getLogger(__name__)


class MainWindow(ctk.CTk):
    """Ventana principal de la aplicación."""

    def __init__(self, log_queue, config, database, estado_licencia="activa"):
        super().__init__()

        self.log_queue = log_queue
        self.config = config
        self.database = database
        self.estado_licencia = estado_licencia

        # Directorio judicial (correos, direcciones y teléfonos)
        self.directorio = Directorio(BASE_DIR)

        self.title(
            "Revisor Judicial — Monitoreo inteligente para Rama Judicial y SAMAI"
        )
        self.minsize(1100, 780)

        # Abrir maximizada al inicio (con fallback multiplataforma)
        self._abrir_maximizada()

        # Guardar geometría al redimensionar (con debounce)
        self._resize_after_id = None
        self.bind("<Configure>", self._on_window_configure)

        self._vista_actual = None
        self._botones_sidebar = {}

        self._crear_layout()

        # Si la licencia no es válida, abrir directamente Suscripción
        vista_inicial = (
            "suscripcion" if estado_licencia == "invalida" else "escaneo"
        )
        self._mostrar_vista(vista_inicial)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _crear_layout(self) -> None:
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ------------------ SIDEBAR ------------------
        self.sidebar = ctk.CTkFrame(
            self,
            width=220,
            corner_radius=0,
            fg_color=("gray85", "#1F1F1F"),
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)

        ctk.CTkLabel(
            self.sidebar,
            text="⚖️ Revisor Judicial",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        ).pack(padx=16, pady=(20, 4), anchor="w")

        ctk.CTkLabel(
            self.sidebar,
            text="Monitoreo Rama Judicial y SAMAI",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=("gray40", "gray60"),
        ).pack(padx=16, pady=(0, 20), anchor="w")

        # Botones de navegación
        self._crear_boton_sidebar("escaneo", "🚀  Escaneo")
        self._crear_boton_sidebar("radicados", "📋  Radicados")
        self._crear_boton_sidebar("historial", "📚  Historial")
        self._crear_boton_sidebar("directorio", "📞  Correos y Teléfonos")
        self._crear_boton_sidebar("suscripcion", "🔑  Suscripción")
        self._crear_boton_sidebar("configuracion", "⚙️  Configuración")
        self._crear_boton_sidebar("acerca", "ℹ️  Acerca de")

        ctk.CTkFrame(self.sidebar, fg_color="transparent").pack(
            fill="both", expand=True
        )

        # Botón de tema (footer del sidebar)
        self.btn_tema = ctk.CTkButton(
            self.sidebar,
            text="🌙 Modo Oscuro",
            width=180,
            height=32,
            corner_radius=18,
            fg_color=("#3B82F6", "#1E3A8A"),
            hover_color=("#2563EB", "#1D4ED8"),
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=self._alternar_tema,
        )
        self.btn_tema.pack(padx=20, pady=(0, 20))

        self._actualizar_texto_boton_tema()

        # ------------------ ÁREA DE VISTAS ------------------
        self.contenedor_vistas = ctk.CTkFrame(self, fg_color="transparent")
        self.contenedor_vistas.grid(
            row=0, column=1, sticky="nsew", padx=0, pady=0
        )
        self.contenedor_vistas.grid_rowconfigure(0, weight=1)
        self.contenedor_vistas.grid_columnconfigure(0, weight=1)

        # Instanciar vistas
        self.vistas = {
            "escaneo": EscaneoView(
                self.contenedor_vistas,
                log_queue=self.log_queue,
                config=self.config,
                database=self.database,
            ),
            "radicados": RadicadosView(
                self.contenedor_vistas,
                database=self.database,
            ),
            "historial": HistorialView(
                self.contenedor_vistas,
                database=self.database,
            ),
            "directorio": DirectorioView(
                self.contenedor_vistas,
                directorio=self.directorio,
            ),
            "configuracion": ConfigView(
                self.contenedor_vistas,
                config=self.config,
            ),
            "acerca": AcercaView(self.contenedor_vistas),
            "suscripcion": SuscripcionView(
                self.contenedor_vistas, config=self.config
            ),
        }
        self.vistas["escaneo"].on_escaneo_terminado = (
            self._on_escaneo_terminado
        )
        self.vistas["suscripcion"].on_licencia_activada = (
            self._on_licencia_activada
        )

    # ------------------------------------------------------------------

    def _crear_boton_sidebar(self, clave: str, texto: str) -> None:
        btn = ctk.CTkButton(
            self.sidebar,
            text=texto,
            width=180,
            height=38,
            corner_radius=8,
            fg_color="transparent",
            text_color=("gray20", "gray90"),
            hover_color=("gray75", "#3A3A3C"),
            anchor="w",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            command=lambda c=clave: self._mostrar_vista(c),
        )
        btn.pack(padx=20, pady=3)
        self._botones_sidebar[clave] = btn

    # ------------------------------------------------------------------
    # Navegación
    # ------------------------------------------------------------------

    def _mostrar_vista(self, clave: str) -> None:
        """Muestra la vista indicada. Bloquea las restringidas sin licencia."""

        # El directorio y radicados NO requieren licencia
        vistas_restringidas = ("escaneo", "historial")

        if (
            self.estado_licencia == "invalida"
            and clave in vistas_restringidas
        ):
            messagebox.showwarning(
                "Licencia requerida",
                "Necesitas activar una licencia o solicitar la prueba\n"
                "de 3 días para usar esta función.\n\n"
                "Ve a la sección 'Suscripción' para activarla.",
            )
            self._mostrar_vista("suscripcion")
            return

        if self._vista_actual is not None:
            self._vista_actual.pack_forget()

        # Actualizar resaltado del sidebar
        for k, btn in self._botones_sidebar.items():
            if k == clave:
                btn.configure(
                    fg_color=("#B4D3F5", "#2563EB"),
                    text_color=("#000000", "#FFFFFF"),
                )
            else:
                btn.configure(
                    fg_color="transparent",
                    text_color=("gray20", "gray90"),
                )

        if clave in self.vistas:
            vista = self.vistas[clave]
        else:
            vista = self._crear_vista_placeholder(clave)

        vista.pack(fill="both", expand=True)
        self._vista_actual = vista

    def _crear_vista_placeholder(self, clave: str) -> ctk.CTkFrame:
        """Placeholder para vistas aún no implementadas."""
        frame = ctk.CTkFrame(
            self.contenedor_vistas, fg_color="transparent"
        )

        titulos = {
            "historial": (
                "📚  Historial de escaneos",
                "Aquí verás los escaneos anteriores, con filtros y comparación.",
            ),
        }
        titulo, sub = titulos.get(clave, ("En construcción", ""))

        ctk.CTkLabel(
            frame,
            text=titulo,
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
        ).pack(pady=(80, 10))

        ctk.CTkLabel(
            frame,
            text=sub,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=("gray40", "gray70"),
        ).pack(pady=(0, 30))

        ctk.CTkLabel(
            frame,
            text="(próximamente)",
            font=ctk.CTkFont(family="Segoe UI", size=12, slant="italic"),
            text_color=("gray50", "gray60"),
        ).pack()

        return frame

    # ------------------------------------------------------------------
    # Tema
    # ------------------------------------------------------------------

    def _alternar_tema(self) -> None:
        if ctk.get_appearance_mode() == "Dark":
            ctk.set_appearance_mode("Light")
            tema = "Light"
        else:
            ctk.set_appearance_mode("Dark")
            tema = "Dark"
        self._actualizar_texto_boton_tema()
        try:
            if hasattr(self.config, "set"):
                self.config.set("usuario", "tema", tema)
        except Exception as e:
            log.warning("No se pudo guardar el tema: %s", e)
        self.update_idletasks()

    def _actualizar_texto_boton_tema(self) -> None:
        if ctk.get_appearance_mode() == "Dark":
            self.btn_tema.configure(
                text="☀️ Modo Claro",
                fg_color=("#F59E0B", "#D97706"),
            )
        else:
            self.btn_tema.configure(
                text="🌙 Modo Oscuro",
                fg_color=("#3B82F6", "#1E3A8A"),
            )

    # ------------------------------------------------------------------
    # Geometría y maximización
    # ------------------------------------------------------------------

    def _abrir_maximizada(self):
        """Abre la ventana maximizada. Compatible con Windows/Linux/macOS."""
        try:
            self.state("zoomed")
        except Exception:
            try:
                ancho_pantalla = self.winfo_screenwidth()
                alto_pantalla = self.winfo_screenheight()
                self.geometry(
                    "{}x{}+0+0".format(ancho_pantalla, alto_pantalla)
                )
            except Exception:
                self._restaurar_geometria()

    def _on_window_configure(self, event):
        """Detecta cambios de tamaño y programa el guardado con debounce."""
        if event.widget is not self:
            return

        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass

        self._resize_after_id = self.after(500, self._guardar_geometria)

    def _restaurar_geometria(self) -> None:
        ancho, alto, x, y = 1120, 880, None, None
        try:
            if hasattr(self.config, "get"):
                ancho = int(self.config.get("ventana", "ancho", 1120))
                alto = int(self.config.get("ventana", "alto", 880))
                x = self.config.get("ventana", "x", None)
                y = self.config.get("ventana", "y", None)
        except Exception as e:
            log.warning("No se pudo leer la geometría guardada: %s", e)

        if x is not None and y is not None:
            self.geometry("{}x{}+{}+{}".format(ancho, alto, x, y))
        else:
            self.geometry("{}x{}".format(ancho, alto))

    def _guardar_geometria(self) -> None:
        """Guarda la geometría actual (solo si NO está maximizada)."""
        try:
            self._resize_after_id = None

            if self.state() == "zoomed":
                return

            self.update_idletasks()
            ancho = self.winfo_width()
            alto = self.winfo_height()
            x = self.winfo_x()
            y = self.winfo_y()

            if ancho < 800 or alto < 600:
                return

            if hasattr(self.config, "set_seccion"):
                self.config.set_seccion(
                    "ventana",
                    {
                        "ancho": ancho,
                        "alto": alto,
                        "x": x,
                        "y": y,
                    },
                )
        except Exception as e:
            log.warning("No se pudo guardar la geometría: %s", e)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_escaneo_terminado(self) -> None:
        log.info("Escaneo terminado. Vistas listas para actualizarse.")

    def _on_licencia_activada(self) -> None:
        """Se llama cuando SuscripcionView activa una licencia exitosamente."""
        self.estado_licencia = "activa"
        log.info("✅ Estado de licencia actualizado a: activa")
        self._mostrar_vista("escaneo")

    def _on_close(self) -> None:
        try:
            vista = self.vistas.get("escaneo")
            if vista and hasattr(vista, "detener_por_cierre"):
                vista.detener_por_cierre()
        except Exception as e:
            log.warning("Error al detener la vista de escaneo: %s", e)

        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass

        self.destroy()