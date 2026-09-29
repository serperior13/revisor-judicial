# gui/widgets/tarjetas.py
"""
Tarjetas de estadísticas para la barra superior del GUI.
"""

import customtkinter as ctk


class TarjetaStat(ctk.CTkFrame):
    """
    Tarjeta con título y valor numérico grande.
    Pensada para mostrar contadores (Revisar, Errores, etc.).
    """

    def __init__(self, parent, titulo: str, fg_color, col: int):
        super().__init__(
            parent,
            corner_radius=10,
            fg_color=fg_color,
            border_width=1,
            border_color=("gray70", "gray30"),
        )
        self.grid(row=0, column=col, padx=3, pady=2, sticky="nsew")

        color_texto = ("#000000", "#FFFFFF")

        self.lbl_titulo = ctk.CTkLabel(
            self, text=titulo,
            font=ctk.CTkFont(size=10, weight="bold"),
            text_color=color_texto,
        )
        self.lbl_titulo.pack(pady=(6, 1))

        self.lbl_valor = ctk.CTkLabel(
            self, text="0",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=color_texto,
        )
        self.lbl_valor.pack(pady=(0, 6))

    def set_valor(self, valor: int) -> None:
        """Actualiza el número mostrado en la tarjeta."""
        self.lbl_valor.configure(text=str(int(valor)))


class PanelEstadisticas(ctk.CTkFrame):
    """
    Fila con las 5 tarjetas de estadísticas.
    Expone métodos para actualizar cada contador o todos a la vez.
    """

    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self.pack(fill="x", padx=14, pady=6)
        self.grid_columnconfigure((0, 1, 2, 3, 4), weight=1, uniform="stat_card")

        self.card_revisar = TarjetaStat(
            self, "🟡 Revisar", ("#FEF08A", "#854D0E"), 0)
        self.card_fuera = TarjetaStat(
            self, "⚪ Fuera de Rango", ("#E5E7EB", "#374151"), 1)
        self.card_sin_fecha = TarjetaStat(
            self, "⚪ Sin Fecha", ("#D1D5DB", "#4B5563"), 2)
        self.card_privados = TarjetaStat(
            self, "🔵 Privados", ("#BFDBFE", "#1E3A8A"), 3)
        self.card_errores = TarjetaStat(
            self, "🔴 Errores / Fallos", ("#FCA5A5", "#7F1D1D"), 4)

    def actualizar_todo(self, stats) -> None:
        """Recibe un objeto Estadisticas (core.modelos) y refresca las 5 tarjetas."""
        self.card_revisar.set_valor(stats.revisar)
        self.card_fuera.set_valor(stats.fuera)
        self.card_sin_fecha.set_valor(stats.sin_fecha)
        self.card_privados.set_valor(stats.privados)
        self.card_errores.set_valor(stats.errores)