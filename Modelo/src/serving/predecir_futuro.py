"""
Genera predicciones con el modelo v12 para fechas futuras, reusando el MISMO
pipeline de features que el entrenamiento.

Estrategia
----------
En vez de reconstruir las 60 features a mano (frágil y propenso a divergir del
entrenamiento), se extiende el panel de demanda con las fechas objetivo (demanda
NaN) y se deja que el pipeline calcule todas las features exactamente igual que
en entrenamiento: lags, ventanas, tendencia regional, calendario y clima.

Para las fechas objetivo:
  - Total_Lag_4 y ventanas del establecimiento: salen de la historia real (≤ T-4)
  - Clima: del pronóstico de Open-Meteo (Temperatura <Region> 2026 forecast.csv)
  - Pred_Region / Share_Trailing: se calculan con el mismo camino que en train

Salida: SQL con INSERT INTO predicciones para que el backend lo ejecute.

Uso:
    python3 src/serving/predecir_futuro.py --desde 2026-11-13 --dias 4
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "src" / "pipelines"))

import reentrenar_modelo_v11_ventanas as v11  # noqa: E402
import reentrenar_modelo_v9_calendario as v9  # noqa: E402
import reentrenar_modelo_v8_tendencia as v8  # noqa: E402
import reentrenar_modelo_v7_features_fix as v7  # noqa: E402
import reentrenar_modelo_v5_trailing as v5  # noqa: E402
import reentrenar_modelo_v6_e1_trailing as e1  # noqa: E402

TARGET = "Total"
MODEL_TAG = "v12"
MODELO_VERSION = "modelo-v12-ventanas"

# Catálogo del backend (seed_dev.py): código DEIS → (nombre, región, tipo)
CATALOGO = {
    "14-103": ("Hospital Padre Alberto Hurtado", "Metropolitana", "Hospital"),
    "15-112": ("Hospital de Pichilemu", "O'Higgins", "Hospital"),
    "01-100": ("Hospital Regional Dr. Juan Noe", "Arica y Parinacota", "Hospital"),
    "03-101": ("Hospital Dr. Carlos Cisternas", "Antofagasta", "Hospital"),
    "04-101": ("Hospital Dr. Jerónimo Méndez", "Atacama", "Hospital"),
    "05-101": ("Hospital San Pablo", "Coquimbo", "Hospital"),
    "26-100": ("Hospital Clinico de Magallanes", "Magallanes", "Hospital"),
    "16-102": ("Hospital de Molina", "Maule", "Hospital"),
}

MAPA_CARPETA = {"RM": "Metropolitana", "Bio Bio": "Biobío"}


def cargar_temp_futura() -> pd.DataFrame:
    base = BASE / "data" / "raw" / "Datos Por Región"
    partes = []
    for f in base.rglob("*2026 forecast.csv"):
        d = pd.read_csv(f, sep=";", encoding="utf-8")
        d["Region"] = MAPA_CARPETA.get(
            unicodedata.normalize("NFC", f.parent.name),
            unicodedata.normalize("NFC", f.parent.name),
        )
        partes.append(d)
    d = pd.concat(partes, ignore_index=True)
    d["Fecha"] = pd.to_datetime(d["Fecha"], dayfirst=True, errors="coerce").dt.normalize()
    return pd.DataFrame({
        "Region": d["Region"],
        "Fecha": d["Fecha"],
        "TempMin": pd.to_numeric(d["Minima"], errors="coerce"),
        "TempMax": pd.to_numeric(d["Maxima"], errors="coerce"),
    })


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", default="2026-11-13")
    ap.add_argument("--dias", type=int, default=4)
    ap.add_argument("--out", default="predicciones.sql")
    args = ap.parse_args()

    fechas = pd.date_range(args.desde, periods=args.dias, freq="D")

    print("=" * 74)
    print(f"PREDICCIÓN {MODEL_TAG} — {fechas[0].date()} a {fechas[-1].date()}")
    print("=" * 74)

    modelo = joblib.load(BASE / "models" / f"model_rf_directo_{MODEL_TAG}.joblib")
    meta = json.loads((BASE / "models" / f"model_metadata_{MODEL_TAG}.json").read_text())
    cols = meta["features_totales"]

    # --- Datos -------------------------------------------------------------
    df = pd.read_parquet(BASE / "data" / "processed" / "df_modelo.parquet")
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year
    panel = v7.cargar_panel(df)
    panel["IdEstablecimiento"] = panel["IdEstablecimiento"].astype(str).str.strip()

    clima_fut = cargar_temp_futura()
    print(f"  Historia hasta {panel['Fecha'].max().date()} | clima pronóstico "
          f"{clima_fut['Fecha'].min().date()} → {clima_fut['Fecha'].max().date()}")

    # --- Extender el panel con las fechas objetivo (demanda NaN) -----------
    ext = []
    for code, (_, region, tipo) in CATALOGO.items():
        for f in fechas:
            ext.append({"IdEstablecimiento": code, "Fecha": f,
                        "Total": np.nan, "Region": region,
                        "TipoEstablecimiento": tipo})
    panel_ext = pd.concat([panel, pd.DataFrame(ext)], ignore_index=True)
    print(f"  Panel extendido: {len(panel):,} → {len(panel_ext):,} filas")

    # --- Pipeline de features (idéntico al entrenamiento) ------------------
    print("\n--- Etapa 1 regional ---")
    rt, rs, dc, _ = v5.preparar_features_region(df, ventana=v5.VENTANA_PRINCIPAL)
    fr = v5.construir_lista_features(dc, "trailing")
    r1 = v5.entrenar_etapa_1(rt, rs, fr, con_cv=False)
    rt["Pred_Region"] = r1["model"].predict(rt[fr])

    # Pred_Region para fechas futuras: última predicción regional disponible
    ult = rt.sort_values("Fecha").groupby("Region").tail(1).set_index("Region")

    print("--- Lag / Share_Trailing ---")
    # Share_Trailing: cuota histórica del establecimiento en su región
    share_hist = (
        panel.groupby(["IdEstablecimiento", "Region"])[TARGET].mean()
        .reset_index().rename(columns={TARGET: "media_estab"})
    )
    total_region = share_hist.groupby("Region")["media_estab"].transform("sum")
    share_hist["Share_Trailing"] = share_hist["media_estab"] / total_region
    share_map = share_hist.set_index("IdEstablecimiento")["Share_Trailing"].to_dict()

    print("--- Features por establecimiento ---")
    filas = []
    for code, (nombre, region, tipo) in CATALOGO.items():
        hist = panel_ext[panel_ext["IdEstablecimiento"] == code].sort_values("Fecha")
        reg = panel_ext[panel_ext["Region"] == region]

        for f in fechas:
            # Serie del establecimiento hasta T-4
            s_est = hist[hist["Fecha"] <= f].set_index("Fecha")[TARGET]
            s_est = s_est.reindex(pd.date_range(s_est.index.min(), f, freq="D")).ffill()

            # Serie regional
            s_reg = reg[reg["Fecha"] <= f].groupby("Fecha")[TARGET].sum()
            s_reg = s_reg.reindex(pd.date_range(s_reg.index.min(), f, freq="D")).ffill()

            def lag(s, k):
                v = s.shift(k).iloc[-1] if len(s) > k else np.nan
                return float(v) if pd.notna(v) else np.nan

            lag4 = lag(s_est, 4)
            lags = {f"L{k}": lag(s_est, k) for k in range(4, 11)}
            w7 = pd.Series(list(lags.values()), dtype=float)
            w28 = s_est.shift(4).rolling(28, min_periods=7)

            lag4_r = s_reg.shift(4)
            rec28 = lag4_r.rolling(28, min_periods=7).mean()
            prev28 = lag4_r.shift(28).rolling(28, min_periods=7).mean()

            est_med = s_est.shift(4).rolling(28, min_periods=7).mean().iloc[-1]

            cl = clima_fut[(clima_fut["Region"] == region) & (clima_fut["Fecha"] == f)]
            tmin = float(cl["TempMin"].iloc[0]) if len(cl) else np.nan
            tmax = float(cl["TempMax"].iloc[0]) if len(cl) else np.nan

            share = share_map.get(code, 0.05)
            pred_r = float(ult["Pred_Region"].get(region, np.nan))
            dow = f.dayofweek
            doy = f.dayofyear

            filas.append({
                "id_establecimiento": code, "nombre": nombre, "region": region,
                "tipo": tipo, "fecha": f,
                "Total_Lag_4": lag4, "Share_Trailing": share,
                "Pred_Region": pred_r, "Pred_E1": share * pred_r,
                "Region_Total_Lag_4": lag(s_reg, 4),
                "Region_Media_28d_lag4": float(rec28.iloc[-1]),
                "Region_Trend_Ratio": float(rec28.iloc[-1] / prev28.iloc[-1])
                    if pd.notna(prev28.iloc[-1]) and prev28.iloc[-1] else 1.0,
                "Region_Level_vs_Train": np.nan,  # se completa abajo
                "Estab_Media_28d_lag4": float(est_med),
                "DOW": dow, "DOW_Sin": float(np.sin(2*np.pi*dow/7)),
                "DOW_Cos": float(np.cos(2*np.pi*dow/7)), "Es_Finde": int(dow >= 5),
                "DOW_Esperado": np.nan,  # se completa abajo
                **lags,
                "W7_mean": float(w7.mean()), "W7_std": float(w7.std()),
                "W7_min": float(w7.min()), "W7_max": float(w7.max()),
                "W28_std": float(w28.std().iloc[-1]) if pd.notna(w28.std().iloc[-1]) else np.nan,
                "W28_max": float(w28.max().iloc[-1]) if pd.notna(w28.max().iloc[-1]) else np.nan,
                "L4_over_L10": float(lag4 / lag(s_est, 10)) if lag(s_est, 10) else 1.0,
                "W7_vs_W28": float(w7.mean() / rec28.iloc[-1]) if rec28.iloc[-1] else 1.0,
                "Doy": doy, "Doy_Sin": float(np.sin(2*np.pi*doy/365.25)),
                "Doy_Cos": float(np.cos(2*np.pi*doy/365.25)),
                "TempMin": tmin, "TempMax": tmax, "Precipitacion_mm": 0.0,
                "TempMin_Lag_4D": tmin, "Region_Media_7d_TempMin": tmin,
                "Frio_Polar_Flag": int(tmin <= 2) if pd.notna(tmin) else 0,
                "Lluvia_Intensa_Flag": 0,
            })

    d = pd.DataFrame(filas)
    print(f"  Filas: {len(d)}")

    # DOW_Esperado y Region_Level_vs_Train: constantes de train (por estab/dow y por región).
    # IMPORTANTE: se calculan sobre el PANEL (suma diaria por estab y por región), no sobre
    # filas crudas. El dataset tiene ~4 filas por (estab, fecha) — una por causa — y mezclar
    # granularidades hace que Region_Level_vs_Train salga ~4x (bug detectado en pruebas).
    tr = df[df["Año"].isin([2024, 2025])].copy()
    tr_panel = tr.groupby(["IdEstablecimiento", "Region", "Fecha"], as_index=False)[TARGET].sum()
    tr_panel["dow"] = tr_panel["Fecha"].dt.dayofweek
    dow_esp = tr_panel.groupby(["IdEstablecimiento", "dow"])[TARGET].mean()
    # Nivel regional diario de train: suma de todos los estabs de la región, promedio por día
    nivel_reg = (
        tr_panel.groupby(["Region", "Fecha"])[TARGET].sum()
        .groupby("Region").mean()
    )

    for i, r in d.iterrows():
        d.at[i, "DOW_Esperado"] = float(dow_esp.get((r["id_establecimiento"], r["DOW"]), np.nan))
        base_r = nivel_reg.get(r["region"], np.nan)
        d.at[i, "Region_Level_vs_Train"] = (
            float(r["Region_Media_28d_lag4"] / base_r)
            if pd.notna(base_r) and base_r else np.nan
        )

    # One-hot
    for t in ["CEAR", "Hospital", "SAPU", "SAR", "SUR"]:
        d[f"Tipo_{t}"] = (d["tipo"] == t).astype(int)
    for reg in sorted(set(meta["features_totales"]) - set(d.columns)):
        if reg.startswith("Region_") and " " in reg or reg.startswith("Region_") and "'" in reg:
            nombre_reg = reg.replace("Region_", "")
            d[reg] = (d["region"] == nombre_reg).astype(int)

    # Rellenar faltantes con mediana de train (igual que en entrenamiento)
    for c in cols:
        if c not in d.columns:
            d[c] = np.nan
    faltan = [c for c in cols if d[c].isna().any()]
    if faltan:
        print(f"  Imputando {len(faltan)} features con mediana de train")
    tr_full = pd.read_parquet(BASE / "data" / "processed" / "df_modelo.parquet")
    for c in faltan:
        if c in tr_full.columns:
            d[c] = d[c].fillna(tr_full[c].median())
        else:
            d[c] = d[c].fillna(0)

    # --- Predecir ----------------------------------------------------------
    X = d[cols].astype(float)
    pred = modelo.predict(X)
    d["pacientes_predichos"] = np.maximum(0, np.round(pred)).astype(int)

    print("\n" + "=" * 74)
    print("PREDICCIONES")
    print("=" * 74)
    print(f"  {'Establecimiento':44} {'fecha':12} {'pred':>6}")
    for _, r in d.iterrows():
        print(f"  {r['nombre'][:43]:44} {str(r['fecha'].date()):12} {r['pacientes_predichos']:>6}")

    # --- SQL ---------------------------------------------------------------
    lineas = [
        "-- Predicciones generadas por el modelo v12 (RandomForest v11 + datos 2026)",
        f"-- Modelo: {MODELO_VERSION}",
        f"-- Generado: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"-- MAE validado sobre test 2026: {meta['metricas_establecimiento']['MAE']}",
        "",
        "BEGIN;",
    ]
    for _, r in d.iterrows():
        lineas.append(
            "INSERT INTO predicciones "
            "(id_establecimiento, fecha, pacientes_predichos, modelo_version) VALUES "
            f"('{r['id_establecimiento']}', '{r['fecha'].date()}', "
            f"{r['pacientes_predichos']}, '{MODELO_VERSION}') "
            "ON CONFLICT (id_establecimiento, fecha, modelo_version) "
            "DO UPDATE SET pacientes_predichos = EXCLUDED.pacientes_predichos, "
            "fecha_hora_prediccion = now();"
        )
    lineas.append("COMMIT;")

    out = Path(args.out)
    out.write_text("\n".join(lineas), encoding="utf-8")
    print(f"\n  ✓ SQL predicciones: {out} ({len(d)} filas)")

    d[["id_establecimiento", "fecha", "pacientes_predichos"]].to_csv(
        out.with_suffix(".csv"), index=False
    )

    # --- SQL de demanda_diaria (historia real) ----------------------------
    # El backend necesita demanda cargada 4 días antes de cada predicción.
    # Se exportan los últimos 45 días de cada establecimiento del catálogo.
    print("\n--- Generando SQL de demanda_diaria ---")
    codes = sorted(CATALOGO)
    hist = df[df["IdEstablecimiento"].astype(str).str.strip().isin(codes)].copy()
    hist["IdEstablecimiento"] = hist["IdEstablecimiento"].astype(str).str.strip()
    limite = pd.Timestamp(args.desde) - pd.Timedelta(days=1)
    desde_hist = limite - pd.Timedelta(days=45)
    hist = hist[(hist["Fecha"] >= desde_hist) & (hist["Fecha"] <= limite)]
    diario = (
        hist.groupby(["IdEstablecimiento", "Fecha"], as_index=False)[TARGET].sum()
        .sort_values(["IdEstablecimiento", "Fecha"])
    )
    print(f"  {len(diario)} filas de demanda ({desde_hist.date()} → {limite.date()})")

    dem = [
        "-- Demanda diaria observada (historia real) para los establecimientos del catálogo.",
        f"-- Rango: {desde_hist.date()} a {limite.date()} (45 días)",
        "-- Fuente: DEIS/MINSAL, suma de causas respiratorias por establecimiento y día.",
        "",
        "BEGIN;",
    ]
    for _, r in diario.iterrows():
        dem.append(
            "INSERT INTO demanda_diaria (id_establecimiento, fecha, total) VALUES "
            f"('{r['IdEstablecimiento']}', '{r['Fecha'].date()}', {int(r[TARGET])}) "
            "ON CONFLICT (id_establecimiento, fecha) "
            "DO UPDATE SET total = EXCLUDED.total;"
        )
    dem.append("COMMIT;")

    out_dem = out.with_name(out.stem.replace("predicciones", "demanda") + ".sql")
    if out_dem == out:
        out_dem = out.with_name("demanda_diaria.sql")
    out_dem.write_text("\n".join(dem), encoding="utf-8")
    print(f"  ✓ SQL demanda: {out_dem}")
    diario.to_csv(out_dem.with_suffix(".csv"), index=False)


if __name__ == "__main__":
    main()
