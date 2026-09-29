# data/database.py
"""
Persistencia del historial de escaneos en SQLite.
"""

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Optional

from core.constantes import BASE_DIR

log = logging.getLogger(__name__)

ARCHIVO_DB = os.path.join(BASE_DIR, "historial.db")


ESQUEMA = """
CREATE TABLE IF NOT EXISTS escaneos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_inicio TEXT NOT NULL,
    fecha_fin TEXT,
    total_radicados INTEGER DEFAULT 0,
    modo_actuaciones TEXT,
    dias_umbral INTEGER,
    cantidad_actuaciones INTEGER,
    ruta_informe TEXT,
    jurisdiccion TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    escaneo_id INTEGER NOT NULL,
    radicado TEXT NOT NULL,
    estado TEXT,
    fecha_ultima_actuacion TEXT,
    observacion TEXT,
    despacho TEXT,
    demandante TEXT,
    demandado TEXT,
    apoderado TEXT,
    resumen TEXT,
    captura TEXT,
    captura_actuaciones TEXT,
    FOREIGN KEY (escaneo_id) REFERENCES escaneos(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_resultados_radicado
    ON resultados(radicado);
CREATE INDEX IF NOT EXISTS idx_escaneos_fecha
    ON escaneos(fecha_inicio);
"""


