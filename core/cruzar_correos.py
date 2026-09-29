# core/cruzar_correos.py
import json
import pandas as pd
from pathlib import Path


def cruzar(excel_path: Path, correos_path: Path, salida: Path):
    # 1. Leer Excel (saltando encabezados decorativos)
    raw = pd.read_excel(excel_path, sheet_name="Consulta Externa", header=None)
    header_row = None
    for i, fila in raw.iterrows():
        valores = [str(v).strip().upper() for v in fila.tolist()]
        if "CODIGO DESPACHO" in valores:
            header_row = i
            break

    df = pd.read_excel(
        excel_path, sheet_name="Consulta Externa", header=header_row
    )
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(subset=["CODIGO DESPACHO"])
    df["CODIGO DESPACHO"] = df["CODIGO DESPACHO"].astype(str).str.strip()

    # 2. Leer JSON de correos
    correos = json.loads(correos_path.read_text(encoding="utf-8"))
    df_correos = pd.DataFrame(correos)
    df_correos = df_correos.rename(columns={"codigo": "CODIGO DESPACHO"})

    # 3. Merge (left join para no perder despachos sin correo)
    df_final = df.merge(
        df_correos[["CODIGO DESPACHO", "correo"]],
        on="CODIGO DESPACHO",
        how="left",
    )
    df_final["correo"] = df_final["correo"].fillna("")

    df_final.to_excel(salida, index=False)
    print(f"✅ Guardado en {salida}  ({len(df_final)} registros)")
    return df_final