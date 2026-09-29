# gui/widgets/panel_progreso.py
"""
Panel de progreso con contador de tiempo transcurrido y ETA.
"""

import customtkinter as ctk

from core.constantes import INTERVALO_TICK_ETA_MS


class PanelProgreso(ctk.CTkFrame):
    """
    Panel con:
      - Label de progreso (X/Y radicados, %)
      - Label de ETA (transcurrido | ETA | ritmo)
      - Barra de progreso
    """

    def __init__(self, parent):
        super().__init__(parent, corner_radius=10)
        self.pack(fill="x", padx=14, pady=4)

        self._hora_inicio = None
        self._tiempos_consulta = []
        self._actual = 0
        self._total = 0
        self._tick_id = None
        self._activo = False

        # --- Fila superior: progreso (izq) + ETA (der) ---
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(6, 2))

        self.lbl_progreso = ctk.CTkLabel(
            top, text="Progreso: 0% (0/0 radicados)",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            anchor="w",
        )
        self.lbl_progreso.pack(side="left")

        self.lbl_eta = ctk.CTkLabel(
            top,
            text="⏱️ Transcurrido: 00s   |   ETA: —   |   Ritmo: —",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=("#1D4ED8", "#93C5FD"),
            anchor="e",
        )
        self.lbl_eta.pack(side="right")

        # --- Barra ---
        self.progress = ctk.CTkProgressBar(self, height=10, corner_radius=5)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=12, pady=(0, 6))

    # ------------------------------------------------------------------
    # Control del ciclo de vida
    # ------------------------------------------------------------------

    def iniciar(self, hora_inicio) -> None:
        """Se llama al arrancar un escaneo."""
        self._hora_inicio = hora_inicio
        self._tiempos_consulta = []
        self._actual = 0
        self._total = 0
        self.progress.set(0)
        self.lbl_progreso.configure(text="Progreso: 0% (0/0 radicados)")
        self.lbl_eta.configure(
            text="⏱️ Transcurrido: 00s   |   ETA: —   |   Ritmo: —")

        self._activo = True
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
        self._tick_id = self.after(INTERVALO_TICK_ETA_MS, self._tick)

    def detener(self) -> None:
        """Se llama al terminar el escaneo o al cerrar."""
        self._activo = False
        if self._tick_id is not None:
            try:
                self.after_cancel(self._tick_id)
            except Exception:
                pass
            self._tick_id = None

    # ------------------------------------------------------------------
    # Datos
    # ------------------------------------------------------------------

    def registrar_consulta(self, duracion_seg: float) -> None:
        """Llamado desde el worker al terminar cada consulta."""
        self.after(0, self._append_duracion, duracion_seg)

    def _append_duracion(self, dur: float) -> None:
        self._tiempos_consulta.append(dur)

    def set_progreso(self, actual: int, total: int) -> None:
        """Llamado desde el worker o desde el hilo principal."""
        self.after(0, self._update_progreso, actual, total)

    def _update_progreso(self, actual: int, total: int) -> None:
        self._actual = actual
        self._total = total
        porcentaje = (actual / total) if total > 0 else 0
        p_int = int(porcentaje * 100)
        self.progress.set(porcentaje)
        self.lbl_progreso.configure(
            text="Progreso: {}% ({}/{} radicados)".format(p_int, actual, total))
        self._refrescar_label_eta()

    # ------------------------------------------------------------------
    # Tick y formato
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        if not self._activo:
            return
        self._refrescar_label_eta()
        self._tick_id = self.after(INTERVALO_TICK_ETA_MS, self._tick)

    def _refrescar_label_eta(self) -> None:
        transcurrido = self._formatear_segundos(self._tiempo_transcurrido())
        eta_txt, promedio = self._calcular_eta()
        ritmo_txt = "—" if promedio is None else "{:.1f} s/rad".format(promedio)
        self.lbl_eta.configure(
            text="⏱️ Transcurrido: {}   |   ETA: {}   |   Ritmo: {}".format(
                transcurrido, eta_txt, ritmo_txt))

    def _tiempo_transcurrido(self) -> float:
        if self._hora_inicio is None:
            return 0.0
        return (self._hora_inicio.now() - self._hora_inicio).total_seconds()

    def _calcular_eta(self):
        if not self._tiempos_consulta:
            return "calculando...", None
        promedio = sum(self._tiempos_consulta) / len(self._tiempos_consulta)
        restantes = max(0, self._total - self._actual)
        if restantes == 0:
            return "00s", promedio
        return self._formatear_segundos(promedio * restantes), promedio

    @staticmethod
    def _formatear_segundos(seg) -> str:
        try:
            seg = int(round(seg))
        except (TypeError, ValueError):
            return "—"
        if seg < 0:
            return "—"
        h = seg // 3600
        m = (seg % 3600) // 60
        s = seg % 60
        if h > 0:
            return "{}h {:02d}m {:02d}s".format(h, m, s)
        if m > 0:
            return "{}m {:02d}s".format(m, s)
        return "{}s".format(s)