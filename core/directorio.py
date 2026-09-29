# core/directorio.py
from __future__ import annotations
import re
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict

try:
    import pandas as pd
except ImportError:
    pd = None


# ----------------------------------------------------------------------
# Clasificación de especialidad a partir del nombre del despacho.
# El ORDEN importa: primero los patrones más específicos.
# ----------------------------------------------------------------------
ESPECIALIDADES = [
    ("CORTE CONSTITUCIONAL",       r"CORTE\s+CONSTITUCIONAL"),
    ("CORTE SUPREMA",              r"CORTE\s+SUPREMA"),
    ("CONSEJO DE ESTADO",          r"CONSEJO\s+DE\s+ESTADO"),
    ("CONSEJO SUPERIOR JUDICATURA", r"CONSEJO\s+SUPERIOR\s+DE\s+LA\s+JUDICATURA"),
    ("COMISIÓN NACIONAL DISCIPLINA", r"COMISIÓN\s+NACIONAL\s+DE\s+DISCIPLINA"),
    ("COMISIÓN SECCIONAL DISCIPLINA", r"COMISIÓN\s+SECCIONAL\s+DE\s+DISCIPLINA"),
    ("JUSTICIA Y PAZ",             r"JUSTICIA\s+Y\s+PAZ"),
    ("RESTITUCIÓN DE TIERRAS",     r"RESTITUCIÓN\s+DE\s+TIERRAS"),
    ("EXTINCIÓN DE DOMINIO",       r"EXTINCIÓN\s+DE\s+DOMINIO"),
    ("CONTROL DE GARANTÍAS",       r"CONTROL\s+DE\s+GARANT"),
    ("EJECUCIÓN DE PENAS",         r"EJECUCIÓN\s+DE\s+PENAS"),
    ("ADOLESCENTES",               r"ADOLESCENTE"),
    ("PROMISCUO FAMILIA",          r"PROMISCUO\s+DE\s+FAMILIA"),
    ("PROMISCUO",                  r"PROMISCUO"),
    ("PEQUEÑAS CAUSAS",            r"PEQUEÑAS\s+CAUSAS"),
    ("CIVIL FAMILIA",              r"CIVIL\s+FAMILIA"),
    ("CIVIL",                      r"\bCIVIL\b"),
    ("FAMILIA",                    r"\bFAMILIA\b"),
    ("PENAL",                      r"\bPENAL\b"),
    ("LABORAL",                    r"\bLABORAL\b"),
    ("ADMINISTRATIVO",             r"ADMINISTRATIV"),
    ("DISCIPLINARIO",              r"DISCIPLINA"),
    ("TRIBUNAL SUPERIOR",          r"TRIBUNAL\s+SUPERIOR"),
]


def clasificar_especialidad(nombre: str) -> str:
    """Devuelve una etiqueta de especialidad a partir del nombre del despacho."""
    nombre_u = (nombre or "").upper()
    for etiqueta, patron in ESPECIALIDADES:
        if re.search(patron, nombre_u):
            return etiqueta
    return "OTROS"


