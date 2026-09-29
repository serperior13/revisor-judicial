# gui/views/historial_view.py
"""Vista del historial de escaneos."""

import logging
import os
import subprocess

import customtkinter as ctk
from tkinter import messagebox

from core.constantes import BASE_DIR

log = logging.getLogger(__name__)


class HistorialView(ctk.CTkFrame):
    """Vista de historial con tabla, filtros, zoom y acciones."""

    TAMANOS_FUENTE = [10, 11, 12, 13, 14, 16]
    TAMANO_INICIAL_IDX = 2   # 12 por defecto

    def __init__(self, parent, database):
        super().__init__(parent, fg_color="transparent")
        self.database = database

        self._escaneos = []
        self._escaneos_filtrados = []
        self._idx_fuente = self.TAMANO_INICIAL_IDX

        self.var_busqueda = ctk.StringVar()
        self.var_jurisdiccion = ctk.StringVar(value="Todas")

        # 👇 Debounce para la búsqueda por radicado
        self._search_after_id = None

        self._crear_layout()
        self.recargar()

    # ------------------------------------------------------------------
    # Fuente actual
    # ------------------------------------------------------------------

    @property
    def _tamano(self):
        return self.TAMANOS_FUENTE[self._idx_fuente]

    def _fuente(self, delta=0, weight="normal"):
        return ctk.CTkFont(family="Segoe UI",
                           size=self._tamano + delta, weight=weight)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _crear_layout(self):
        # --- Header ---
        header = ctk.CTkFrame(
            self, corner_radius=12, fg_color=("gray90", "#2B2B2B"))
        header.pack(fill="x", padx=14, pady=(10, 6))

        ctk.CTkLabel(
            header, text="📚 Historial de escaneos",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).pack(side="left", padx=16, pady=10)

        ctk.CTkButton(
            header, text="🔄  Actualizar", width=130, height=34,
            fg_color="#0066FF", hover_color="#0052CC",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.recargar,
        ).pack(side="right", padx=(4, 16), pady=10)

        ctk.CTkButton(
            header, text="🧹  Limpiar antiguos", width=160, height=34,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=12),
            command=self._limpiar_antiguos,
        ).pack(side="right", padx=4, pady=10)

        # --- Filtros + Zoom ---
        filtros = ctk.CTkFrame(self, corner_radius=12)
        filtros.pack(fill="x", padx=14, pady=4)

        ctk.CTkLabel(
            filtros, text="🔎  Buscar radicado:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(12, 4), pady=8)

        self.entry_busqueda = ctk.CTkEntry(
            filtros, textvariable=self.var_busqueda,
            width=240, height=32, placeholder_text="Ej: 110014003...")
        self.entry_busqueda.pack(side="left", padx=(0, 12), pady=8)
        # 👇 Reemplazado: antes llamaba directo, ahora usa debounce
        self.entry_busqueda.bind("<KeyRelease>", self._on_busqueda_key)

        ctk.CTkLabel(
            filtros, text="Jurisdicción:",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(0, 4))

        self.opt_juris = ctk.CTkOptionMenu(
            filtros, values=["Todas", "RAMA", "SAMAI"],
            variable=self.var_jurisdiccion,
            width=120, height=32,
            font=ctk.CTkFont(size=12),
            command=lambda _: self._aplicar_filtros(),
        )
        self.opt_juris.pack(side="left", padx=(0, 12))

        zoom_frame = ctk.CTkFrame(filtros, fg_color="transparent")
        zoom_frame.pack(side="right", padx=(0, 16))

        ctk.CTkLabel(
            zoom_frame, text="Zoom:",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            zoom_frame, text="🔍 −", width=44, height=30,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._reducir_fuente,
        ).pack(side="left", padx=2)

        self.lbl_zoom = ctk.CTkLabel(
            zoom_frame, text=str(self._tamano),
            font=ctk.CTkFont(size=12, weight="bold"),
            width=30)
        self.lbl_zoom.pack(side="left", padx=2)

        ctk.CTkButton(
            zoom_frame, text="🔍 +", width=44, height=30,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._aumentar_fuente,
        ).pack(side="left", padx=2)

        # --- Tabla ---
        self.tabla_frame = ctk.CTkFrame(self, corner_radius=12)
        self.tabla_frame.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        self._crear_encabezado_tabla()
        self.scroll = ctk.CTkScrollableFrame(self.tabla_frame, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=4, pady=(0, 6))

    # ------------------------------------------------------------------
    # Debounce búsqueda
    # ------------------------------------------------------------------

    def _on_busqueda_key(self, event=None):
        """Espera 300ms desde la última tecla antes de filtrar."""
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except Exception:
                pass
        self._search_after_id = self.after(300, self._ejecutar_filtro_debounced)

    def _ejecutar_filtro_debounced(self):
        self._search_after_id = None
        self._aplicar_filtros()

    # ------------------------------------------------------------------
    # Anchos dinámicos
    # ------------------------------------------------------------------

    def _anchos(self):
        f = self._tamano
        return [
            int(11 * f),   # Fecha
            int(6.5 * f),  # Juris.
            int(5 * f),    # Total
            int(6 * f),    # Revisar
            int(5.5 * f),  # Fuera
            int(6 * f),    # Errores
            int(24 * f),   # Acciones
        ]

    def _crear_encabezado_tabla(self):
        header = ctk.CTkFrame(self.tabla_frame,
                              fg_color=("gray85", "#2A2A2A"),
                              corner_radius=6, height=42)
        header.pack(fill="x", padx=4, pady=(6, 2))
        header.pack_propagate(False)

        self._header = header
        self._redibujar_encabezado()

    def _redibujar_encabezado(self):
        for w in self._header.winfo_children():
            w.destroy()
        for i, w in enumerate(self._anchos()):
            self._header.grid_columnconfigure(i, minsize=w)
        self._header.grid_columnconfigure(6, weight=1)

        titulos = ["Fecha", "Juris.", "Total", "Revisar", "Fuera",
                   "Errores", "Acciones"]
        for i, t in enumerate(titulos):
            ctk.CTkLabel(
                self._header, text=t,
                font=self._fuente(0, "bold"),
                anchor="w",
            ).grid(row=0, column=i, sticky="w", padx=8, pady=10)

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def _aumentar_fuente(self):
        if self._idx_fuente < len(self.TAMANOS_FUENTE) - 1:
            self._idx_fuente += 1
            self._aplicar_zoom()

    def _reducir_fuente(self):
        if self._idx_fuente > 0:
            self._idx_fuente -= 1
            self._aplicar_zoom()

    def _aplicar_zoom(self):
        self.lbl_zoom.configure(text=str(self._tamano))
        self._redibujar_encabezado()
        self._renderizar_filas()

    # ------------------------------------------------------------------
    # Carga de datos
    # ------------------------------------------------------------------

    def recargar(self):
        try:
            self._escaneos = self.database.listar_escaneos_con_stats(limite=500)
        except Exception as e:
            log.exception("Error leyendo historial: %s", e)
            self._escaneos = []
        self._aplicar_filtros()

    def _aplicar_filtros(self):
        texto = (self.var_busqueda.get() or "").strip()
        juris = (self.var_jurisdiccion.get() or "Todas").strip().upper()

        filtrados = self._escaneos

        if juris in ("RAMA", "SAMAI"):
            filtrados = [
                e for e in filtrados
                if (e.get("jurisdiccion") or "").strip().upper() == juris
            ]

        if texto:
            try:
                coincidentes = {
                    r["escaneo_id"]
                    for r in self.database.buscar_radicados_por_patron(texto)
                }
                filtrados = [e for e in filtrados if e["id"] in coincidentes]
            except Exception as e:
                log.warning("Error filtrando por radicado: %s", e)
                filtrados = []

        self._escaneos_filtrados = filtrados
        self._renderizar_filas()

    # ------------------------------------------------------------------
    # Render de filas
    # ------------------------------------------------------------------

    def _renderizar_filas(self):
        for w in self.scroll.winfo_children():
            w.destroy()

        if not self._escaneos_filtrados:
            ctk.CTkLabel(
                self.scroll,
                text="No hay escaneos que coincidan con los filtros.",
                font=self._fuente(0, "normal"),
                text_color=("gray50", "gray60"),
            ).pack(pady=40)
            return

        for esc in self._escaneos_filtrados:
            self._crear_fila(esc)

    def _crear_fila(self, esc):
        fecha = (esc.get("fecha_inicio") or "")[:16].replace("T", " ")
        juris = (esc.get("jurisdiccion") or "").upper() or "—"
        total = esc.get("cnt_total") or esc.get("total_radicados") or 0
        revisar = esc.get("cnt_revisar") or 0
        fuera = esc.get("cnt_fuera") or 0
        errores = esc.get("cnt_errores") or 0

        fila = ctk.CTkFrame(
            self.scroll, fg_color=("gray95", "#242424"),
            corner_radius=6, height=int(self._tamano * 3.2))
        fila.pack(fill="x", padx=2, pady=1)
        fila.pack_propagate(False)

        for i, w in enumerate(self._anchos()):
            fila.grid_columnconfigure(i, minsize=w)
        fila.grid_columnconfigure(6, weight=1)

        ctk.CTkLabel(
            fila, text=fecha or "—",
            font=self._fuente(), anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=6)

        if juris == "SAMAI":
            color_j = ("#1D4ED8", "#93C5FD")
        elif juris == "RAMA":
            color_j = ("#B45309", "#FDBA74")
        else:
            color_j = ("gray50", "gray60")

        ctk.CTkLabel(
            fila, text=juris or "—",
            font=self._fuente(0, "bold"),
            text_color=color_j, anchor="w",
        ).grid(row=0, column=1, sticky="w", padx=8, pady=6)

        ctk.CTkLabel(
            fila, text=str(total), font=self._fuente(), anchor="w",
        ).grid(row=0, column=2, sticky="w", padx=8, pady=6)

        ctk.CTkLabel(
            fila, text=str(revisar),
            font=self._fuente(0, "bold" if revisar else "normal"),
            text_color=("#B45309", "#FDBA74") if revisar else ("gray50", "gray60"),
            anchor="w",
        ).grid(row=0, column=3, sticky="w", padx=8, pady=6)

        ctk.CTkLabel(
            fila, text=str(fuera),
            font=self._fuente(0, "bold" if fuera else "normal"),
            text_color=("#92400E", "#FCD34D") if fuera else ("gray50", "gray60"),
            anchor="w",
        ).grid(row=0, column=4, sticky="w", padx=8, pady=6)

        ctk.CTkLabel(
            fila, text=str(errores),
            font=self._fuente(0, "bold" if errores else "normal"),
            text_color=("#991B1B", "#FCA5A5") if errores else ("gray50", "gray60"),
            anchor="w",
        ).grid(row=0, column=5, sticky="w", padx=8, pady=6)

        acc = ctk.CTkFrame(fila, fg_color="transparent")
        acc.grid(row=0, column=6, sticky="w", padx=8)

        ctk.CTkButton(
            acc, text="📂  Abrir", width=int(self._tamano * 7.5), height=30,
            font=self._fuente(-1, "bold"),
            fg_color=("#3B82F6", "#1E3A8A"),
            hover_color=("#2563EB", "#1D4ED8"),
            command=lambda e=esc: self._abrir_informe(e),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            acc, text="ℹ️  Informe", width=int(self._tamano * 8.5), height=30,
            font=self._fuente(-1, "bold"),
            fg_color=("#8B5CF6", "#5B21B6"),
            hover_color=("#7C3AED", "#4C1D95"),
            command=lambda e=esc: self._ver_detalle(e),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            acc, text="🗑️  Eliminar", width=int(self._tamano * 8.5), height=30,
            font=self._fuente(-1, "bold"),
            fg_color=("#DC2626", "#7F1D1D"),
            hover_color=("#B91C1C", "#991B1B"),
            command=lambda e=esc: self._eliminar(e),
        ).pack(side="left", padx=2)

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _abrir_informe(self, esc):
        ruta = esc.get("ruta_informe") or ""
        if not ruta:
            messagebox.showinfo("Sin archivo",
                                "Este escaneo no tiene informe guardado.")
            return
        candidatos = [
            ruta,
            os.path.join(BASE_DIR, os.path.basename(ruta)),
        ]
        for c in candidatos:
            if c and os.path.exists(c):
                try:
                    os.startfile(c)
                    return
                except AttributeError:
                    subprocess.Popen(["xdg-open", c])
                    return
        messagebox.showwarning(
            "Archivo no encontrado",
            "El informe ya no está en la carpeta original.\n\n"
            "Ubicación esperada:\n{}".format(ruta))

    def _ver_detalle(self, esc):
        try:
            resultados = self.database.obtener_resultados(esc["id"])
        except Exception as e:
            messagebox.showerror("Error",
                                 "No se pudieron leer los resultados:\n{}".format(e))
            return
        DetalleEscaneoModal(self, esc, resultados, self._tamano)

    def _eliminar(self, esc):
        if not messagebox.askyesno(
            "Eliminar escaneo",
            "¿Eliminar este escaneo del historial?\n\n"
            "Fecha: {}\nJurisdicción: {}\nTotal: {}".format(
                esc.get("fecha_inicio", "?")[:16],
                esc.get("jurisdiccion") or "—",
                esc.get("cnt_total") or 0)):
            return
        try:
            self.database.eliminar_escaneo(esc["id"])
            self.recargar()
        except Exception as e:
            messagebox.showerror("Error", "No se pudo eliminar:\n{}".format(e))

    def _limpiar_antiguos(self):
        if not messagebox.askyesno(
            "Limpiar historial",
            "¿Eliminar escaneos de más de 30 días?\n\n"
            "Esto no borra los Excel de respaldo, solo las entradas "
            "de la base de datos."):
            return
        try:
            n = self.database.eliminar_escaneos_antiguos(dias=30)
            messagebox.showinfo("Historial limpio",
                                "Se eliminaron {} escaneos antiguos.".format(n))
            self.recargar()
        except Exception as e:
            messagebox.showerror("Error", "No se pudo limpiar:\n{}".format(e))


# ====================================================================
# MODAL DE DETALLE
# ====================================================================

class DetalleEscaneoModal(ctk.CTkToplevel):
    """Ventana con la lista de radicados de un escaneo."""

    def __init__(self, parent, escaneo, resultados, tamano=12):
        super().__init__(parent)
        self.title("Detalle del escaneo")
        self.geometry("1100x650")
        self.minsize(800, 500)
        self.tamano = tamano

        self.transient(parent)
        self.grab_set()

        header = ctk.CTkFrame(self, corner_radius=10)
        header.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            header,
            text="📄 Escaneo del {}".format(
                (escaneo.get("fecha_inicio") or "")[:16]),
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(side="left", padx=14, pady=12)

        ctk.CTkLabel(
            header,
            text="Jurisdicción: {}   |   Total: {}".format(
                escaneo.get("jurisdiccion") or "—",
                len(resultados)),
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(side="right", padx=14, pady=12)

        scroll = ctk.CTkScrollableFrame(self, fg_color=("gray90", "#1E1E1E"))
        scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        if not resultados:
            ctk.CTkLabel(
                scroll, text="Sin resultados registrados.",
                font=ctk.CTkFont(size=13, slant="italic"),
            ).pack(pady=30)
            return

        for r in resultados:
            self._fila(scroll, r)

    def _fila(self, parent, r):
        fila = ctk.CTkFrame(
            parent, fg_color=("gray95", "#2A2A2A"), corner_radius=6)
        fila.pack(fill="x", padx=4, pady=3)

        top = ctk.CTkFrame(fila, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 3))

        ctk.CTkLabel(
            top, text=r.get("radicado") or "—",
            font=ctk.CTkFont(size=self.tamano, weight="bold"),
        ).pack(side="left")

        estado = r.get("estado") or "—"
        ctk.CTkLabel(
            top, text=estado,
            font=ctk.CTkFont(size=self.tamano - 1, weight="bold"),
            text_color=self._color_estado(estado),
        ).pack(side="right")

        if r.get("fecha_ultima_actuacion"):
            ctk.CTkLabel(
                fila, text="📅 Última actuación: " + r["fecha_ultima_actuacion"],
                font=ctk.CTkFont(size=self.tamano - 2),
                text_color=("gray40", "gray60"),
            ).pack(anchor="w", padx=12)

        partes = []
        if r.get("demandante"):
            partes.append("Dte: " + r["demandante"][:90])
        if r.get("demandado"):
            partes.append("Ddo: " + r["demandado"][:90])
        if partes:
            ctk.CTkLabel(
                fila, text=" | ".join(partes),
                font=ctk.CTkFont(size=self.tamano - 2),
                anchor="w", justify="left", wraplength=1000,
            ).pack(anchor="w", padx=12, pady=(3, 0))

        if r.get("observacion"):
            ctk.CTkLabel(
                fila, text="📝 " + r["observacion"][:250],
                font=ctk.CTkFont(size=self.tamano - 2),
                text_color=("gray40", "gray60"),
                anchor="w", justify="left", wraplength=1000,
            ).pack(anchor="w", padx=12, pady=(3, 10))

    @staticmethod
    def _color_estado(estado):
        e = (estado or "").lower()
        if e == "revisar":
            return ("#B45309", "#FDBA74")
        if "fuera de b" in e:
            return ("#92400E", "#FCD34D")
        if "⚠" in estado or "error" in e:
            return ("#991B1B", "#FCA5A5")
        return ("gray40", "gray60")