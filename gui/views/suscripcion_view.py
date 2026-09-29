# gui/views/suscripcion_view.py
"""
Vista de suscripción con planes de precios y estado de la licencia.
Se conecta con services/licencias.py y la API de cordobayabogados.com

Comportamiento offline:
  - Si el servidor responde OK → licencia normal (verde).
  - Si el servidor NO responde pero la última validación fue reciente
    (< 7 días) → mostrar como activa normal, con un texto gris discreto.
  - Si el servidor NO responde y han pasado > 7 días → aviso de
    "Requiere conexión" con opción de reintentar.
  - Si el servidor responde con código de error (VENCIDA/REVOCADA) →
    mostrar el estado real.
"""

import logging
import threading
import webbrowser
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from services import licencias

log = logging.getLogger(__name__)


# Días que se permite la app sin poder contactar al servidor.
# Debe coincidir con DIAS_GRACIA_OFFLINE de main.py.
DIAS_GRACIA_OFFLINE = 7


# ====================================================================
# CONFIGURACIÓN DE PLANES
# ====================================================================
PLANES = [
    {
        "nombre": "Prueba",
        "precio": "Gratis",
        "periodo": "3 días",
        "descripcion": "Prueba todas las funciones",
        "caracteristicas": ["Acceso completo", "Escaneo ilimitado", "1 PC"],
        "boton_texto": "Probar Gratis",
        "color": "#8B5CF6",
        "icono": "🎁",
        "link_pago": None,
        "destacado": False,
    },
    {
        "nombre": "Mensual",
        "precio": "$49.900",
        "periodo": "COP / 30 días",
        "descripcion": "Ideal para empezar",
        "caracteristicas": [
            "Acceso completo", "Escaneo ilimitado",
            "1 PC por licencia", "Soporte por correo",
        ],
        "boton_texto": "Comprar",
        "color": "#0066FF",
        "icono": "💼",
        "link_pago": "https://cordobayabogados.com/checkout.html?plan=mensual",
        "destacado": False,
    },
    {
        "nombre": "Trimestral",
        "precio": "$129.900",
        "periodo": "COP / 90 días",
        "descripcion": "Ahorra 13% vs mensual",
        "caracteristicas": [
            "Acceso completo", "Escaneo ilimitado",
            "2 PCs por licencia", "Soporte prioritario",
        ],
        "boton_texto": "Comprar",
        "color": "#F59E0B",
        "icono": "⚡",
        "link_pago": "https://cordobayabogados.com/checkout.html?plan=trimestral",
        "destacado": False,
    },
    {
        "nombre": "Semestral",
        "precio": "$229.900",
        "periodo": "COP / 180 días",
        "descripcion": "Ahorra 23% vs mensual",
        "caracteristicas": [
            "Acceso completo", "Escaneo ilimitado",
            "3 PCs por licencia", "Soporte prioritario",
        ],
        "boton_texto": "Comprar",
        "color": "#EC4899",
        "icono": "🔥",
        "link_pago": "https://cordobayabogados.com/checkout.html?plan=semestral",
        "destacado": False,
    },
    {
        "nombre": "Anual",
        "precio": "$399.900",
        "periodo": "COP / 365 días",
        "descripcion": "El mejor valor — 33% de ahorro",
        "caracteristicas": [
            "Acceso completo", "Escaneo ilimitado",
            "5 PCs por licencia", "Soporte VIP",
            "Actualizaciones incluidas",
        ],
        "boton_texto": "Comprar",
        "color": "#059669",
        "icono": "⭐",
        "link_pago": "https://cordobayabogados.com/checkout.html?plan=anual",
        "destacado": True,
    },
]


# ====================================================================
# WIDGET: TARJETA DE PLAN
# ====================================================================

