# gui/widgets/controles_escaneo.py
"""
Panel de controles: botones, campos numéricos y selección de jurisdicción.
"""

import customtkinter as ctk


class ControlesEscaneo(ctk.CTkFrame):
    """
    Contiene:
      Fila 1: Iniciar, Pausar, Detener, Desde N°, Días anteriores, Abrir Carpeta.
      Fila 2: Checkboxes de jurisdicción (Rama Judicial / SAMAI).
    """

    def __init__(self, parent, on_iniciar, on_pausar, on_detener, on_abrir_carpeta):
        super().__init__(parent, corner_radius=12)
        self.pack(fill="x", padx=14, pady=4)

        # ============================================================
        # FILA 1: Botones y campos numéricos
        # ============================================================
        fila1 = ctk.CTkFrame(self, fg_color="transparent")
        fila1.pack(fill="x", padx=0, pady=(0, 4))

        self.btn_iniciar = ctk.CTkButton(
            fila1, text="🚀 Iniciar Escaneo",
            width=134, height=32, corner_radius=9,
            fg_color="#0066FF", hover_color="#0052CC",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            command=on_iniciar,
        )
        self.btn_iniciar.pack(side="left", padx=(12, 4), pady=8)

        self.btn_pausar = ctk.CTkButton(
            fila1, text="⏸ Pausar",
            width=92, height=32, corner_radius=9,
            fg_color="#D97706", hover_color="#B45309",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            state="disabled", command=on_pausar,
        )
        self.btn_pausar.pack(side="left", padx=4, pady=8)

        self.btn_detener = ctk.CTkButton(
            fila1, text="🛑 Detener",
            width=92, height=32, corner_radius=9,
            fg_color="#DC2626", hover_color="#B91C1C",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            state="disabled", command=on_detener,
        )
        self.btn_detener.pack(side="left", padx=4, pady=8)

        ctk.CTkLabel(
            fila1, text="Desde N°:", font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=(12, 2))

        self.entry_inicio = ctk.CTkEntry(
            fila1, width=52, height=30, corner_radius=8, justify="center")
        self.entry_inicio.insert(0, "1")
        self.entry_inicio.pack(side="left", padx=2)

        ctk.CTkLabel(
            fila1, text="Días anteriores a revisar:",
            font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=(12, 2))

        self.entry_dias = ctk.CTkEntry(
            fila1, width=52, height=30, corner_radius=8, justify="center")
        self.entry_dias.insert(0, "10")
        self.entry_dias.pack(side="left", padx=2)

        self.btn_abrir_carpeta = ctk.CTkButton(
            fila1, text="📁 Abrir Carpeta",
            width=118, height=32, corner_radius=9,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            command=on_abrir_carpeta,
        )
        self.btn_abrir_carpeta.pack(side="right", padx=12, pady=8)

        # ============================================================
        # FILA 2: Checkboxes de jurisdicción
        # ============================================================
        fila2 = ctk.CTkFrame(self, fg_color="transparent")
        fila2.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkLabel(
            fila2, text="Jurisdicción a consultar:",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
        ).pack(side="left", padx=(0, 10))

        self.var_rama = ctk.BooleanVar(value=True)
        self.var_samai = ctk.BooleanVar(value=True)

        self.chk_rama = ctk.CTkCheckBox(
            fila2, text="Rama Judicial",
            variable=self.var_rama,
            font=ctk.CTkFont(size=11),
            checkbox_width=18, checkbox_height=18,
            border_width=1,
        )
        self.chk_rama.pack(side="left", padx=6)

        self.chk_samai = ctk.CTkCheckBox(
            fila2, text="SAMAI (Consejo de Estado)",
            variable=self.var_samai,
            font=ctk.CTkFont(size=11),
            checkbox_width=18, checkbox_height=18,
            border_width=1,
        )
        self.chk_samai.pack(side="left", padx=6)

        self.lbl_juris_info = ctk.CTkLabel(
            fila2,
            text="",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color=("gray40", "gray60"),
        )
        self.lbl_juris_info.pack(side="left", padx=(12, 0))

        # Trazabilidad de los checkboxes
        self.var_rama.trace_add("write", lambda *_: self._actualizar_info())
        self.var_samai.trace_add("write", lambda *_: self._actualizar_info())
        self._actualizar_info()

    # ------------------------------------------------------------------
    # Jurisdicciones
    # ------------------------------------------------------------------

    def _actualizar_info(self) -> None:
        """Muestra un mensaje de ayuda según lo que esté marcado."""
        rama = self.var_rama.get()
        samai = self.var_samai.get()
        if rama and samai:
            txt = "Se consultarán ambas jurisdicciones (con fallback automático)."
        elif rama:
            txt = "Solo se consultará la Rama Judicial (sin fallback)."
        elif samai:
            txt = "Solo se consultará SAMAI (sin fallback)."
        else:
            txt = "⚠️ Debes marcar al menos una jurisdicción."
        try:
            self.lbl_juris_info.configure(text=txt)
        except Exception:
            pass

    def get_jurisdicciones(self) -> set:
        """Devuelve el conjunto de jurisdicciones seleccionadas."""
        juris = set()
        if self.var_rama.get():
            juris.add("RAMA")
        if self.var_samai.get():
            juris.add("SAMAI")
        return juris

    def set_jurisdicciones(self, juris) -> None:
        """Aplica un conjunto de jurisdicciones a los checkboxes."""
        juris = {j.upper() for j in (juris or {"RAMA", "SAMAI"})}
        self.var_rama.set("RAMA" in juris)
        self.var_samai.set("SAMAI" in juris)
        self._actualizar_info()

    # ------------------------------------------------------------------
    # Valores numéricos
    # ------------------------------------------------------------------

    def get_indice_inicio(self) -> int:
        try:
            return max(1, int(self.entry_inicio.get()))
        except ValueError:
            return 1

    def get_dias_umbral(self) -> int:
        try:
            return max(1, int(self.entry_dias.get()))
        except ValueError:
            return 10

    def set_indice_inicio(self, valor: int) -> None:
        self.entry_inicio.delete(0, "end")
        self.entry_inicio.insert(0, str(valor))

    def set_dias_umbral(self, valor: int) -> None:
        self.entry_dias.delete(0, "end")
        self.entry_dias.insert(0, str(valor))

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def bloquear(self) -> None:
        """Deshabilita los controles mientras corre un escaneo."""
        self.btn_iniciar.configure(state="disabled", text="⏳ Procesando...")
        self.btn_pausar.configure(state="normal", text="⏸ Pausar", fg_color="#D97706")
        self.btn_detener.configure(state="normal")
        self.entry_inicio.configure(state="disabled")
        self.entry_dias.configure(state="disabled")
        self.chk_rama.configure(state="disabled")
        self.chk_samai.configure(state="disabled")

    def desbloquear(self) -> None:
        """Restaura el estado normal."""
        self.btn_iniciar.configure(state="normal", text="🚀 Iniciar Escaneo")
        self.btn_pausar.configure(state="disabled", text="⏸ Pausar", fg_color="#D97706")
        self.btn_detener.configure(state="disabled")
        self.entry_inicio.configure(state="normal")
        self.entry_dias.configure(state="normal")
        self.chk_rama.configure(state="normal")
        self.chk_samai.configure(state="normal")

    def marcar_pausado(self, pausado: bool) -> None:
        if pausado:
            self.btn_pausar.configure(text="▶ Reanudar", fg_color="#10B981")
        else:
            self.btn_pausar.configure(text="⏸ Pausar", fg_color="#D97706")