class Directorio:
    """Directorio judicial: carga, indexa y consulta despachos."""

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "directorio.db"
        self._xls_path = self._localizar_archivo()
        self._asegurar_db()

    # -------------------- carga --------------------
    def _localizar_archivo(self) -> Optional[Path]:
        candidatos = sorted(self.data_dir.glob("Despachos_*.xls*"))
        return candidatos[-1] if candidatos else None

    def _asegurar_db(self):
        """Crea o actualiza la BD. Si falta ESPECIALIDAD, reimporta."""
        if self.db_path.exists():
            try:
                with sqlite3.connect(self.db_path) as con:
                    cur = con.execute("PRAGMA table_info(despachos)")
                    cols = [r[1] for r in cur.fetchall()]
                if "ESPECIALIDAD" in cols:
                    return
                # Falta la columna → borrar y reimportar
                print("🔁 Directorio: reimportando para añadir ESPECIALIDAD…")
                self.db_path.unlink()
            except Exception:
                pass

        if not self._xls_path:
            print(
                "⚠️  Directorio: no se encontró 'data/Despachos_*.xls*'.\n"
                "   La vista 'Correos y Teléfonos' aparecerá vacía."
            )
            return

        try:
            self.importar(self._xls_path)
            print(f"✅ Directorio importado desde {self._xls_path.name}")
        except ImportError as e:
            print(
                f"⚠️  Directorio: falta una dependencia ({e}).\n"
                "   Instala con: pip install xlrd  (para .xls)  "
                "o guarda el archivo como .xlsx."
            )
        except Exception as e:
            print(f"⚠️  Directorio: error al importar {self._xls_path.name}: {e}")

    def importar(self, archivo: Path):
        if pd is None:
            raise ImportError("Instala pandas, openpyxl y xlrd")

        raw = pd.read_excel(archivo, sheet_name="Consulta Externa", header=None)
        header_row = None
        for i, fila in raw.iterrows():
            valores = [str(v).strip().upper() for v in fila.tolist()]
            if "CODIGO DESPACHO" in valores:
                header_row = i
                break
        if header_row is None:
            raise ValueError("No se encontró la fila de encabezado.")

        df = pd.read_excel(
            archivo, sheet_name="Consulta Externa", header=header_row
        )
        df.columns = [str(c).strip() for c in df.columns]
        df = df.dropna(subset=["CODIGO DESPACHO"])

        for c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()

        # ---------- NUEVA columna derivada ----------
        df["ESPECIALIDAD"] = df["NOMBRE DESPACHO"].apply(clasificar_especialidad)

        con = sqlite3.connect(self.db_path)
        df.to_sql("despachos", con, if_exists="replace", index=False)
        cur = con.cursor()
        for col in ("DEPARTAMENTO", "MUNICIPIO", "ÁREA", "ESPECIALIDAD"):
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_{col} ON despachos("{col}")'
            )
        con.commit()
        con.close()

    # -------------------- consultas --------------------
    def _con(self):
        return sqlite3.connect(self.db_path)

    def departamentos(self) -> List[str]:
        with self._con() as con:
            cur = con.execute(
                'SELECT DISTINCT DEPARTAMENTO FROM despachos '
                "WHERE DEPARTAMENTO <> '' ORDER BY DEPARTAMENTO"
            )
            return [r[0] for r in cur.fetchall()]

    def municipios(self, departamento: Optional[str] = None) -> List[str]:
        sql = "SELECT DISTINCT MUNICIPIO FROM despachos WHERE MUNICIPIO <> ''"
        params: list = []
        if departamento:
            sql += " AND DEPARTAMENTO = ?"
            params.append(departamento)
        sql += " ORDER BY MUNICIPIO"
        with self._con() as con:
            return [r[0] for r in con.execute(sql, params).fetchall()]

    def especialidades(self) -> List[str]:
        """Especialidades derivadas del nombre del despacho."""
        with self._con() as con:
            cur = con.execute(
                'SELECT DISTINCT ESPECIALIDAD FROM despachos '
                "WHERE ESPECIALIDAD <> '' ORDER BY ESPECIALIDAD"
            )
            return [r[0] for r in cur.fetchall()]

    def buscar(
        self,
        texto: str = "",
        departamento: Optional[str] = None,
        municipio: Optional[str] = None,
        especialidad: Optional[str] = None,
        limite: int = 5000,
    ) -> List[Dict]:
        sql = "SELECT * FROM despachos WHERE 1=1"
        params: list = []

        if texto:
            sql += (
                ' AND ( "NOMBRE DESPACHO" LIKE ?'
                ' OR "JUEZ/MAGISTRADO DESPACHO" LIKE ?'
                ' OR "DIRECCIÓN DESPACHO" LIKE ?'
                ' OR "TELÉFONO" LIKE ?'
                ' OR "CODIGO DESPACHO" LIKE ? )'
            )
            like = f"%{texto}%"
            params += [like] * 5

        if departamento:
            sql += " AND DEPARTAMENTO = ?"
            params.append(departamento)
        if municipio:
            sql += " AND MUNICIPIO = ?"
            params.append(municipio)
        if especialidad:
            sql += " AND ESPECIALIDAD = ?"
            params.append(especialidad)

        sql += ' ORDER BY DEPARTAMENTO, MUNICIPIO, "NOMBRE DESPACHO" LIMIT ?'
        params.append(limite)

        with self._con() as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute(sql, params).fetchall()]