class Database:
    """Envoltura simple sobre SQLite. Sin ORM, sin sorpresas."""

    def __init__(self, ruta: str = None):
        self.ruta = ruta or ARCHIVO_DB
        self._inicializar()
        self._migrar()

    # ================================================================
    # CONEXIÓN
    # ================================================================

    @contextmanager
    def _conexion(self):
        conn = sqlite3.connect(self.ruta)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _inicializar(self) -> None:
        try:
            with self._conexion() as conn:
                conn.executescript(ESQUEMA)
            log.info("Base de datos lista en %s", self.ruta)
        except sqlite3.Error as e:
            log.error("Error inicializando BD: %s", e)

    def _migrar(self) -> None:
        """Añade columnas nuevas si no existen (migración segura)."""
        try:
            with self._conexion() as conn:
                # Verificar si existe la columna 'jurisdiccion'
                cur = conn.execute("PRAGMA table_info(escaneos)")
                columnas = {row[1] for row in cur.fetchall()}
                if "jurisdiccion" not in columnas:
                    conn.execute(
                        "ALTER TABLE escaneos ADD COLUMN jurisdiccion TEXT DEFAULT ''")
                    log.info("Migración: columna 'jurisdiccion' añadida.")

                # Poblar 'jurisdiccion' en escaneos viejos que esté vacía
                cur = conn.execute("""
                    SELECT id, ruta_informe FROM escaneos
                    WHERE jurisdiccion IS NULL OR jurisdiccion = ''
                """)
                actualizados = 0
                for row in cur.fetchall():
                    ruta = (row["ruta_informe"] or "").lower()
                    juris = ""
                    if "samai" in ruta:
                        juris = "SAMAI"
                    elif "actuacion" in ruta or "rama" in ruta:
                        juris = "RAMA"
                    if juris:
                        conn.execute(
                            "UPDATE escaneos SET jurisdiccion = ? WHERE id = ?",
                            (juris, row["id"]))
                        actualizados += 1
                if actualizados:
                    log.info("Migración: %s escaneos con jurisdicción asignada.",
                             actualizados)
        except sqlite3.Error as e:
            log.warning("No se pudo migrar el esquema: %s", e)

    # ================================================================
    # ESCRITURA
    # ================================================================

    def iniciar_escaneo(
        self,
        modo_actuaciones: str,
        dias_umbral: int,
        cantidad_actuaciones: int,
        total_radicados: int,
        jurisdiccion: str = "",
    ) -> int:
        with self._conexion() as conn:
            cur = conn.execute(
                """INSERT INTO escaneos
                   (fecha_inicio, total_radicados, modo_actuaciones,
                    dias_umbral, cantidad_actuaciones, jurisdiccion)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    total_radicados,
                    modo_actuaciones,
                    dias_umbral,
                    cantidad_actuaciones,
                    jurisdiccion,
                ),
            )
            return cur.lastrowid

    def finalizar_escaneo(self, escaneo_id: int, ruta_informe: str = "") -> None:
        with self._conexion() as conn:
            conn.execute(
                """UPDATE escaneos
                   SET fecha_fin = ?, ruta_informe = ?
                   WHERE id = ?""",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 ruta_informe, escaneo_id),
            )

    def guardar_resultados(self, escaneo_id: int, resultados: list) -> None:
        if not resultados:
            return

        filas = []
        for r in resultados:
            if hasattr(r, "to_dict"):
                r = r.to_dict()
            filas.append((
                escaneo_id,
                r.get("Radicado", ""),
                r.get("Estado", ""),
                r.get("Fecha_Ultima_Actuacion", ""),
                r.get("Observacion", ""),
                r.get("Despacho", ""),
                r.get("Demandante", ""),
                r.get("Demandado", ""),
                r.get("Apoderado", ""),
                r.get("Resumen de Actuacion", ""),
                r.get("Captura", ""),
                r.get("Captura_Actuaciones", ""),
            ))

        with self._conexion() as conn:
            conn.executemany(
                """INSERT INTO resultados
                   (escaneo_id, radicado, estado, fecha_ultima_actuacion,
                    observacion, despacho, demandante, demandado, apoderado,
                    resumen, captura, captura_actuaciones)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                filas,
            )

    def eliminar_escaneo(self, escaneo_id: int) -> None:
        with self._conexion() as conn:
            conn.execute("DELETE FROM escaneos WHERE id = ?", (escaneo_id,))

    def eliminar_escaneos_antiguos(self, dias: int = 30) -> int:
        """Elimina escaneos más antiguos que `dias`. Devuelve cuántos eliminó."""
        limite = (datetime.now() - timedelta(days=dias)).strftime(
            "%Y-%m-%d %H:%M:%S")
        with self._conexion() as conn:
            cur = conn.execute(
                "DELETE FROM escaneos WHERE fecha_inicio < ?", (limite,))
            return cur.rowcount

    # ================================================================
    # LECTURA
    # ================================================================

    def listar_escaneos(self, limite: int = 100) -> list:
        with self._conexion() as conn:
            cur = conn.execute(
                """SELECT * FROM escaneos
                   ORDER BY fecha_inicio DESC
                   LIMIT ?""",
                (limite,),
            )
            return [dict(row) for row in cur.fetchall()]

    def listar_escaneos_con_stats(self, limite: int = 500) -> list:
        """
        Devuelve cada escaneo con conteos de clasificación.
        Columnas adicionales: cnt_total, cnt_revisar, cnt_fuera, cnt_errores
        """
        with self._conexion() as conn:
            cur = conn.execute("""
                SELECT
                    e.*,
                    COUNT(r.id) AS cnt_total,
                    SUM(CASE WHEN r.estado = 'Revisar' THEN 1 ELSE 0 END)
                        AS cnt_revisar,
                    SUM(CASE WHEN r.estado LIKE '%fuera de b%' THEN 1 ELSE 0 END)
                        AS cnt_fuera,
                    SUM(CASE WHEN r.estado LIKE '%⚠%'
                             OR r.estado LIKE '%Error%'
                             THEN 1 ELSE 0 END)
                        AS cnt_errores
                FROM escaneos e
                LEFT JOIN resultados r ON r.escaneo_id = e.id
                GROUP BY e.id
                ORDER BY e.fecha_inicio DESC
                LIMIT ?
            """, (limite,))
            return [dict(row) for row in cur.fetchall()]

    def obtener_escaneo(self, escaneo_id: int) -> Optional[dict]:
        with self._conexion() as conn:
            cur = conn.execute(
                "SELECT * FROM escaneos WHERE id = ?", (escaneo_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def obtener_resultados(self, escaneo_id: int) -> list:
        with self._conexion() as conn:
            cur = conn.execute(
                "SELECT * FROM resultados WHERE escaneo_id = ? ORDER BY id",
                (escaneo_id,),
            )
            return [dict(row) for row in cur.fetchall()]

    def buscar_radicado(self, radicado: str) -> list:
        with self._conexion() as conn:
            cur = conn.execute(
                """SELECT r.*, e.fecha_inicio AS escaneo_fecha
                   FROM resultados r
                   JOIN escaneos e ON e.id = r.escaneo_id
                   WHERE r.radicado = ?
                   ORDER BY e.fecha_inicio DESC""",
                (radicado,),
            )
            return [dict(row) for row in cur.fetchall()]

    def buscar_radicados_por_patron(self, patron: str, limite: int = 300) -> list:
        """Búsqueda parcial de radicados (contiene)."""
        with self._conexion() as conn:
            cur = conn.execute(
                """SELECT r.*, e.fecha_inicio AS escaneo_fecha,
                          e.jurisdiccion AS jurisdiccion
                   FROM resultados r
                   JOIN escaneos e ON e.id = r.escaneo_id
                   WHERE r.radicado LIKE ?
                   ORDER BY e.fecha_inicio DESC
                   LIMIT ?""",
                (f"%{patron}%", limite),
            )
            return [dict(row) for row in cur.fetchall()]