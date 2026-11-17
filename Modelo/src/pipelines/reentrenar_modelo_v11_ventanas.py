"""
v11 — v9 + VENTANA MÓVIL RICA DEL ESTABLECIMIENTO
=================================================

Diagnóstico que motiva v11
--------------------------
v9 logra MAE 7.236 / R2 0.8066. Antes de cambiar el algoritmo se midió el techo
y se descartaron varias vías:

  | Experimentos descartados (misma matriz v9) | MAE | R2 | Veredicto |
  |-------------------------------------------|-----|-----|-----------|
  | RF profundo (hoja=4, mtry=0.5)            | 7.394 | 0.7946 | peor |
  | ExtraTrees (hoja=2)                       | 7.298 | 0.8001 | peor |
  | HistGradientBoosting L1                   | 7.295 | 0.7961 | peor |
  | HistGradientBoosting L2                   | 7.412 | 0.7911 | peor |
  | RF sobre log1p                            | 7.199 | 0.7975 | +MAE pero −R2 y sesgo −3.1% |
  | Calibración isotónica (OOF)               | 7.198 | 0.8052 | −0.5% MAE, −R2 |

  Conclusión de esa fase: **el techo está en las features, no en el algoritmo.**

Lo que el diagnóstico SÍ mostró como explotable:
  - El residuo tiene **autocorrelación lag-1 de +0.245** por establecimiento:
    hay estructura temporal que el modelo no captura.
  - El error es de regresión a la media: sobreestima los días flojos (+134% en
    el quintil más bajo) y subestima los picos (−9.2% en el quintil más alto).
  - El modelo solo conoce `Total_Lag_4` (un día) y `Estab_Media_28d_lag4` (media
    de 4 semanas). Le falta la FORMA de la serie reciente.

Qué agrega v11
--------------
Features de ventana del establecimiento, todas con información ≤ T−4:

  1. `L4..L10`      los 7 lags diarios consecutivos (T−4 .. T−10). `Total_Lag_4`
                    solo daba un punto; con la serie el árbol distingue "viene
                    subiendo" de "viene bajando".
  2. `W7_mean/std/min/max`  estadísticos de la ventana [T−10..T−4].
  3. `W28_std/max`  dispersión y techo de las últimas 4 semanas.
  4. `L4_over_L10`  razón de cambio (demanda actual vs 6 días antes), clip [0,5].
  5. `W7_vs_W28`    media de 7 días / media de 28 días: régimen actual vs
                    tendencia larga del propio establecimiento.

La intuición clínica: la demanda de urgencias tiene memoria corta (brotes de
virus respiratorios duran días) y el nivel de la última semana informa mejor
que el nivel de hace 4 días aislado.

Anti-leakage: todo se calcula sobre la serie calendario del establecimiento con
shift(≥4). Hay asserts de correlación feature-target.

Artefactos (models/):
  - model_rf_directo_v11.joblib
  - model_metadata_v11.json
v9 queda intacto.

Uso:
    python3 src/pipelines/reentrenar_modelo_v11_ventanas.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
RUTA_DATOS = BASE_DIR / "data" / "processed" / "df_modelo.parquet"
RUTA_MODELO_OUT = BASE_DIR / "models" / "model_rf_directo_v11.joblib"
RUTA_SALIDA = BASE_DIR / "models" / "model_metadata_v11.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reentrenar_modelo_v8_tendencia as v8  # noqa: E402
import reentrenar_modelo_v9_calendario as v9  # noqa: E402
import reentrenar_modelo_v7_features_fix as v7  # noqa: E402
import reentrenar_modelo_v5_trailing as v5  # noqa: E402
import reentrenar_modelo_v6_e1_trailing as e1  # noqa: E402

TARGET = v7.TARGET
LAG_MIN = v7.LAG_DEMANDA  # 4

FEATURES_VENTANA = (
    [f"L{k}" for k in range(4, 11)]
    + ["W7_mean", "W7_std", "W7_min", "W7_max", "W28_std", "W28_max",
       "L4_over_L10", "W7_vs_W28"]
)


def construir_ventanas_estab(panel: pd.DataFrame) -> pd.DataFrame:
    """Serie calendario del establecimiento: lags 4..10 y estadísticos de ventana.

    ANTI-LEAKAGE: todas las ventanas terminan en T−4 (`shift(LAG_MIN)` antes de
    cualquier rolling). El día T nunca entra en sus propias features.
    """
    partes = []
    for est, g in panel.groupby("IdEstablecimiento"):
        g = g.sort_values("Fecha")
        cal = pd.date_range(g["Fecha"].min(), g["Fecha"].max(), freq="D")
        s = pd.Series(
            g[TARGET].to_numpy(), index=pd.DatetimeIndex(g["Fecha"].to_numpy())
        ).reindex(cal).ffill()

        d = pd.DataFrame({"IdEstablecimiento": est, "Fecha": cal})
        for k in range(4, 11):
            d[f"L{k}"] = s.shift(k).to_numpy()

        base = s.shift(LAG_MIN)  # todo lo que sigue mira <= T-4
        w7 = base.rolling(7, min_periods=3)
        w28 = base.rolling(28, min_periods=7)
        d["W7_mean"] = w7.mean().to_numpy()
        d["W7_std"] = w7.std().to_numpy()
        d["W7_min"] = w7.min().to_numpy()
        d["W7_max"] = w7.max().to_numpy()
        d["W28_std"] = w28.std().to_numpy()
        d["W28_max"] = w28.max().to_numpy()
        d["L4_over_L10"] = (
            s.shift(4) / s.shift(10).replace(0, np.nan)
        ).clip(0, 5).to_numpy()
        d["W7_vs_W28"] = (
            w7.mean() / w28.mean().replace(0, np.nan)
        ).clip(0, 5).to_numpy()
        partes.append(d)
    return pd.concat(partes, ignore_index=True)


def main() -> None:
    t0 = time.time()
    print("=" * 74)
    print("v11 — v9 + VENTANA MÓVIL RICA DEL ESTABLECIMIENTO")
    print("=" * 74)

    df = pd.read_parquet(RUTA_DATOS)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year
    train_raw = df[df["Año"] == v5.TRAIN_YEAR].copy()
    test_raw = df[df["Año"] == v5.TEST_YEAR].copy()
    panel = v7.cargar_panel(df)
    print(f"  Panel estab+fecha: {len(panel):,}")

    print("\n--- Etapa 1 (v5): Pred_Region ---")
    rt, rs, dc, _ = v5.preparar_features_region(df, ventana=v5.VENTANA_PRINCIPAL)
    fr = v5.construir_lista_features(dc, "trailing")
    r1 = v5.entrenar_etapa_1(rt, rs, fr, con_cv=False)
    rt["Pred_Region"] = r1["model"].predict(rt[fr])
    rs["Pred_Region"] = r1["y_pred"]
    print(f"  Región (test 2025): MAE={r1['met_region']['MAE']:.3f} "
          f"R2={r1['met_region']['R2']:.4f}")

    print("\n--- Total_Lag_4 + Share_Trailing ---")
    lag_cal = v7.calcular_total_lag_calendario(panel)
    sh24, _ = e1.calcular_share_2024_con_fallback(test_raw, train_raw)
    shg = v7.calcular_share_trailing_grilla(panel, sh24)

    print("\n--- Tendencia regional (v8) ---")
    mtr = (train_raw.groupby("Region")[TARGET].sum()
           / train_raw.groupby("Region")["Fecha"].nunique())
    reg_f, est_f = v8.calcular_features_tendencia(panel, mtr)

    print("\n--- NUEVO v11: ventanas del establecimiento ---")
    win = construir_ventanas_estab(panel)
    print(f"  Filas de ventana: {len(win):,} | features: {len(FEATURES_VENTANA)}")

    print("\n--- Ensamblado ---")
    base = panel.merge(lag_cal, on=["IdEstablecimiento", "Fecha"], how="left")
    base = base.merge(
        shg.rename(columns={"share_trailing": "Share_Trailing"}),
        on=["IdEstablecimiento", "Fecha"], how="left")
    base = base.merge(est_f, on=["IdEstablecimiento", "Fecha"], how="left")
    base = base.merge(reg_f, on=["Region", "Fecha"], how="left")
    base = base.merge(win, on=["IdEstablecimiento", "Fecha"], how="left")
    for r in (rt, rs):
        base = base.merge(
            r[["Region", "Fecha", "Pred_Region"] + v7.COLUMNAS_CLIMA_DIRECTO],
            on=["Region", "Fecha"], how="left", suffixes=("", "_rt"))
    for c in ["Pred_Region"] + v7.COLUMNAS_CLIMA_DIRECTO:
        if f"{c}_rt" in base.columns:
            base[c] = base[c].fillna(base[f"{c}_rt"])
            base = base.drop(columns=[f"{c}_rt"])

    base["Pred_E1"] = base["Share_Trailing"] * base["Pred_Region"]
    doy = base["Fecha"].dt.dayofyear
    base["Doy"] = doy
    base["Doy_Sin"] = np.sin(2 * np.pi * doy / 365.25)
    base["Doy_Cos"] = np.cos(2 * np.pi * doy / 365.25)
    base["Año"] = base["Fecha"].dt.year

    dtr = base[base["Año"] == v5.TRAIN_YEAR].copy()
    dte = base[base["Año"] == v5.TEST_YEAR].copy()

    print("\n--- Patrón semanal (v9) ---")
    a, b, info_dow = v9.construir_dow_esperado(dtr, dte)
    dtr = v9.agregar_calendario(dtr, a)
    dte = v9.agregar_calendario(dte, b)

    dtr, dte, dt = v7.codificar_onehot(dtr, dte, "TipoEstablecimiento", "Tipo")
    dtr, dte, dr = v7.codificar_onehot(dtr, dte, "Region", "Region")

    nuevas_v8 = [
        "Region_Total_Lag_4", "Region_Media_28d_lag4",
        "Region_Trend_Ratio", "Region_Level_vs_Train", "Estab_Media_28d_lag4",
    ]
    core = ["Total_Lag_4", "Share_Trailing", "Pred_Region", "Pred_E1"]
    fc = (core + nuevas_v8 + v9.FEATURES_CALENDARIO + FEATURES_VENTANA
          + dt + dr + v7.FEATURES_ESTACIONALIDAD + v7.COLUMNAS_CLIMA_DIRECTO)
    print(f"  Features finales ({len(fc)}; v9 tenía "
          f"{len(fc) - len(FEATURES_VENTANA)})")

    for c in fc:
        if dtr[c].isna().any():
            med = dtr[c].median()
            dtr[c] = dtr[c].fillna(med)
            dte[c] = dte[c].fillna(med)

    print("\n" + "-" * 70)
    print("VERIFICACIÓN ANTI-LEAKAGE")
    print("-" * 70)
    verif = v7.verificar_anti_leakage(dtr, dte, fc)
    corrs = {}
    for f in FEATURES_VENTANA:
        c = float(dtr[f].corr(dtr[TARGET]))
        corrs[f] = round(c, 4)
    maxc = max(abs(v) for v in corrs.values())
    print(f"  Correlación máxima feature-ventana vs target: {maxc:.3f} "
          f"(fuga si >0.995)")
    assert maxc < 0.995
    print(f"  Todas las ventanas terminan en T−{LAG_MIN} (shift antes de rolling).")

    print("\n" + "-" * 70)
    print("ENTRENAMIENTO — RandomForest v11")
    print("-" * 70)
    X_tr, y_tr = dtr[fc], dtr[TARGET]
    X_te, y_te = dte[fc], dte[TARGET]
    print(f"  Train: {len(X_tr):,} | Test: {len(X_te):,} | {len(fc)} features")

    t_fit = time.time()
    model = v5.RandomForestRegressor(**v5.HIPERPARAMETROS)
    model.fit(X_tr, y_tr)
    t_ent = time.time() - t_fit
    print(f"  Entrenado en {t_ent:.1f} s")

    y_pred = model.predict(X_te)
    met = v7.metricas(y_te.to_numpy(float), y_pred)
    print(f"\n  MAE={met['MAE']:.4f}  RMSE={met['RMSE']:.4f}  "
          f"R2={met['R2']:.4f}  sesgo={met['sesgo_pct']:+.2f}%  (n={met['n']:,})")
    fuga = bool(met["R2"] and met["R2"] > 0.9)
    print(f"  Sanity R2≤0.9: {'⚠ SOSPECHOSO' if fuga else '✅ OK'}")

    ev = dte[["IdEstablecimiento", "Region", "Fecha", TARGET]].copy()
    ev["pred"] = y_pred
    met_region = {
        r: v7.metricas(g[TARGET].to_numpy(float), g["pred"].to_numpy(float))
        for r, g in ev.groupby("Region")
    }

    print("\n=== SESGO POR QUINTIL DE DEMANDA REAL: v9 → v11 ===")
    v9y = json.loads((BASE_DIR / "models" / "model_metadata_v9.json").read_text())
    ref9 = v9y["metricas_establecimiento"]
    ref9r = v9y["metricas_por_region"]
    qb = pd.qcut(ev[TARGET], 5, labels=["p0-20", "p20-40", "p40-60", "p60-80", "p80-100"])
    print(f"  {'bin':>9} {'n':>7} {'sesgo':>9} {'MAE':>8}")
    por_bin = {}
    for lab, g in ev.groupby(qb, observed=True):
        s = 100 * (g["pred"].sum() - g[TARGET].sum()) / g[TARGET].sum()
        m = float(np.mean(np.abs(g["pred"] - g[TARGET])))
        por_bin[str(lab)] = {"sesgo_pct": round(float(s), 2), "MAE": round(m, 4),
                             "n": len(g)}
        print(f"  {lab:>9} {len(g):>7,} {s:>+8.1f}% {m:>8.2f}")

    print("\n=== SESGO POR REGIÓN: v9 → v11 ===")
    print(f"  {'Región':<22} {'v9':>8} {'v11':>8} {'Δ pp':>7} {'v9 R2':>7} {'v11 R2':>7}")
    filas = []
    for r in sorted(met_region):
        s9 = ref9r[r]["sesgo_pct"]; s11 = met_region[r]["sesgo_pct"]
        filas.append((r, s9, s11))
        print(f"  {r:<22} {s9:>+7.1f}% {s11:>+7.1f}% {s11 - s9:>+7.1f} "
              f"{ref9r[r]['R2']:>7.3f} {met_region[r]['R2']:>7.3f}")
    mej = [abs(x) - abs(y) for _, x, y in filas]
    r2up = sum(1 for r in met_region if met_region[r]["R2"] > ref9r[r]["R2"])
    print(f"\n  |sesgo| medio: {np.mean(mej):+.2f} pp | mejora en "
          f"{sum(1 for m in mej if m > 0)}/{len(mej)} | R2 mejora en {r2up}/{len(met_region)}")

    print("\n=== TABLA COMPARATIVA ===")
    comp = pd.DataFrame([
        {"versión": "v9", **{k: ref9[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct"]}},
        {"versión": "v11 (+ ventanas)", **{k: met[k] for k in
                                           ["MAE", "RMSE", "R2", "sesgo_pct"]}},
    ])
    print(comp.round(4).to_string(index=False))

    imp = pd.DataFrame({"feature": fc, "importance": model.feature_importances_}) \
        .sort_values("importance", ascending=False)
    print("\nTop 15 features:")
    for _, row in imp.head(15).iterrows():
        marca = " ←NUEVA" if row["feature"] in FEATURES_VENTANA else ""
        print(f"  {row['feature']:<26} {row['importance']:.4f}{marca}")

    joblib.dump(model, RUTA_MODELO_OUT)
    t_total = time.time() - t0
    metadata = {
        "release": "modelo-v11-ventanas",
        "experimento": "v11 — v9 + ventana móvil rica del establecimiento",
        "descripcion": (
            "v9 solo conocía Total_Lag_4 (un día) y la media de 28 días del "
            "establecimiento. El residuo de v9 tiene autocorrelación lag-1 de "
            "+0.245, señal de estructura temporal no capturada. v11 agrega los "
            "7 lags consecutivos T−4..T−10, estadísticos de la ventana de 7 y "
            "28 días (media, desvío, min, max) y dos razones de cambio. "
            "Antes de llegar acá se descartaron cambios de algoritmo "
            "(RF profundo, ExtraTrees, HistGradientBoosting L1/L2, log1p) y "
            "calibración isotónica: ninguno superó a v9 de forma consistente."
        ),
        "justificacion_diagnostica": {
            "autocorrelacion_residuo_lag1": 0.245,
            "experimentos_descartados": {
                "RF profundo (hoja=4, mtry=0.5)": {"MAE": 7.3936, "R2": 0.7946},
                "ExtraTrees (hoja=2)": {"MAE": 7.2980, "R2": 0.8001},
                "HistGradientBoosting L1": {"MAE": 7.2949, "R2": 0.7961},
                "HistGradientBoosting L2": {"MAE": 7.4117, "R2": 0.7911},
                "RF log1p": {"MAE": 7.1988, "R2": 0.7975, "sesgo": -3.13},
                "Calibración isotónica": {"MAE": 7.1980, "R2": 0.8052},
            },
            "conclusion_fase_algortimo": (
                "El techo está en las features, no en el algoritmo: ningún "
                "cambio de modelo superó a v9 sin sacrificar R2."
            ),
            "regresion_a_la_media_v9": {
                "quintil_mas_bajo": "+134.1% de sobreestimación",
                "quintil_mas_alto": "-9.2% de subestimación",
            },
        },
        "features_nuevas": {
            "L4..L10": "7 lags diarios consecutivos (T−4 .. T−10)",
            "W7_mean/std/min/max": "estadísticos de [T−10..T−4]",
            "W28_std/max": "dispersión y techo de las últimas 4 semanas",
            "L4_over_L10": "razón de cambio reciente, clip [0,5]",
            "W7_vs_W28": "media 7d / media 28d (régimen vs tendencia)",
        },
        "anti_leakage": {
            "todas_las_ventanas_terminan_en": f"T−{LAG_MIN}",
            "shift_aplicado_antes_de_rolling": True,
            "correlaciones_train": corrs,
            "correlacion_maxima": round(maxc, 4),
            "verificacion": verif,
        },
        "features_totales": fc,
        "n_features": len(fc),
        "n_features_v9": len(fc) - len(FEATURES_VENTANA),
        "configuracion": {
            "target": "Total (nivel, sin transformar)",
            "filas": "una por (establecimiento, fecha)",
            "split": "train = 2024, test = 2025",
            "horizonte_horas": 96,
            "semilla": v5.RANDOM_STATE,
            "hiperparametros": {k: v for k, v in v5.HIPERPARAMETROS.items()
                                if k != "n_jobs"},
        },
        "metricas_establecimiento": met,
        "metricas_por_region": met_region,
        "metricas_por_quintil_demanda": por_bin,
        "sesgo_por_region_vs_v9": {
            r: {"v9": ref9r[r]["sesgo_pct"], "v11": met_region[r]["sesgo_pct"],
                "delta_pp": round(met_region[r]["sesgo_pct"] - ref9r[r]["sesgo_pct"], 2)}
            for r in met_region
        },
        "comparativa": {
            "v9": {k: ref9[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct", "n"]},
            "v11": met,
        },
        "importancia_features": imp.head(20).to_dict("records"),
        "sanity_check": {"r2_mayor_a_0_9_sospechoso": fuga, "r2_observado": met["R2"]},
        "tiempo_entrenamiento_segundos": round(t_ent, 1),
        "tiempo_total_segundos": round(t_total, 1),
        "limitaciones": [
            "Split de 2 años: el aporte de las ventanas se valida en 2025 "
            "solamente.",
            "La regresión a la media persiste en los extremos: es una "
            "propiedad del RandomForest con MSE, no un bug.",
            "Los lags asumen reporte diario continuo; establecimientos con "
            "huecos usan ffill (documentado desde v6).",
        ],
    }
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 74)
    print("✅ v11 COMPLETADO")
    print(f"  Modelo:   {RUTA_MODELO_OUT.name}")
    print(f"  Metadata: {RUTA_SALIDA.name}")
    print(f"  Tiempo total: {t_total:.1f} s")
    print("=" * 74)


if __name__ == "__main__":
    main()
