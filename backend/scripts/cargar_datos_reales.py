"""
Carga datos REALES del DEIS en las tablas de la plataforma (reemplaza seed_demo).

Lee `Modelo/data/raw/AtencionesUrgencia<año>.csv` (datos observados del
Ministerio de Salud) y llena:

  - `demanda_diaria`   una fila por (establecimiento, fecha) con la suma de
                       causas respiratorias del día.
  - `ingresos_diarios` una fila por (establecimiento, fecha, grupo etario)
                       con el desglose real por edad.

No inventa ninguna cifra. Si un día no está en el archivo, no se carga.

Los códigos DEIS del CSV se normalizan (el archivo los trae con espacios).

Uso, desde la carpeta backend/:
    python scripts/cargar_datos_reales.py                # últimos 60 días
    python scripts/cargar_datos_reales.py --dias 45
    python scripts/cargar_datos_reales.py --borrar       # limpia antes de cargar

Requiere que los establecimientos existan (scripts/seed_dev.py).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
import app.models.user  # noqa: E402,F401  (registra todas las tablas)
from app.models.establishment import Establishment  # noqa: E402
from app.models.intake import DailyIntake  # noqa: E402
from app.models.ml_data import DailyDemand  # noqa: E402

# Ruta al CSV del DEIS (fuera del repo, en el workspace de datos).
CSV_CANDIDATOS = [
    Path.home() / "Downloads",
    Path(__file__).resolve().parents[2] / "Modelo" / "data" / "raw",
]

# Columnas de edad del CSV → etiquetas aceptadas por el CHECK de la tabla.
GRUPOS = {
    "Menores_1": "Menores de 1",
    "De_1_a_4": "1-4",
    "De_5_a_14": "5-14",
    "De_15_a_64": "15-64",
    "De_65_y_mas": "65+",
}


def encontrar_csv() -> Path:
    """Busca el archivo de atenciones más reciente."""
    import re
    for base in CSV_CANDIDATOS:
        if not base.exists():
            continue
        # Solo archivos con nombre exacto "AtencionesUrgencia<4 dígitos>.csv"
        # (excluye los *Filtrado*, *Mezclado*, " 2.csv", etc.)
        validos = []
        for f in base.glob("AtencionesUrgencia*.csv"):
            m = re.fullmatch(r"AtencionesUrgencia(\d{4})\.csv", f.name)
            if m:
                validos.append((int(m.group(1)), f))
        if validos:
            validos.sort(key=lambda x: x[0])
            return validos[-1][1]
    raise SystemExit(
        "No se encontró AtencionesUrgencia*.csv. Copiá el archivo del DEIS a "
        "~/Downloads o indicá la ruta con --csv."
    )


def leer_atenciones(ruta: Path, desde: date, codigos: set[str]) -> pd.DataFrame:
    """Lee el CSV por chunks y devuelve solo los códigos y fechas pedidos."""
    partes = []
    for chunk in pd.read_csv(
        ruta, sep=";", encoding="latin-1",
        usecols=["IdEstablecimiento", "fecha", "Total", *GRUPOS],
        dtype=str, chunksize=800_000,
    ):
        chunk["codigo"] = chunk["IdEstablecimiento"].astype(str).str.strip()
        chunk = chunk[chunk["codigo"].isin(codigos)]
        if chunk.empty:
            continue
        chunk["f"] = pd.to_datetime(chunk["fecha"], format="%d/%m/%Y", errors="coerce")
        chunk = chunk[chunk["f"].notna() & (chunk["f"].dt.date >= desde)]
        if chunk.empty:
            continue
        for col in ["Total", *GRUPOS]:
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce").fillna(0).astype(int)
        partes.append(chunk)
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dias", type=int, default=60, help="Días hacia atrás a cargar")
    ap.add_argument("--csv", type=Path, default=None, help="Ruta explícita al CSV")
    ap.add_argument("--borrar", action="store_true", help="Vaciar las tablas antes")
    args = ap.parse_args()

    desde = date.today() - timedelta(days=args.dias)
    ruta = args.csv or encontrar_csv()
    print(f"Archivo: {ruta.name}")
    print(f"Ventana: desde {desde}")

    db: Session = SessionLocal()
    try:
        hospitales = db.query(Establishment).filter(
            Establishment.id_establecimiento.isnot(None)
        ).all()
        if not hospitales:
            raise SystemExit("No hay establecimientos con código DEIS. Ejecutá seed_dev.py primero.")

        por_codigo = {h.id_establecimiento: h for h in hospitales}
        print(f"Establecimientos en la base: {len(por_codigo)}")

        if args.borrar:
            n1 = db.query(DailyDemand).delete()
            n2 = db.query(DailyIntake).delete()
            db.commit()
            print(f"Borrados: {n1} demanda, {n2} ingresos")

        df = leer_atenciones(ruta, desde, set(por_codigo))
        if df.empty:
            raise SystemExit("El CSV no tiene filas para esos establecimientos y fechas.")
        print(f"Filas leídas del CSV: {len(df):,}")

        # ---- demanda_diaria: suma de causas respiratorias por día ----------
        diario = (
            df.groupby(["codigo", "f"], as_index=False)["Total"].sum()
            .sort_values(["codigo", "f"])
        )
        creados_dem = 0
        for _, r in diario.iterrows():
            dia = r["f"].date()
            fila = db.get(DailyDemand, (r["codigo"], dia))
            if fila is None:
                db.add(DailyDemand(
                    id_establecimiento=r["codigo"], fecha=dia, total=int(r["Total"]),
                ))
                creados_dem += 1
            else:
                fila.total = int(r["Total"])
        db.commit()
        print(f"demanda_diaria: {creados_dem} nuevas, {len(diario) - creados_dem} actualizadas")

        # ---- ingresos_diarios: desglose real por grupo etario --------------
        creados_ing = 0
        for _, r in df.iterrows():
            estab = por_codigo[r["codigo"]]
            dia = r["f"].date()
            for col, grupo in GRUPOS.items():
                casos = int(r[col])
                if casos == 0:
                    continue
                existe = db.query(DailyIntake).filter_by(
                    establecimiento_id=estab.id, fecha=dia, grupo_etario=grupo,
                ).first()
                if existe is None:
                    db.add(DailyIntake(
                        fecha=dia, establecimiento_id=estab.id,
                        casos_respiratorios=casos, grupo_etario=grupo,
                    ))
                    creados_ing += 1
        db.commit()
        print(f"ingresos_diarios: {creados_ing} nuevos")

        # ---- resumen ------------------------------------------------------
        total_dem = db.query(DailyDemand).count()
        total_ing = db.query(DailyIntake).count()
        fechas = sorted({r["f"].date() for _, r in diario.iterrows()})
        print()
        print("=" * 60)
        print(f"  demanda_diaria   : {total_dem} filas")
        print(f"  ingresos_diarios : {total_ing} filas")
        print(f"  rango de fechas  : {fechas[0]} → {fechas[-1]}")
        print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    main()
