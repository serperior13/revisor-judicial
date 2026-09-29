# gui/views/radicados_view.py
"""
Vista para gestionar los radicados de entrada (RAMA / SAMAI).

Permite:
  - Ver la lista actual con demandante/demandado (según historial).
  - Agregar nuevos (con validación).
  - Eliminar existentes.
  - Guardar cambios (con respaldo automático).
  - Ver y restaurar respaldos anteriores.
  - Actualizar la lista desde el Excel.

Nota: el scroll se reconstruye completo en cada recarga para evitar
bugs visuales de CTkScrollableFrame al cambiar el número de items.
"""

import logging
import os
import subprocess
from tkinter import messagebox

import customtkinter as ctk

from services.radicados_manager import (
    RadicadosManager,
    validar_radicado,
    limpiar_radicado,
)

log = logging.getLogger(__name__)


COLOR_VS = ("gray50", "gray50")


class RadicadosView(ctk.CTkFrame):
    """Vista de gestión de radicados."""

    def __init__(self, parent, database=None):
        super().__init__(parent, fg_color="transparent")
        self.manager = RadicadosManager()
        self.database = database
        self._jurisdiccion = "RAMA"
        self._hay_cambios = False
        self._partes_cache = {}
        self._scroll = None
        self._lista_frame = None

        self._crear_layout()
        self._recargar_lista()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _crear_layout(self):
        # --- Header ---
        header = ctk.CTkFrame(
            self, corner_radius=12, fg_color=("gray90", "#2B2B2B"))
        header.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            header,
            text="📋 Gestión de Radicados",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).pack(side="left", padx=16, pady=10)

        ctk.CTkButton(
            header, text="🔄  Actualizar", width=140, height=34,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._actualizar_desde_disco,
        ).pack(side="right", padx=(4, 16), pady=10)

        ctk.CTkButton(
            header, text="💾  Guardar cambios", width=180, height=34,
            fg_color="#0066FF", hover_color="#0052CC",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._guardar,
        ).pack(side="right", padx=4, pady=10)

        # --- Selector de jurisdicción ---
        selector = ctk.CTkFrame(self, corner_radius=12)
        selector.pack(fill="x", padx=14, pady=4)

        ctk.CTkLabel(
            selector, text="Jurisdicción:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(12, 8), pady=10)

        self.seg_juris = ctk.CTkSegmentedButton(
            selector,
            values=["RAMA", "SAMAI"],
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_jurisdiccion_cambiada,
        )
        self.seg_juris.set("RAMA")
        self.seg_juris.pack(side="left", padx=4, pady=10)

        self.lbl_info = ctk.CTkLabel(
            selector, text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        self.lbl_info.pack(side="left", padx=16, pady=10)

        # --- Agregar radicado ---
        agregar = ctk.CTkFrame(self, corner_radius=12)
        agregar.pack(fill="x", padx=14, pady=4)

        ctk.CTkLabel(
            agregar, text="➕  Agregar radicado:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(12, 8), pady=10)

        self.entry_nuevo = ctk.CTkEntry(
            agregar, height=34,
            placeholder_text="Ej: 11001400301820250072500",
        )
        self.entry_nuevo.pack(side="left", fill="x", expand=True,
                              padx=(0, 8), pady=10)
        self.entry_nuevo.bind("<Return>", lambda e: self._agregar())

        ctk.CTkButton(
            agregar, text="Agregar", width=110, height=34,
            fg_color="#059669", hover_color="#047857",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._agregar,
        ).pack(side="left", padx=(0, 12), pady=10)

        # --- Contenedor de lista ---
        self._lista_frame = ctk.CTkFrame(self, corner_radius=12)
        self._lista_frame.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        header_lista = ctk.CTkFrame(self._lista_frame, fg_color="transparent")
        header_lista.pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkLabel(
            header_lista, text="Radicados actuales:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=("#1D4ED8", "#93C5FD"),
        ).pack(side="left")

        self.lbl_contador = ctk.CTkLabel(
            header_lista, text="0 radicados",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        )
        self.lbl_contador.pack(side="right")

        ctk.CTkFrame(self._lista_frame, height=1,
                     fg_color=("gray70", "gray30")).pack(fill="x", padx=12)

        # El scroll se crea en _recargar_lista() para poder destruirlo
        # y recrearlo completo cada vez.

        # --- Acciones inferiores ---
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkButton(
            footer, text="↩️  Descartar cambios", width=200, height=34,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=12),
            command=self._descartar,
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            footer, text="📦  Ver respaldos", width=180, height=34,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=12),
            command=self._ver_respaldos,
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            footer, text="📂  Abrir carpeta respaldos", width=220, height=34,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=12),
            command=self._abrir_carpeta_respaldos,
        ).pack(side="left", padx=2)

        self.lbl_estado = ctk.CTkLabel(
            footer, text="",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.lbl_estado.pack(side="right", padx=12)

    # ------------------------------------------------------------------
    # Cambio de jurisdicción
    # ------------------------------------------------------------------

    def _on_jurisdiccion_cambiada(self, valor):
        if self._hay_cambios:
            respuesta = messagebox.askyesno(
                "Cambios sin guardar",
                "Tienes cambios sin guardar en la lista actual.\n\n"
                "¿Descartarlos y cambiar de jurisdicción?",
                parent=self,
            )
            if not respuesta:
                self.seg_juris.set(self._jurisdiccion)
                return
            self.manager.descartar_cambios(self._jurisdiccion)

        self._jurisdiccion = valor
        self._hay_cambios = False
        self._recargar_lista()

    # ------------------------------------------------------------------
    # Consulta de partes
    # ------------------------------------------------------------------

    def _obtener_partes(self, radicado: str):
        if not self.database:
            return None

        if radicado in self._partes_cache:
            return self._partes_cache[radicado]

        partes = None
        try:
            filas = self.database.buscar_radicado(radicado)
            if filas:
                f = filas[0]
                demandante = (f.get("demandante") or "").strip()
                demandado = (f.get("demandado") or "").strip()

                if demandante in ("Sin demandante", "Proceso Privado"):
                    demandante = ""
                if demandado in ("Sin demandado", "Proceso Privado"):
                    demandado = ""

                if demandante or demandado:
                    partes = {
                        "demandante": demandante,
                        "demandado": demandado,
                    }
        except Exception as e:
            log.debug("No se pudieron leer partes de %s: %s", radicado, e)

        self._partes_cache[radicado] = partes
        return partes

    # ------------------------------------------------------------------
    # Lista
    # ------------------------------------------------------------------

    def _destruir_scroll(self):
        """Destruye el scroll actual si existe."""
        if self._scroll is not None:
            try:
                self._scroll.destroy()
            except Exception:
                pass
            self._scroll = None

    def _crear_scroll(self):
        """Crea un CTkScrollableFrame nuevo dentro de _lista_frame."""
        self._scroll = ctk.CTkScrollableFrame(
            self._lista_frame, fg_color="transparent")
        self._scroll.pack(
            fill="both", expand=True, padx=8, pady=(6, 12))

    def _recargar_lista(self):
        """
        Recarga la lista. Reconstruye el scroll entero para evitar bugs
        de CTkScrollableFrame al cambiar el número de items.
        """
        # 1) Destruir el scroll viejo (evita el bug visual)
        self._destruir_scroll()

        # 2) Crear uno nuevo
        self._crear_scroll()

        # 3) Cargar radicados
        radicados = self.manager.listar_actuales(self._jurisdiccion)
        self.lbl_contador.configure(
            text="{} radicado{}".format(
                len(radicados), "s" if len(radicados) != 1 else "")
        )

        self.lbl_info.configure(
            text="Editando: {}".format(
                "Procesos.xlsx" if self._jurisdiccion == "RAMA"
                else "Radicados_SAMAI.xlsx")
        )

        # 4) Poblar
        if not radicados:
            ctk.CTkLabel(
                self._scroll,
                text="No hay radicados en la lista.\n"
                     "Agrega uno arriba o pulsa 'Actualizar'.",
                font=ctk.CTkFont(size=12, slant="italic"),
                text_color=("gray50", "gray60"),
                justify="center",
            ).pack(pady=40)
        else:
            for i, rad in enumerate(radicados, start=1):
                self._crear_fila(i, rad)

        # 5) Forzar layout (evita que quede el alto del scroll viejo)
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _crear_fila(self, indice, radicado):
        partes = self._obtener_partes(radicado)

        fila = ctk.CTkFrame(
            self._scroll,
            corner_radius=6,
            fg_color=("gray95", "#2A2A2A"),
            height=64 if partes else 46,
        )
        fila.pack(fill="x", padx=2, pady=3)
        fila.pack_propagate(False)

        # Contenedor izquierdo (índice + datos)
        izq = ctk.CTkFrame(fila, fg_color="transparent")
        izq.pack(side="left", fill="x", expand=True, padx=(10, 4), pady=6)

        # Línea 1: índice + radicado
        linea1 = ctk.CTkFrame(izq, fg_color="transparent")
        linea1.pack(fill="x", anchor="w")

        ctk.CTkLabel(
            linea1, text="{:>3}.".format(indice),
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=("gray50", "gray60"),
            width=40,
        ).pack(side="left")

        ctk.CTkLabel(
            linea1, text=radicado,
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            anchor="w",
        ).pack(side="left", padx=4)

        # Línea 2: partes
        if partes:
            linea2 = ctk.CTkFrame(izq, fg_color="transparent")
            linea2.pack(fill="x", anchor="w", pady=(2, 0))

            ctk.CTkLabel(
                linea2, text=" " * 5,
                font=ctk.CTkFont(size=11),
                width=40,
            ).pack(side="left")

            ctk.CTkLabel(
                linea2,
                text=partes["demandante"] or "—",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#1D4ED8", "#93C5FD"),
                anchor="w",
            ).pack(side="left", padx=(4, 2))

            ctk.CTkLabel(
                linea2, text="vs",
                font=ctk.CTkFont(size=10, slant="italic"),
                text_color=COLOR_VS,
            ).pack(side="left", padx=2)

            ctk.CTkLabel(
                linea2,
                text=partes["demandado"] or "—",
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color=("#B45309", "#FDBA74"),
                anchor="w",
            ).pack(side="left", padx=(2, 0))

        # Botón eliminar
        ctk.CTkButton(
            fila, text="🗑️", width=42, height=28,
            fg_color=("#DC2626", "#7F1D1D"),
            hover_color=("#B91C1C", "#991B1B"),
            font=ctk.CTkFont(size=14),
            command=lambda r=radicado: self._eliminar(r),
        ).pack(side="right", padx=(4, 10))

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _actualizar_desde_disco(self):
        if self._hay_cambios:
            respuesta = messagebox.askyesno(
                "Cambios sin guardar",
                "Tienes cambios sin guardar.\n\n"
                "¿Descartarlos y recargar desde el Excel?",
                parent=self,
            )
            if not respuesta:
                return

        self.manager.descartar_cambios(self._jurisdiccion)
        self._hay_cambios = False
        self._partes_cache.clear()
        self._recargar_lista()
        self._marcar_limpio()
        log.info("🔄 Lista de %s recargada desde disco.", self._jurisdiccion)

    def _agregar(self):
        texto = self.entry_nuevo.get().strip()
        if not texto:
            return

        ok, error = self.manager.agregar(self._jurisdiccion, texto)
        if not ok:
            messagebox.showwarning(
                "Radicado inválido", error, parent=self)
            return

        self.entry_nuevo.delete(0, "end")
        self._hay_cambios = True
        self._recargar_lista()
        self._marcar_sucios()
        self.entry_nuevo.focus_set()

    def _eliminar(self, radicado):
        respuesta = messagebox.askyesno(
            "Eliminar radicado",
            "¿Eliminar el radicado?\n\n{}\n\n"
            "(El cambio no se guarda hasta pulsar 'Guardar cambios')".format(
                radicado),
            parent=self,
        )
        if not respuesta:
            return

        if self.manager.eliminar(self._jurisdiccion, radicado):
            self._hay_cambios = True
            self._recargar_lista()
            self._marcar_sucios()

    def _guardar(self):
        radicados = self.manager.listar_actuales(self._jurisdiccion)
        if not radicados:
            respuesta = messagebox.askyesno(
                "Lista vacía",
                "La lista está vacía. ¿Guardar de todos modos?",
                parent=self,
            )
            if not respuesta:
                return

        ok, mensaje = self.manager.guardar(self._jurisdiccion, radicados)
        if ok:
            self._hay_cambios = False
            self._marcar_limpio()
            messagebox.showinfo("Guardado", mensaje, parent=self)
        else:
            messagebox.showerror("Error", mensaje, parent=self)

    def _descartar(self):
        if not self._hay_cambios:
            messagebox.showinfo(
                "Sin cambios",
                "No hay cambios pendientes por descartar.",
                parent=self,
            )
            return

        respuesta = messagebox.askyesno(
            "Descartar cambios",
            "¿Descartar los cambios sin guardar?\n\n"
            "Se restaurará la lista desde el Excel.",
            parent=self,
        )
        if not respuesta:
            return

        self.manager.descartar_cambios(self._jurisdiccion)
        self._hay_cambios = False
        self._recargar_lista()
        self._marcar_limpio()

    def _ver_respaldos(self):
        respaldos = self.manager.listar_respaldos(self._jurisdiccion)
        if not respaldos:
            messagebox.showinfo(
                "Sin respaldos",
                "No hay respaldos de esta jurisdicción todavía.\n\n"
                "Se crea uno automáticamente cada vez que guardas.",
                parent=self,
            )
            return

        ModalRespaldos(self, self.manager, self._jurisdiccion, respaldos,
                       on_restaurar=self._on_respaldo_restaurado)

    def _on_respaldo_restaurado(self):
        self._hay_cambios = False
        self._partes_cache.clear()
        self._recargar_lista()
        self._marcar_limpio()

    def _abrir_carpeta_respaldos(self):
        from core.constantes import CARPETA_RESPALDOS_RADICADOS
        try:
            os.startfile(CARPETA_RESPALDOS_RADICADOS)
        except AttributeError:
            subprocess.Popen(["xdg-open", CARPETA_RESPALDOS_RADICADOS])
        except Exception as e:
            messagebox.showerror(
                "Error", "No se pudo abrir la carpeta:\n{}".format(e),
                parent=self,
            )

    # ------------------------------------------------------------------
    # Indicador de cambios
    # ------------------------------------------------------------------

    def _marcar_sucios(self):
        self.lbl_estado.configure(
            text="● Cambios sin guardar",
            text_color=("#D97706", "#FBBF24"),
        )

    def _marcar_limpio(self):
        self.lbl_estado.configure(text="", text_color=("gray40", "gray60"))


# ====================================================================
# MODAL DE RESPALDOS
# ====================================================================

class ModalRespaldos(ctk.CTkToplevel):
    def __init__(self, parent, manager, jurisdiccion, respaldos,
                 on_restaurar=None):
        super().__init__(parent)
        self.manager = manager
        self.jurisdiccion = jurisdiccion
        self.respaldos = respaldos
        self.on_restaurar = on_restaurar

        self.title("Respaldos de {}".format(jurisdiccion))
        self.geometry("640x520")
        self.minsize(560, 400)
        self.transient(parent)
        self.grab_set()

        header = ctk.CTkFrame(self, corner_radius=10)
        header.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            header, text="📦 Respaldos de {}".format(jurisdiccion),
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left", padx=14, pady=12)

        ctk.CTkLabel(
            header, text="{} archivos".format(len(self.respaldos)),
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(side="right", padx=14, pady=12)

        scroll = ctk.CTkScrollableFrame(self, fg_color=("gray90", "#1E1E1E"))
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        for r in self.respaldos:
            self._fila(scroll, r)

    def _fila(self, parent, ruta):
        fila = ctk.CTkFrame(
            parent, corner_radius=6, fg_color=("gray95", "#2A2A2A"))
        fila.pack(fill="x", padx=4, pady=3)

        info = ctk.CTkFrame(fila, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True, padx=12, pady=8)

        ctk.CTkLabel(
            info, text=ruta.name,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            anchor="w",
        ).pack(anchor="w")

        try:
            import datetime as dt
            mtime = dt.datetime.fromtimestamp(ruta.stat().st_mtime)
            fecha_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
            tam_kb = ruta.stat().st_size / 1024
            ctk.CTkLabel(
                info, text="{} · {:.1f} KB".format(fecha_str, tam_kb),
                font=ctk.CTkFont(size=10),
                text_color=("gray40", "gray60"),
                anchor="w",
            ).pack(anchor="w")
        except Exception:
            pass

        ctk.CTkButton(
            fila, text="↩️ Restaurar", width=120, height=30,
            fg_color=("#8B5CF6", "#5B21B6"),
            hover_color=("#7C3AED", "#4C1D95"),
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._restaurar(ruta),
        ).pack(side="right", padx=12, pady=8)

    def _restaurar(self, ruta):
        respuesta = messagebox.askyesno(
            "Restaurar respaldo",
            "¿Restaurar este respaldo?\n\n{}\n\n"
            "El Excel actual se respaldará antes de sobreescribirse.".format(
                ruta.name),
            parent=self,
        )
        if not respuesta:
            return

        ok, mensaje = self.manager.restaurar_respaldo(
            self.jurisdiccion, ruta)
        if ok:
            messagebox.showinfo("Restaurado", mensaje, parent=self)
            if callable(self.on_restaurar):
                self.on_restaurar()
            self.destroy()
        else:
            messagebox.showerror("Error", mensaje, parent=self)