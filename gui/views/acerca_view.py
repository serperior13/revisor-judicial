# gui/views/acerca_view.py
"""Vista 'Acerca de' con información del producto."""

import os
import subprocess

import customtkinter as ctk

from core.constantes import BASE_DIR


class AcercaView(ctk.CTkFrame):
    """Información del producto, autor y contacto."""

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._crear_layout()

    # ------------------------------------------------------------------

    def _crear_layout(self):
        header = ctk.CTkFrame(
            self, corner_radius=12, fg_color=("gray90", "#2B2B2B"))
        header.pack(fill="x", padx=14, pady=(10, 6))
        ctk.CTkLabel(
            header,
            text="ℹ️ Acerca de Revisor Judicial",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
        ).pack(side="left", padx=16, pady=10)

        cont = ctk.CTkFrame(self, corner_radius=12)
        cont.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        ctk.CTkLabel(
            cont,
            text="⚖️  Revisor Judicial",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
        ).pack(pady=(30, 4))

        ctk.CTkLabel(
            cont,
            text="Edición 2026 Beta",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            text_color=("gray40", "gray70"),
        ).pack(pady=(0, 30))

        info_frame = ctk.CTkFrame(cont, fg_color="transparent")
        info_frame.pack(pady=10)

        self._agregar_info(info_frame, "Desarrollado por", "Córdoba y Abogados SAS")
        self._agregar_info(info_frame, "Contacto", "302 415 8837")
        self._agregar_info(info_frame, "Correo", "cordobayabogadossas@gmail.com")
        self._agregar_info(info_frame, "Versión", "1.0.0-beta")
        self._agregar_info(
            info_frame, "Jurisdicciones",
            "Rama Judicial · SAMAI (Consejo de Estado)")

        ctk.CTkLabel(
            cont,
            text=(
                "Herramienta de consulta automatizada para procesos judiciales.\n"
                "Permite escanear radicados en la Rama Judicial y en SAMAI,\n"
                "generar informes en Excel con clasificación automática y\n"
                "mantener un historial completo de las consultas realizadas."
            ),
            font=ctk.CTkFont(family="Segoe UI", size=12),
            justify="center",
            text_color=("gray30", "gray80"),
        ).pack(pady=20)

        ctk.CTkLabel(
            cont,
            text="Construido con Selenium, CustomTkinter, pandas y openpyxl.",
            font=ctk.CTkFont(family="Segoe UI", size=10, slant="italic"),
            text_color=("gray50", "gray60"),
        ).pack(pady=(10, 4))

        ctk.CTkButton(
            cont,
            text="📁 Abrir carpeta de la aplicación",
            width=260, height=36,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            command=self._abrir_carpeta,
        ).pack(pady=(20, 30))

    # ------------------------------------------------------------------

    def _agregar_info(self, parent, etiqueta, valor):
        fila = ctk.CTkFrame(parent, fg_color="transparent")
        fila.pack(fill="x", pady=2)
        ctk.CTkLabel(
            fila, text=etiqueta + ":",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=150, anchor="e",
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            fila, text=valor,
            font=ctk.CTkFont(size=12),
            anchor="w",
        ).pack(side="left")

    def _abrir_carpeta(self):
        try:
            os.startfile(BASE_DIR)
        except AttributeError:
            subprocess.Popen(["xdg-open", BASE_DIR])