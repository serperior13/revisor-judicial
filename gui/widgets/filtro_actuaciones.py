# gui/widgets/filtro_actuaciones.py
"""
Panel del filtro de actuaciones (Todas / 15 días / Último mes / Personalizado).
"""

from tkinter import StringVar

import customtkinter as ctk


class FiltroActuaciones(ctk.CTkFrame):
    """
    Selección del modo de actuaciones a incluir en el informe.
    """

    def __init__(self, parent):
        super().__init__(parent, corner_radius=12)
        self.pack(fill="x", padx=14, pady=4)

        ctk.CTkLabel(
            self, text="Actuaciones en el informe:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        ).pack(side="left", padx=(12, 8), pady=6)

        self.modo = StringVar(value="personalizado")

        self.radio_todas = ctk.CTkRadioButton(
            self, text="Todas",
            variable=self.modo, value="todas",
            command=self._on_cambio,
            font=ctk.CTkFont(size=11),
        )
        self.radio_todas.pack(side="left", padx=6, pady=6)

        self.radio_15d = ctk.CTkRadioButton(
            self, text="Últimos 15 días",
            variable=self.modo, value="15dias",
            command=self._on_cambio,
            font=ctk.CTkFont(size=11),
        )
        self.radio_15d.pack(side="left", padx=6, pady=6)

        self.radio_mes = ctk.CTkRadioButton(
            self, text="Último mes",
            variable=self.modo, value="1mes",
            command=self._on_cambio,
            font=ctk.CTkFont(size=11),
        )
        self.radio_mes.pack(side="left", padx=6, pady=6)

        self.radio_personalizado = ctk.CTkRadioButton(
            self, text="Personalizado:",
            variable=self.modo, value="personalizado",
            command=self._on_cambio,
            font=ctk.CTkFont(size=11),
        )
        self.radio_personalizado.pack(side="left", padx=6, pady=6)

        self.option_cantidad = ctk.CTkOptionMenu(
            self,
            values=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
            width=64, height=26,
            font=ctk.CTkFont(size=11),
        )
        self.option_cantidad.set("5")
        self.option_cantidad.pack(side="left", padx=(2, 4), pady=6)

        ctk.CTkLabel(
            self, text="N° días de anotaciones",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
        ).pack(side="left", padx=(0, 8), pady=6)

        # Estado inicial consistente con el modo por defecto
        self._on_cambio()

    # ------------------------------------------------------------------

    def _on_cambio(self) -> None:
        if self.modo.get() == "personalizado":
            self.option_cantidad.configure(state="normal")
        else:
            self.option_cantidad.configure(state="disabled")

    def get_modo(self) -> str:
        return self.modo.get() or "personalizado"

    def get_cantidad(self) -> int:
        try:
            return int(self.option_cantidad.get())
        except (ValueError, TypeError):
            return 5

    def set_modo(self, modo: str) -> None:
        if modo not in ("todas", "15dias", "1mes", "personalizado"):
            modo = "personalizado"
        self.modo.set(modo)
        self._on_cambio()

    def set_cantidad(self, cantidad: int) -> None:
        cantidad = max(1, min(10, int(cantidad)))
        self.option_cantidad.set(str(cantidad))

    def bloquear(self) -> None:
        for r in (self.radio_todas, self.radio_15d,
                  self.radio_mes, self.radio_personalizado):
            r.configure(state="disabled")
        self.option_cantidad.configure(state="disabled")

    def desbloquear(self) -> None:
        for r in (self.radio_todas, self.radio_15d,
                  self.radio_mes, self.radio_personalizado):
            r.configure(state="normal")
        self._on_cambio()