class TarjetaPlan(ctk.CTkFrame):
    """Tarjeta de precios para un plan."""

    def __init__(self, parent, plan_data, on_click):
        super().__init__(
            parent,
            corner_radius=16,
            border_width=2,
            border_color=plan_data["color"],
            fg_color=("gray95", "#1F1F1F"),
        )
        self.plan_data = plan_data
        self.on_click = on_click

        if plan_data.get("destacado"):
            badge = ctk.CTkLabel(
                self,
                text="  RECOMENDADO  ",
                font=ctk.CTkFont(size=10, weight="bold"),
                fg_color=plan_data["color"],
                corner_radius=8,
                text_color="white",
            )
            badge.pack(pady=(12, 0))

        ctk.CTkLabel(
            self,
            text="{} {}".format(plan_data["icono"], plan_data["nombre"]),
            font=ctk.CTkFont(size=20, weight="bold"),
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            self,
            text=plan_data["precio"],
            font=ctk.CTkFont(size=30, weight="bold"),
            text_color=plan_data["color"],
        ).pack(pady=(10, 0))

        ctk.CTkLabel(
            self,
            text=plan_data["periodo"],
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(pady=(0, 8))

        ctk.CTkLabel(
            self,
            text=plan_data["descripcion"],
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(pady=(4, 14))

        ctk.CTkFrame(self, height=1, fg_color=("gray70", "gray30")).pack(
            fill="x", padx=20, pady=(0, 12))

        for carac in plan_data["caracteristicas"]:
            fila = ctk.CTkFrame(self, fg_color="transparent")
            fila.pack(fill="x", padx=20, pady=2)

            ctk.CTkLabel(
                fila, text="✓",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=plan_data["color"],
                width=16,
            ).pack(side="left")

            ctk.CTkLabel(
                fila, text=carac,
                font=ctk.CTkFont(size=11),
                anchor="w",
            ).pack(side="left", padx=(4, 0))

        ctk.CTkButton(
            self,
            text=plan_data["boton_texto"],
            height=42,
            corner_radius=10,
            fg_color=plan_data["color"],
            hover_color=self._oscurecer(plan_data["color"]),
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.on_click,
        ).pack(fill="x", padx=20, pady=(20, 20))

    @staticmethod
    def _oscurecer(color_hex):
        try:
            h = color_hex.lstrip("#")
            r = int(h[0:2], 16)
            g = int(h[2:4], 16)
            b = int(h[4:6], 16)
            r = max(0, int(r * 0.8))
            g = max(0, int(g * 0.8))
            b = max(0, int(b * 0.8))
            return "#{:02X}{:02X}{:02X}".format(r, g, b)
        except Exception:
            return color_hex


# ====================================================================
# VISTA PRINCIPAL
# ====================================================================

class SuscripcionView(ctk.CTkFrame):
    """Vista de suscripción con tarjetas de planes + estado de licencia."""

    def __init__(self, parent, config):
        super().__init__(parent, fg_color="transparent")
        self.config = config
        self.estado = {}
        self.on_licencia_activada = None

        # Bandera: ¿el último intento de consultar al servidor fue OK?
        # True por defecto para no mostrar avisos raros al arrancar.
        self._conexion_ok = True

        self._crear_layout()
        self._refrescar_estado_local()

        self.after(300, self._consultar_servidor_async)

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
            text="🔑 Mi Suscripción",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        ).pack(side="left", padx=16, pady=10)

        self.lbl_estado_header = ctk.CTkLabel(
            header, text="",
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.lbl_estado_header.pack(side="right", padx=16, pady=10)

        # --- Contenido con scroll ---
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=(4, 10))

        self.frame_estado = ctk.CTkFrame(scroll, corner_radius=12)
        self.frame_estado.pack(fill="x", padx=0, pady=(0, 14))

        ctk.CTkLabel(
            scroll,
            text="Elige tu plan",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
        ).pack(anchor="w", pady=(4, 4))

        ctk.CTkLabel(
            scroll,
            text="Todos los planes incluyen acceso completo a la aplicación.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", pady=(0, 12))

        # ============ PLANES RESPONSIVOS ============
        self.planes_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self.planes_frame.pack(fill="x", pady=(0, 14))

        self.plan_cards = []
        for plan_data in PLANES:
            card = TarjetaPlan(
                self.planes_frame, plan_data,
                on_click=lambda p=plan_data: self._on_plan_click(p),
            )
            self.plan_cards.append(card)

        self._ultimo_layout_planes = None
        self._resize_after_id_planes = None
        self.planes_frame.bind("<Configure>", self._on_planes_resize)

        self._seccion_activar_manual(scroll)
        self._seccion_contacto(scroll)

    # ------------------------------------------------------------------

    def _seccion_activar_manual(self, parent):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.pack(fill="x", padx=0, pady=(4, 12))

        ctk.CTkLabel(
            frame,
            text="🔑 ¿Ya tienes un token?",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1D4ED8", "#93C5FD"),
        ).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(
            frame,
            text="Si ya compraste tu licencia y recibiste un token por correo, actívalo aquí.",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", padx=20, pady=(0, 12))

        botones = ctk.CTkFrame(frame, fg_color="transparent")
        botones.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkButton(
            botones,
            text="🔑  Activar licencia",
            width=170, height=38,
            fg_color="#0066FF",
            hover_color="#0052CC",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._abrir_modal_activar,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            botones,
            text="🔄  Verificar estado",
            width=160, height=38,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=12),
            command=self._consultar_servidor_async,
        ).pack(side="left", padx=(0, 8))

        self.btn_eliminar = ctk.CTkButton(
            botones,
            text="🗑️  Desvincular esta PC",
            width=180, height=38,
            fg_color=("#DC2626", "#7F1D1D"),
            hover_color=("#B91C1C", "#991B1B"),
            font=ctk.CTkFont(size=12),
            command=self._desvincular_pc,
        )

    # ------------------------------------------------------------------

    def _seccion_contacto(self, parent):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.pack(fill="x", padx=0, pady=(0, 10))

        ctk.CTkLabel(
            frame,
            text="💬 ¿Dudas o necesitas soporte?",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("#1D4ED8", "#93C5FD"),
        ).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(
            frame,
            text="Córdoba y Abogados SAS · 302 415 8837 · cordobayabogadossas@gmail.com",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", padx=20, pady=(0, 12))

        ctk.CTkButton(
            frame,
            text="💬  Contactar soporte",
            width=180, height=34,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            font=ctk.CTkFont(size=12),
            command=self._contactar_soporte,
        ).pack(anchor="w", padx=20, pady=(0, 16))

    # ------------------------------------------------------------------
    # Cálculo del estado efectivo (licencia + conexión)
    # ------------------------------------------------------------------

    def _calcular_estado_efectivo(self):
        """
        Devuelve una tupla (tipo, texto, color, icono, mensaje_gris) donde:

          tipo ∈ {
            "sin_licencia",       → no hay token local
            "activa",             → licencia activa verificada
            "trial",              → trial activo verificado
            "offline_ok",         → sin conexión pero dentro del periodo de gracia
            "offline_expirado",   → sin conexión y fuera del periodo de gracia
            "vencida",            → el servidor confirmó vencimiento
            "revocada",           → el servidor confirmó revocación
            "maquina_no_activada",→ el servidor indica que esta PC no está activada
          }

        El mensaje_gris es un texto discreto (o None) que se muestra debajo
        del estado principal sin asustar al usuario.
        """
        estado = self.estado or {}
        tiene_token = bool(estado.get("token"))
        plan = (estado.get("plan") or "").lower()
        invalida = (estado.get("invalida") or "").strip()

        # 1) Sin licencia local
        if not tiene_token:
            return ("sin_licencia", "Sin licencia",
                    ("#DC2626", "#F87171"), "🚫", None)

        # 2) Códigos duros del servidor (autoritativos)
        if invalida == "VENCIDA":
            return ("vencida", "Licencia vencida",
                    "#D97706", "⏰", None)
        if invalida == "REVOCADA":
            return ("revocada", "Licencia revocada",
                    "#DC2626", "🚫", None)
        if invalida == "MAQUINA_NO_ACTIVADA":
            return ("maquina_no_activada", "PC no activada",
                    "#DC2626", "🚫", None)

        # 3) ¿El servidor respondió OK?
        if self._conexion_ok:
            if plan == "trial":
                return ("trial", "Prueba activa",
                        ("#8B5CF6", "#C4B5FD"), "🎁", None)
            return ("activa", "Licencia activa",
                    ("#059669", "#34D399"), "✅", None)

        # 4) Sin conexión: usar periodo de gracia
        ultima = estado.get("ultima_validacion_ok")
        if ultima:
            try:
                dias = (datetime.now() - datetime.fromisoformat(ultima)).days
            except Exception:
                dias = 999
        else:
            dias = 999

        if dias <= DIAS_GRACIA_OFFLINE:
            # Dentro de la gracia → mostrar como activa normal,
            # pero con un texto gris discreto debajo
            if plan == "trial":
                return ("offline_ok", "Prueba activa",
                        ("#8B5CF6", "#C4B5FD"), "🎁",
                        "Sin conexión al servidor. "
                        "Última verificación: hace {} día(s).".format(dias))
            return ("offline_ok", "Licencia activa",
                    ("#059669", "#34D399"), "✅",
                    "Sin conexión al servidor. "
                    "Última verificación: hace {} día(s).".format(dias))

        # Fuera de la gracia → aviso claro pero no alarmante
        return ("offline_expirado", "Requiere conexión",
                "#D97706", "📡",
                "Conéctate a internet para verificar tu licencia. "
                "Última verificación: hace {} día(s).".format(dias))

    # ------------------------------------------------------------------
    # Render del estado de la licencia
    # ------------------------------------------------------------------

    def _renderizar_estado(self):
        for w in self.frame_estado.winfo_children():
            w.destroy()

        tipo, texto, color, icono, mensaje_gris = self._calcular_estado_efectivo()

        # Si no hay licencia → ocultar el bloque completo
        if tipo == "sin_licencia":
            self.frame_estado.pack_forget()
            self.lbl_estado_header.configure(
                text=texto, text_color=color)
            return

        # Mostrar el frame de estado
        self.frame_estado.pack(fill="x", padx=0, pady=(0, 14),
                               before=self.planes_frame)

        # --- Cabecera ---
        header_lic = ctk.CTkFrame(self.frame_estado, fg_color="transparent")
        header_lic.pack(fill="x", padx=20, pady=(16, 8))

        ctk.CTkLabel(
            header_lic,
            text="{}  {}".format(icono, texto),
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=color,
        ).pack(side="left")

        self.lbl_estado_header.configure(text=texto, text_color=color)

        # --- Datos en fila (Plan / Vence / Días) ---
        # Solo si NO es "offline_expirado" (que no tiene datos fiables)
        if tipo != "offline_expirado":
            plan = (self.estado.get("plan") or "").lower()
            vence = self.estado.get("vence", "")
            dias_restantes = int(self.estado.get("dias_restantes") or 0)

            datos = ctk.CTkFrame(self.frame_estado, fg_color="transparent")
            datos.pack(fill="x", padx=20, pady=(0, 10))

            plan_txt = "Prueba gratuita" if plan == "trial" else plan.capitalize()
            maximo = 3 if plan == "trial" else 365
            progreso = min(1.0, max(0.0, dias_restantes / maximo))

            self._mini_info(datos, "Plan", plan_txt or "—", 0)
            self._mini_info(datos, "Vence", vence or "—", 1)
            self._mini_info(datos, "Días restantes", str(dias_restantes), 2)

            barra = ctk.CTkProgressBar(self.frame_estado, height=6)
            barra.pack(fill="x", padx=20, pady=(4, 8))
            barra.set(progreso)

        # --- Mensaje gris discreto (offline / requiere conexión) ---
        if mensaje_gris:
            ctk.CTkLabel(
                self.frame_estado,
                text=mensaje_gris,
                font=ctk.CTkFont(size=10),
                text_color=("gray45", "gray55"),
                justify="left", anchor="w", wraplength=600,
            ).pack(anchor="w", padx=20, pady=(2, 8))

        # --- Botón desvincular (dentro del frame) ---
        self.btn_eliminar.pack(side="left", padx=(0, 8))

    def _mini_info(self, parent, etiqueta, valor, col):
        parent.grid_columnconfigure(col, weight=1, uniform="mini")
        sub = ctk.CTkFrame(parent, fg_color="transparent")
        sub.grid(row=0, column=col, sticky="w")

        ctk.CTkLabel(
            sub, text=etiqueta,
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w")

        ctk.CTkLabel(
            sub, text=valor,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(anchor="w")

    # ------------------------------------------------------------------
    # Refrescar estado
    # ------------------------------------------------------------------

    def _refrescar_estado_local(self):
        self.estado = licencias.obtener_estado_local()
        self._renderizar_estado()

    def _consultar_servidor_async(self):
        # Feedback inmediato (aunque sea silencioso)
        self.lbl_estado_header.configure(
            text="Verificando…", text_color=("gray50", "gray60"))
        threading.Thread(target=self._consultar_servidor, daemon=True).start()

    def _consultar_servidor(self):
        try:
            resp = licencias.validar(silencioso=True)
        except Exception as e:
            log.warning("Error validando licencia: %s", e)
            resp = {"ok": False, "error": str(e)}

        self.after(0, self._on_respuesta_servidor, resp)

    # 👇 FIX: comportamiento silencioso cuando no hay conexión
    def _on_respuesta_servidor(self, resp):
        if resp.get("ok"):
            # El servidor respondió bien → todo en orden
            self._conexion_ok = True
            self.estado = licencias.obtener_estado_local()
            self.estado.pop("invalida", None)
        else:
            codigo = (resp.get("codigo") or "").strip()
            if codigo:
                # El servidor respondió con un código explícito
                # (VENCIDA, REVOCADA, MAQUINA_NO_ACTIVADA) → respetar
                self._conexion_ok = True
                self.estado["invalida"] = codigo
            else:
                # El servidor NO respondió (sin internet, timeout, caída)
                # → no marcar nada, dejar que el periodo de gracia decida
                self._conexion_ok = False
                self.estado.pop("invalida", None)
                log.info("Servidor de licencias no disponible: %s",
                         resp.get("error", "sin conexión"))

        self._renderizar_estado()

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------

    def _on_plan_click(self, plan_data):
        if plan_data["link_pago"] is None:
            self._abrir_modal_trial()
        else:
            self._abrir_enlace_pago(plan_data)

    def _abrir_enlace_pago(self, plan_data):
        link = plan_data.get("link_pago", "")
        if not link or "tu-enlace" in link:
            messagebox.showwarning(
                "Enlace no configurado",
                "El enlace de pago para el plan '{}' aún no ha sido configurado.\n\n"
                "Por favor, contacta a soporte:\n"
                "📞 302 415 8837".format(plan_data["nombre"]))
            return

        try:
            webbrowser.open(link)
            log.info("Abriendo enlace de pago para plan %s", plan_data["nombre"])
        except Exception as e:
            messagebox.showerror(
                "Error",
                "No se pudo abrir el navegador:\n{}".format(e))

    def _abrir_modal_activar(self):
        ModalActivar(self, on_exito=self._on_activacion_exitosa)

    def _abrir_modal_trial(self):
        ModalTrial(self, on_exito=self._on_activacion_exitosa)

    def _on_activacion_exitosa(self):
        self._refrescar_estado_local()
        if callable(self.on_licencia_activada):
            try:
                self.on_licencia_activada()
            except Exception as e:
                log.warning("Callback on_licencia_activada falló: %s", e)

        messagebox.showinfo(
            "¡Listo!",
            "La licencia se activó correctamente.\n\n"
            "Ya puedes usar todas las funciones de Revisor Judicial.")

    def _desvincular_pc(self):
        if not messagebox.askyesno(
            "Desvincular esta PC",
            "¿Eliminar la licencia guardada en este equipo?\n\n"
            "Tendrás que volver a activar el token si quieres usarla aquí.\n"
            "Tu licencia en el servidor NO se elimina."
        ):
            return
        licencias.limpiar_licencia()
        self.estado = {}
        self._conexion_ok = True
        self._renderizar_estado()
        messagebox.showinfo("Listo", "Esta PC fue desvinculada.")

    # ------------------------------------------------------------------
    # Layout responsivo de las tarjetas de planes
    # ------------------------------------------------------------------

    def _on_planes_resize(self, event):
        ancho = event.width
        if self._resize_after_id_planes is not None:
            try:
                self.after_cancel(self._resize_after_id_planes)
            except Exception:
                pass
        self._resize_after_id_planes = self.after(
            100, lambda: self._redimensionar_planes(ancho))

    def _columnas_para_ancho(self, ancho):
        if ancho >= 1100:
            return 5
        elif ancho >= 800:
            return 3
        elif ancho >= 500:
            return 2
        else:
            return 1

    def _redimensionar_planes(self, ancho):
        self._resize_after_id_planes = None

        if ancho <= 0 or not self.plan_cards:
            return

        cols = self._columnas_para_ancho(ancho)

        if self._ultimo_layout_planes == cols:
            return
        self._ultimo_layout_planes = cols

        for i in range(10):
            try:
                self.planes_frame.grid_columnconfigure(i, weight=0, minsize=0)
            except Exception:
                pass

        for i in range(cols):
            self.planes_frame.grid_columnconfigure(
                i, weight=1, uniform="plan")

        for idx, card in enumerate(self.plan_cards):
            fila = idx // cols
            col = idx % cols
            card.grid_forget()
            card.grid(row=fila, column=col, sticky="nsew", padx=8, pady=6)

    def _contactar_soporte(self):
        messagebox.showinfo(
            "Contactar soporte",
            "Córdoba y Abogados SAS\n\n"
            "📞 302 415 8837\n"
            "📧 cordobayabogadossas@gmail.com\n\n"
            "Escríbenos si necesitas:\n"
            "• Activar o renovar tu licencia\n"
            "• Cambiar el titular\n"
            "• Soporte técnico"
        )


# ====================================================================
# MODAL: ACTIVAR LICENCIA
# ====================================================================

class ModalActivar(ctk.CTkToplevel):
    def __init__(self, parent, on_exito=None):
        super().__init__(parent)
        self.on_exito = on_exito
        self.title("Activar licencia")
        self.geometry("460x320")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(
            self, text="🔑  Activar licencia",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(24, 4))

        ctk.CTkLabel(
            self, text="Pega el token que te enviamos por correo.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
        ).pack(pady=(0, 18))

        self.entry = ctk.CTkEntry(
            self, width=340, height=42, justify="center",
            font=ctk.CTkFont(family="Consolas", size=14),
            placeholder_text="RJM-2026-XXXXXXXX")
        self.entry.pack(pady=6)

        self.lbl_msg = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), wraplength=400)
        self.lbl_msg.pack(pady=8)

        botones = ctk.CTkFrame(self, fg_color="transparent")
        botones.pack(pady=10)

        ctk.CTkButton(
            botones, text="Cancelar", width=120, height=36,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            command=self.destroy,
        ).pack(side="left", padx=6)

        self.btn_ok = ctk.CTkButton(
            botones, text="✓  Activar", width=140, height=36,
            fg_color="#0066FF", hover_color="#0052CC",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._activar,
        )
        self.btn_ok.pack(side="left", padx=6)

    def _activar(self):
        token = self.entry.get().strip()
        if not token:
            self.lbl_msg.configure(
                text="⚠️ Pega el token primero.",
                text_color=("#D97706", "#FBBF24"))
            return

        self.btn_ok.configure(state="disabled", text="Activando...")
        self.lbl_msg.configure(
            text="Consultando servidor...", text_color=("gray40", "gray60"))
        self.update_idletasks()

        threading.Thread(
            target=self._hacer_activacion, args=(token,), daemon=True).start()

    def _hacer_activacion(self, token):
        try:
            resp = licencias.activar(token)
        except Exception as e:
            resp = {"ok": False, "error": str(e)}
        self.after(0, self._on_respuesta, resp)

    def _on_respuesta(self, resp):
        self.btn_ok.configure(state="normal", text="✓  Activar")

        if resp.get("ok"):
            self.lbl_msg.configure(
                text="✅ Activada hasta " + resp.get("vence", ""),
                text_color=("#059669", "#34D399"))
            self.after(1200, self._cerrar_con_exito)
        else:
            self.lbl_msg.configure(
                text="❌ " + resp.get("error", "Error desconocido"),
                text_color=("#DC2626", "#F87171"))

    def _cerrar_con_exito(self):
        if callable(self.on_exito):
            self.on_exito()
        self.destroy()


# ====================================================================
# MODAL: SOLICITAR PRUEBA
# ====================================================================

class ModalTrial(ctk.CTkToplevel):
    def __init__(self, parent, on_exito=None):
        super().__init__(parent)
        self.on_exito = on_exito
        self.title("Prueba gratuita de 3 días")
        self.geometry("480x440")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(
            self, text="🎁  Prueba gratuita",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(24, 4))

        ctk.CTkLabel(
            self,
            text="Usa todas las funciones durante 3 días.\n"
                 "Solo se puede pedir una vez por PC y por correo.",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray60"),
            justify="center",
        ).pack(pady=(0, 18))

        ctk.CTkLabel(
            self, text="Nombre completo:",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(anchor="w", padx=60)

        self.entry_nombre = ctk.CTkEntry(
            self, width=340, height=40,
            placeholder_text="Ej: Juan Pérez")
        self.entry_nombre.pack(pady=(4, 12))

        ctk.CTkLabel(
            self, text="Correo electrónico:",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(anchor="w", padx=60)

        self.entry_email = ctk.CTkEntry(
            self, width=340, height=40,
            placeholder_text="tucorreo@gmail.com")
        self.entry_email.pack(pady=4)

        ctk.CTkLabel(
            self,
            text="Acepta Gmail, Outlook, Hotmail, Yahoo, iCloud,\n"
                 "correos universitarios (.edu) o de gobierno.",
            font=ctk.CTkFont(size=10),
            text_color=("gray40", "gray60"),
            justify="center",
        ).pack(pady=(4, 8))

        self.lbl_msg = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), wraplength=420)
        self.lbl_msg.pack(pady=4)

        botones = ctk.CTkFrame(self, fg_color="transparent")
        botones.pack(pady=10)

        ctk.CTkButton(
            botones, text="Cancelar", width=120, height=36,
            fg_color=("gray75", "#3A3A3C"),
            hover_color=("gray65", "#4A4A4C"),
            command=self.destroy,
        ).pack(side="left", padx=6)

        self.btn_ok = ctk.CTkButton(
            botones, text="🎁  Activar prueba", width=170, height=36,
            fg_color=("#8B5CF6", "#5B21B6"),
            hover_color=("#7C3AED", "#4C1D95"),
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._solicitar,
        )
        self.btn_ok.pack(side="left", padx=6)

    def _solicitar(self):
        nombre = self.entry_nombre.get().strip()
        email = self.entry_email.get().strip()

        if len(nombre) < 3:
            self.lbl_msg.configure(
                text="⚠️ Ingresa tu nombre completo.",
                text_color=("#D97706", "#FBBF24"))
            return

        if "@" not in email or "." not in email:
            self.lbl_msg.configure(
                text="⚠️ Ingresa un correo válido.",
                text_color=("#D97706", "#FBBF24"))
            return

        self.btn_ok.configure(state="disabled", text="Solicitando...")
        self.lbl_msg.configure(
            text="Consultando servidor...", text_color=("gray40", "gray60"))
        self.update_idletasks()

        threading.Thread(
            target=self._hacer_solicitud,
            args=(email, nombre), daemon=True).start()

    def _hacer_solicitud(self, email, nombre):
        try:
            resp = licencias.solicitar_prueba(email, nombre)
        except Exception as e:
            resp = {"ok": False, "error": str(e)}
        self.after(0, self._on_respuesta, resp)

    def _on_respuesta(self, resp):
        self.btn_ok.configure(state="normal", text="🎁  Activar prueba")

        if resp.get("ok"):
            self.lbl_msg.configure(
                text="✅ Prueba activada hasta " + resp.get("vence", ""),
                text_color=("#059669", "#34D399"))
            self.after(1200, self._cerrar_con_exito)
        else:
            self.lbl_msg.configure(
                text="❌ " + resp.get("error", "Error desconocido"),
                text_color=("#DC2626", "#F87171"))

    def _cerrar_con_exito(self):
        if callable(self.on_exito):
            self.on_exito()
        self.destroy()