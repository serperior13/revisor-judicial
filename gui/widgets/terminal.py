# gui/widgets/terminal.py
"""
Terminal de logs en vivo (recibe mensajes desde una queue.Queue).
"""

import queue

import customtkinter as ctk


class TerminalLogs(ctk.CTkFrame):
    """
    Panel con un CTkTextbox que consume una cola de logs y los muestra.
    """

    def __init__(self, parent, log_queue: "queue.Queue"):
        super().__init__(parent, corner_radius=12)
        self.log_queue = log_queue
        self._after_id = None

        ctk.CTkLabel(
            self, text=" Terminal de Ejecución ",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(6, 0))

        self.textbox = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=11),
            corner_radius=8,
        )
        self.textbox.pack(fill="both", expand=True, padx=8, pady=8)

    # ------------------------------------------------------------------

    def iniciar(self) -> None:
        """Empieza a refrescar la terminal cada 100 ms."""
        self._consumir_cola()

    def detener(self) -> None:
        """Detiene el refresco (útil al cerrar la ventana)."""
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _consumir_cola(self) -> None:
        """Vacía la cola y escribe los mensajes en el textbox."""
        while True:
            try:
                msg = self.log_queue.get_nowait()
            except queue.Empty:
                break
            try:
                self.textbox.insert("end", msg + "\n")
                self.textbox.see("end")
            except Exception:
                break

        # Vuelve a programarse en 100 ms
        try:
            self._after_id = self.after(100, self._consumir_cola)
        except Exception:
            self._after_id = None

    # ------------------------------------------------------------------

    def limpiar(self) -> None:
        """Borra todo el contenido de la terminal."""
        try:
            self.textbox.delete("1.0", "end")
        except Exception:
            pass