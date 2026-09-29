# gui/views/directorio_view.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

from core.directorio import Directorio


class DirectorioView(ctk.CTkFrame):
    """Vista de correos, direcciones y teléfonos de despachos judiciales."""

    COLUMNAS = (
        "departamento", "municipio", "despacho", "juez",
        "especialidad", "direccion", "telefono", "codigo",
    )
    ENCABEZADOS = {
        "departamento": "Departamento",
        "municipio":    "Municipio",
        "despacho":     "Despacho",
        "juez":         "Juez / Magistrado",
        "especialidad": "Especialidad",
        "direccion":    "Dirección",
        "telefono":     "Teléfono",
        "codigo":       "Código",
    }
    ANCHOS = {
        "departamento": 130,
        "municipio":    120,
        "despacho":     330,
        "juez":         200,
        "especialidad": 150,
        "direccion":    260,
        "telefono":     130,
        "codigo":       110,
    }
    ANCHO_MINIMO = 60
    LIMITE_RESULTADOS = 5000   # debe coincidir con el default de Directorio.buscar

    def __init__(self, master, directorio: Directorio):
        super().__init__(master, fg_color="transparent")
        self.directorio = directorio
        self._resultados: list[dict] = []

        self._proporciones = {c: self.ANCHOS[c] for c in self.COLUMNAS}
        self._suma_anchos = sum(self._proporciones.values())

        # 👇 Debounce para resize de la tabla
        self._resize_after_id = None

        self._construir()

        if self.directorio.db_path.exists():
            self._cargar_filtros()
            self._buscar()
        else:
            self.lbl_contador.configure(
                text="⚠️ Directorio no disponible: falta el archivo "
                     "data/Despachos_*.xls* o la dependencia 'xlrd'."
            )

    # ------------------------------------------------------------------
    # Construcción
    # ------------------------------------------------------------------
    def _construir(self):
        filtros = ctk.CTkFrame(self)
        filtros.pack(fill="x", padx=10, pady=(10, 5))

        ctk.CTkLabel(filtros, text="Buscar:").grid(
            row=0, column=0, padx=(8, 2), pady=5, sticky="w"
        )
        self.entry_buscar = ctk.CTkEntry(
            filtros,
            placeholder_text="Despacho, juez, dirección, teléfono o código…",
        )
        self.entry_buscar.grid(
            row=0, column=1, columnspan=3, padx=5, pady=5, sticky="ew"
        )

        ctk.CTkLabel(filtros, text="Departamento:").grid(
            row=1, column=0, padx=(8, 2), pady=5, sticky="w"
        )
        self.combo_depto = ctk.CTkComboBox(
            filtros, values=["(Todos)"], command=self._on_depto
        )
        self.combo_depto.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(filtros, text="Municipio:").grid(
            row=1, column=2, padx=(8, 2), pady=5, sticky="w"
        )
        self.combo_muni = ctk.CTkComboBox(filtros, values=["(Todos)"])
        self.combo_muni.grid(row=1, column=3, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(filtros, text="Especialidad:").grid(
            row=2, column=0, padx=(8, 2), pady=5, sticky="w"
        )
        self.combo_especialidad = ctk.CTkComboBox(
            filtros, values=["(Todas)"]
        )
        self.combo_especialidad.grid(
            row=2, column=1, padx=5, pady=5, sticky="ew"
        )

        ctk.CTkButton(filtros, text="Buscar", command=self._buscar).grid(
            row=2, column=2, padx=5, pady=5, sticky="ew"
        )
        ctk.CTkButton(
            filtros, text="Limpiar", command=self._limpiar, fg_color="gray40"
        ).grid(row=2, column=3, padx=5, pady=5, sticky="ew")

        filtros.grid_columnconfigure(1, weight=1)
        filtros.grid_columnconfigure(3, weight=1)

        self.lbl_contador = ctk.CTkLabel(self, text="")
        self.lbl_contador.pack(anchor="w", padx=15, pady=(0, 5))

        contenedor = ctk.CTkFrame(self)
        contenedor.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        estilo = ttk.Style()
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        estilo.configure(
            "Treeview",
            background="#2b2b2b",
            foreground="#e6e6e6",
            fieldbackground="#2b2b2b",
            rowheight=24,
        )
        estilo.configure(
            "Treeview.Heading",
            background="#1f1f1f",
            foreground="#ffffff",
        )

        self.tabla = ttk.Treeview(
            contenedor, columns=self.COLUMNAS, show="headings"
        )
        for c in self.COLUMNAS:
            self.tabla.heading(c, text=self.ENCABEZADOS[c])
            self.tabla.column(
                c, width=self.ANCHOS[c], minwidth=self.ANCHO_MINIMO,
                anchor="w", stretch=True,
            )

        vsb = ttk.Scrollbar(contenedor, orient="vertical",
                            command=self.tabla.yview)
        hsb = ttk.Scrollbar(contenedor, orient="horizontal",
                            command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tabla.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        contenedor.grid_rowconfigure(0, weight=1)
        contenedor.grid_columnconfigure(0, weight=1)

        # -------- Responsividad con debounce --------
        self.tabla.bind("<Configure>", self._on_tabla_resize)

        # Interacciones
        self.entry_buscar.bind("<Return>", lambda e: self._buscar())
        self.combo_muni.bind("<<ComboboxSelected>>", lambda e: self._buscar())
        self.combo_especialidad.bind(
            "<<ComboboxSelected>>", lambda e: self._buscar()
        )
        self.tabla.bind("<Double-1>", self._copiar_fila)
        self.tabla.bind("<Control-c>", self._copiar_fila)

    # ------------------------------------------------------------------
    # Responsividad con debounce
    # ------------------------------------------------------------------
    def _on_tabla_resize(self, event):
        """Programa el re-cálculo de anchos con debounce (evita jank)."""
        if self._resize_after_id is not None:
            try:
                self.after_cancel(self._resize_after_id)
            except Exception:
                pass
        ancho = event.width
        self._resize_after_id = self.after(
            50, lambda: self._aplicar_anchos(ancho))

    def _aplicar_anchos(self, ancho):
        self._resize_after_id = None
        if ancho <= 100:
            return
        ancho_util = ancho - 20
        for c, prop in self._proporciones.items():
            nuevo = max(
                self.ANCHO_MINIMO,
                int(ancho_util * prop / self._suma_anchos),
            )
            self.tabla.column(c, width=nuevo)

    # ------------------------------------------------------------------
    # Filtros
    # ------------------------------------------------------------------
    def _cargar_filtros(self):
        self.combo_depto.configure(
            values=["(Todos)"] + self.directorio.departamentos()
        )
        self.combo_especialidad.configure(
            values=["(Todas)"] + self.directorio.especialidades()
        )

    def _on_depto(self, _=None):
        depto = self.combo_depto.get()
        if depto and depto != "(Todos)":
            self.combo_muni.configure(
                values=["(Todos)"] + self.directorio.municipios(depto)
            )
        else:
            self.combo_muni.configure(values=["(Todos)"])
        self.combo_muni.set("(Todos)")
        self._buscar()

    def _limpiar(self):
        self.entry_buscar.delete(0, "end")
        self.combo_depto.set("(Todos)")
        self.combo_especialidad.set("(Todas)")
        # Reconstruye la lista de municipios vacía y busca
        self._on_depto()

    # ------------------------------------------------------------------
    # Búsqueda
    # ------------------------------------------------------------------
    def _buscar(self, _=None):
        texto = self.entry_buscar.get().strip()
        depto = self.combo_depto.get()
        muni = self.combo_muni.get()
        esp = self.combo_especialidad.get()

        depto = None if depto in ("", "(Todos)") else depto
        muni = None if muni in ("", "(Todos)") else muni
        esp = None if esp in ("", "(Todas)") else esp

        self._resultados = self.directorio.buscar(
            texto=texto, departamento=depto,
            municipio=muni, especialidad=esp,
        )

        self.tabla.delete(*self.tabla.get_children())
        for r in self._resultados:
            self.tabla.insert(
                "", "end",
                values=(
                    r.get("DEPARTAMENTO", ""),
                    r.get("MUNICIPIO", ""),
                    r.get("NOMBRE DESPACHO", ""),
                    r.get("JUEZ/MAGISTRADO DESPACHO", ""),
                    r.get("ESPECIALIDAD", ""),
                    r.get("DIRECCIÓN DESPACHO", ""),
                    r.get("TELÉFONO", ""),
                    r.get("CODIGO DESPACHO", ""),
                ),
            )

        # 👇 Avisar si se alcanzó el límite
        n = len(self._resultados)
        if n >= self.LIMITE_RESULTADOS:
            self.lbl_contador.configure(
                text="⚠️ Mostrando {} resultados (límite). "
                     "Refina la búsqueda para ver más.".format(n)
            )
        else:
            self.lbl_contador.configure(text=f"{n} resultados")

    # ------------------------------------------------------------------
    # Portapapeles
    # ------------------------------------------------------------------
    def _copiar_fila(self, event=None):
        sel = self.tabla.selection()
        if not sel:
            return
        v = self.tabla.item(sel[0], "values")
        texto = (
            f"Despacho:      {v[2]}\n"
            f"Juez:          {v[3]}\n"
            f"Especialidad:  {v[4]}\n"
            f"Dirección:     {v[5]}\n"
            f"Teléfono:      {v[6]}\n"
            f"Municipio:     {v[1]} ({v[0]})\n"
            f"Código:        {v[7]}\n"
        )
        self.clipboard_clear()
        self.clipboard_append(texto)
        self.lbl_contador.configure(text="✔ Datos copiados al portapapeles")
        self.after(
            1500,
            lambda: self.lbl_contador.configure(
                text=f"{len(self._resultados)} resultados"
            ),
        )