"""
v8 — v7 + FEATURES DE TENDENCIA REGIONAL (anti-inercia)
========================================================

Diagnóstico que motiva v8
-------------------------
v7 (16 regiones) logra MAE 8.550 / R2 0.7378, pero el sesgo por región es muy
heterogéneo:

    Atacama    +28.4%   (volumen real 2024→2025: −17.3%)
    O'Higgins  +26.6%   (                            −23.8%)
    Ñuble      +24.9%   (                             −9.0%)
    Coquimbo   +22.2%   (                             −8.9%)
    Los Lagos  −10.1%   (                             +3.4%)

Correlación entre sesgo y cambio real de volumen: **−0.66**. El modelo aprende
los NIVELES de 2024 y los proyecta a 2025: cuando la demanda real cae, el
modelo queda alto; cuando sube (Los Lagos, Biobío, Aysén), queda bajo. El signo
del sesgo coincide con la dirección del cambio real en 14 de 16 regiones.

Verificaciones que DESCARTAN otras explicaciones:
  - No es rotación de establecimientos: Atacama y O'Higgins tienen 0 estabs
    nuevos; el 100% de su caída ocurre en establecimientos comunes.
  - No es zero-inflation: correlación sesgo vs % de días-cero = 0.011.
  - No es sobreajuste: R2 no correlaciona con el sesgo.

Causa: NINGUNA feature del modelo refleja el nivel de demanda REGIONAL
reciente. `Total_Lag_4` es por establecimiento (ruidoso) y `Pred_Region` viene
de la Etapa 1, que también está anclada al train 2024. El RF no tiene cómo
saber que la región entró en un régimen de demanda más bajo.

Qué agrega v8 (todas anti-leakage: información ≤ T-4)
-----------------------------------------------------
  1. `Region_Total_Lag_4`      total diario regional en T−4.
  2. `Region_Media_28d_lag4`   media del total regional en [T−31..T−4]
                               (4 semanas de calendario, robusta a un día raro).
  3. `Region_Trend_Ratio`      Region_Media_28d_lag4 / media de las 4 semanas
                               ANTERIORES [T−59..T−32]. >1 = demanda subiendo,
                               <1 = cayendo. Recortado a [0.25, 4] y con
                               fallback 1.0 cuando no hay historial.
  4. `Region_Level_vs_Train`   Region_Media_28d_lag4 / media regional de
                               TRAIN 2024 (constante por región, calculada
                               SOLO sobre train). <1 = la región opera por
                               debajo de su nivel 2024 — exactamente la señal
                               que el modelo necesitaba para Atacama/O'Higgins.
  5. `Estab_Media_28d_lag4`    media de 4 semanas del propio establecimiento:
                               versión estable de `Total_Lag_4` (que es un solo
                               día y por eso es ruidoso).

Las 3 features de nivel/tendencia regional atacan directamente la inercia: si
Atacama cae −17% en 2025, `Region_Level_vs_Train` lo marca en cuanto pasan 4
días, y el árbol puede aprender a bajar la predicción en consecuencia.

Lo demás es IDÉNTICO a v7 (mismas features base, mismos hiperparámetros, mismo
split, misma verificación anti-leakage), de modo que la comparación aísla el
efecto de las features nuevas.

Artefactos (models/):
  - model_rf_directo_v8.joblib
  - model_metadata_v8.json
v7 queda intacto.

Uso:
    python3 src/pipelines/reentrenar_modelo_v8_tendencia.py
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
RUTA_MODELO_OUT = BASE_DIR / "models" / "model_rf_directo_v8.joblib"
RUTA_SALIDA = BASE_DIR / "models" / "model_metadata_v8.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reentrenar_modelo_v7_features_fix as v7  # noqa: E402
import reentrenar_modelo_v5_trailing as v5  # noqa: E402
import reentrenar_modelo_v6_e1_trailing as e1  # noqa: E402

TARGET = v7.TARGET

# Ventanas de las features de tendencia (días de calendario, todas ≤ T-4).
VENTANA_RECIENTE = 28
VENTANA_PREVIA = 28
LAG = v7.LAG_DEMANDA


def _serie_regional_diaria(panel: pd.DataFrame) -> pd.DataFrame:
    """Total diario por región sobre el CALENDARIO completo de cada región."""
    partes = []
    for region, g in panel.groupby("Region"):
        diario = g.groupby("Fecha", as_index=False)[TARGET].sum().sort_values("Fecha")
        cal = pd.date_range(diario["Fecha"].min(), diario["Fecha"].max(), freq="D")
        serie = pd.Series(
            diario[TARGET].to_numpy(), index=pd.DatetimeIndex(diario["Fecha"].to_numpy())
        )
        partes.append(
            pd.DataFrame({
                "Region": region,
                "Fecha": cal,
                "Region_Total_dia": serie.reindex(cal).ffill().to_numpy(),
            })
        )
    return pd.concat(partes, ignore_index=True)


def calcular_features_tendencia(
    panel: pd.DataFrame,
    media_train_region: pd.Series,
) -> pd.DataFrame:
    """Features de nivel y tendencia regional + media móvil del establecimiento.

    ANTI-LEAKAGE: toda ventana termina en T−4. La media de train 2024 es una
    constante por región calculada SOLO con filas de train.
    """
    reg = _serie_regional_diaria(panel)

    partes = []
    for region, g in reg.groupby("Region"):
        g = g.set_index("Fecha").sort_index()
        s = g["Region_Total_dia"]
        lag4 = s.shift(LAG)
        rec = lag4.rolling(VENTANA_RECIENTE, min_periods=7).mean()
        prev = lag4.shift(VENTANA_RECIENTE).rolling(VENTANA_PREVIA, min_periods=7).mean()
        ratio = (rec / prev).clip(lower=0.25, upper=4.0)
        baseline = float(media_train_region.get(region, np.nan))
        nivel = rec / baseline if baseline and np.isfinite(baseline) else np.nan
        partes.append(pd.DataFrame({
            "Region": region,
            "Fecha": s.index,
            "Region_Total_Lag_4": lag4.to_numpy(),
            "Region_Media_28d_lag4": rec.to_numpy(),
            "Region_Trend_Ratio": ratio.to_numpy(),
            "Region_Level_vs_Train": nivel.to_numpy(),
        }))
    regional = pd.concat(partes, ignore_index=True)

    # Media de 4 semanas del propio establecimiento (versión estable de Total_Lag_4).
    estab = []
    for est, g in panel.groupby("IdEstablecimiento"):
        g = g.sort_values("Fecha")
        cal = pd.date_range(g["Fecha"].min(), g["Fecha"].max(), freq="D")
        serie = pd.Series(
            g[TARGET].to_numpy(), index=pd.DatetimeIndex(g["Fecha"].to_numpy())
        ).reindex(cal).ffill()
        media = serie.shift(LAG).rolling(VENTANA_RECIENTE, min_periods=7).mean()
        estab.append(pd.DataFrame({
            "IdEstablecimiento": est,
            "Fecha": cal,
            "Estab_Media_28d_lag4": media.to_numpy(),
        }))
    estab = pd.concat(estab, ignore_index=True)

    return regional, estab


def main() -> None:
    t0 = time.time()
    print("=" * 74)
    print("v8 — v7 + FEATURES DE TENDENCIA REGIONAL (anti-inercia)")
    print("=" * 74)

    df = pd.read_parquet(RUTA_DATOS)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year
    train_raw = df[df["Año"] == v5.TRAIN_YEAR].copy()
    test_raw = df[df["Año"] == v5.TEST_YEAR].copy()
    panel = v7.cargar_panel(df)
    print(f"  Panel estab+fecha: {len(panel):,} | train 2024: {len(train_raw):,} "
          f"| test 2025: {len(test_raw):,}")

    # --- Etapa 1 (v5) idéntica a v7 ---------------------------------------
    print("\n--- Etapa 1 (v5, importada): Pred_Region ---")
    region_train, region_test, dummies_cols, _ = v5.preparar_features_region(
        df, ventana=v5.VENTANA_PRINCIPAL,
    )
    features_region = v5.construir_lista_features(dummies_cols, "trailing")
    res1 = v5.entrenar_etapa_1(region_train, region_test, features_region, con_cv=False)
    print(f"  Región (test 2025): MAE={res1['met_region']['MAE']:.3f} "
          f"R2={res1['met_region']['R2']:.4f}")
    region_train["Pred_Region"] = res1["model"].predict(region_train[features_region])
    region_test["Pred_Region"] = res1["y_pred"]

    # --- Total_Lag_4 + Share_Trailing (idéntico a v7) ----------------------
    print("\n--- Total_Lag_4 + Share_Trailing (idéntico a v7) ---")
    lag_cal = v7.calcular_total_lag_calendario(panel)
    share_2024, n_nuevos = e1.calcular_share_2024_con_fallback(test_raw, train_raw)
    share_grid = v7.calcular_share_trailing_grilla(panel, share_2024)
    print(f"  Estabs en test sin cuota en train (fallback): {n_nuevos}")

    # --- NUEVO v8: features de tendencia regional -------------------------
    print("\n--- NUEVO v8: tendencia regional (ventanas ≤ T-4) ---")
    media_train_region = (
        train_raw.groupby("Region")[TARGET].sum()
        / train_raw.groupby("Region")["Fecha"].nunique()
    )
    reg_feats, estab_feats = calcular_features_tendencia(panel, media_train_region)
    print(f"  Filas features regionales: {len(reg_feats):,} | "
          f"establecimiento: {len(estab_feats):,}")

    # --- Ensamblado (v7 + v8) --------------------------------------------
    print("\n--- Ensamblado del dataset directo ---")
    base = panel.merge(lag_cal, on=["IdEstablecimiento", "Fecha"], how="left")
    base = base.merge(
        share_grid.rename(columns={"share_trailing": "Share_Trailing"}),
        on=["IdEstablecimiento", "Fecha"], how="left",
    )
    base = base.merge(estab_feats, on=["IdEstablecimiento", "Fecha"], how="left")
    base = base.merge(reg_feats, on=["Region", "Fecha"], how="left")
    base = base.merge(
        region_train[["Region", "Fecha", "Pred_Region"] + v7.COLUMNAS_CLIMA_DIRECTO],
        on=["Region", "Fecha"], how="left", suffixes=("", "_rt"),
    )
    base = base.merge(
        region_test[["Region", "Fecha", "Pred_Region"] + v7.COLUMNAS_CLIMA_DIRECTO],
        on=["Region", "Fecha"], how="left", suffixes=("", "_rt"),
    )
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

    direct_train = base[base["Año"] == v5.TRAIN_YEAR].copy()
    direct_test = base[base["Año"] == v5.TEST_YEAR].copy()
    direct_train, direct_test, dummies_tipo = v7.codificar_onehot(
        direct_train, direct_test, "TipoEstablecimiento", "Tipo"
    )
    direct_train, direct_test, dummies_region = v7.codificar_onehot(
        direct_train, direct_test, "Region", "Region"
    )

    # --- Features finales -------------------------------------------------
    core_v7 = ["Total_Lag_4", "Share_Trailing", "Pred_Region", "Pred_E1"]
    nuevas = [
        "Region_Total_Lag_4", "Region_Media_28d_lag4",
        "Region_Trend_Ratio", "Region_Level_vs_Train",
        "Estab_Media_28d_lag4",
    ]
    feature_cols = (
        core_v7 + nuevas + dummies_tipo + dummies_region
        + v7.FEATURES_ESTACIONALIDAD + v7.COLUMNAS_CLIMA_DIRECTO
    )
    print(f"  Features finales ({len(feature_cols)}; v7 tenía "
          f"{len(feature_cols) - len(nuevas)})")

    for c in feature_cols:
        if direct_train[c].isna().any():
            mediana = direct_train[c].median()
            direct_train[c] = direct_train[c].fillna(mediana)
            direct_test[c] = direct_test[c].fillna(mediana)
    print("  NaN imputados con mediana de SOLO train.")

    # --- Anti-leakage ----------------------------------------------------
    print("\n" + "-" * 70)
    print("VERIFICACIÓN ANTI-LEAKAGE")
    print("-" * 70)
    verif = v7.verificar_anti_leakage(direct_train, direct_test, feature_cols)
    for f in nuevas:
        assert f in feature_cols
        corr = float(direct_train[f].corr(direct_train[TARGET]))
        print(f"  {f:26} corr(train, target)={corr:+.3f}")
        assert abs(corr) < 0.995, f"{f} sospechosa de fuga: {corr}"
    print(f"  Total_Lag_4 vs Total corr: "
          f"{verif['correlacion_total_lag_4_vs_total']:.4f} (fuga si >0.99)")

    # --- Entrenamiento ---------------------------------------------------
    print("\n" + "-" * 70)
    print("ENTRENAMIENTO — RandomForest v8 (hiperparámetros de v7)")
    print("-" * 70)
    X_train, y_train = direct_train[feature_cols], direct_train[TARGET]
    X_test, y_test = direct_test[feature_cols], direct_test[TARGET]
    print(f"  Train: {len(X_train):,} | Test: {len(X_test):,} | "
          f"{len(feature_cols)} features")

    t_fit = time.time()
    model = v5.RandomForestRegressor(**v5.HIPERPARAMETROS)
    model.fit(X_train, y_train)
    t_entrenamiento = time.time() - t_fit
    print(f"  Entrenado en {t_entrenamiento:.1f} s")

    y_pred = model.predict(X_test)
    met = v7.metricas(y_test.to_numpy(float), y_pred)

    print("\n" + "-" * 70)
    print("MÉTRICAS v8 — nivel ESTABLECIMIENTO + DÍA (test 2025)")
    print("-" * 70)
    print(f"  MAE={met['MAE']:.4f}  RMSE={met['RMSE']:.4f}  "
          f"R2={met['R2']:.4f}  sesgo={met['sesgo_pct']:+.2f}%  (n={met['n']:,})")
    fuga = bool(met["R2"] is not None and met["R2"] > 0.9)
    print(f"  Sanity R2≤0.9: {'⚠ SOSPECHOSO' if fuga else '✅ OK'}")

    eval_df = direct_test[["IdEstablecimiento", "Region", "Fecha", TARGET]].copy()
    eval_df["pred"] = y_pred
    met_region = {}
    for r, g in eval_df.groupby("Region"):
        met_region[r] = v7.metricas(g[TARGET].to_numpy(float), g["pred"].to_numpy(float))

    # --- Comparativa y sesgo por región ----------------------------------
    meta_v7 = json.loads((BASE_DIR / "models" / "model_metadata_v7.json").read_text())
    ref_v7 = meta_v7["metricas_establecimiento"]
    ref_region_v7 = meta_v7["metricas_por_region"]

    print("\n=== SESGO POR REGIÓN: v7 → v8 ===")
    print(f"  {'Región':<22} {'v7 sesgo':>9} {'v8 sesgo':>9} {'Δ pp':>7} "
          f"{'v7 R2':>7} {'v8 R2':>7}")
    filas = []
    for r in sorted(met_region):
        s7 = ref_region_v7[r]["sesgo_pct"]
        s8 = met_region[r]["sesgo_pct"]
        filas.append((r, s7, s8, s8 - s7))
        print(f"  {r:<22} {s7:>+8.1f}% {s8:>+8.1f}% {s8 - s7:>+7.1f} "
              f"{ref_region_v7[r]['R2']:>7.3f} {met_region[r]['R2']:>7.3f}")

    mejoras = [abs(f[1]) - abs(f[2]) for f in filas]
    print(f"\n  Reducción media de |sesgo|: "
          f"{np.mean(mejoras):+.2f} pp | regiones que mejoran: "
          f"{sum(1 for m in mejoras if m > 0)}/{len(mejoras)}")

    print("\n=== TABLA COMPARATIVA GLOBAL ===")
    comp = pd.DataFrame([
        {"versión": "v7 (16 reg, sin tendencia)", **{
            k: ref_v7[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct"]}},
        {"versión": "v8 (+ tendencia regional)", **{
            k: met[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct"]}},
    ])
    print(comp.round(4).to_string(index=False))

    imp = pd.DataFrame({"feature": feature_cols,
                        "importance": model.feature_importances_}) \
        .sort_values("importance", ascending=False)
    print("\nTop 12 features por importancia:")
    for _, row in imp.head(12).iterrows():
        marca = " ←NUEVA" if row["feature"] in nuevas else ""
        print(f"  {row['feature']:<28} {row['importance']:.4f}{marca}")

    # --- Exportar ---------------------------------------------------------
    joblib.dump(model, RUTA_MODELO_OUT)
    t_total = time.time() - t0
    metadata = {
        "release": "modelo-v8-tendencia",
        "experimento": (
            "v8 — v7 + 5 features de nivel/tendencia regional para corregir la "
            "inercia del modelo al nivel de demanda de train 2024"
        ),
        "descripcion": (
            "Diagnóstico previo: el sesgo por región de v7 correlaciona −0.66 "
            "con el cambio real de volumen 2024→2025 (Atacama −17.3% real → "
            "+28.4% sesgo; O'Higgins −23.8% → +26.6%; Los Lagos +3.4% → "
            "−10.1%). Ninguna feature de v7 reflejaba el nivel regional "
            "reciente, así que el modelo anclaba su predicción al nivel 2024. "
            "v8 agrega features de nivel/tendencia regional con ventanas que "
            "terminan en T−4."
        ),
        "features_nuevas": {
            "Region_Total_Lag_4": "total diario regional en T−4",
            "Region_Media_28d_lag4": "media 4 semanas ([T−31..T−4]) del total regional",
            "Region_Trend_Ratio": "media reciente / media de las 4 semanas previas (clip [0.25,4], fallback 1.0)",
            "Region_Level_vs_Train": "media reciente regional / media regional de TRAIN 2024 (constante train-only)",
            "Estab_Media_28d_lag4": "media 4 semanas del propio establecimiento",
        },
        "justificacion_diagnostica": {
            "correlacion_sesgo_vs_cambio_real_2024_2025": -0.662,
            "correlacion_sesgo_vs_pct_ceros": 0.011,
            "correlacion_r2_vs_pct_ceros": 0.561,
            "estabs_nuevos_en_regiones_mas_sesgadas": (
                "Atacama y O'Higgins: 0 establecimientos nuevos; la caída real "
                "ocurre íntegramente en establecimientos comunes → no es un "
                "artefacto de rotación de establecimientos."
            ),
        },
        "anti_leakage": {
            "ventanas_terminan_en": "T−4",
            "region_level_vs_train_es_constante_train_only": True,
            "verificacion": verif,
            "correlaciones_train_nuevas_features": {
                f: round(float(direct_train[f].corr(direct_train[TARGET])), 4)
                for f in nuevas
            },
        },
        "features_totales": feature_cols,
        "n_features": len(feature_cols),
        "n_features_v7": len(feature_cols) - len(nuevas),
        "configuracion": {
            "target": "Total (nivel, sin transformar)",
            "filas": "una por (establecimiento, fecha)",
            "split": "train = 2024, test = 2025",
            "horizonte_horas": 96,
            "lag_dias": LAG,
            "ventana_reciente_dias": VENTANA_RECIENTE,
            "ventana_previa_dias": VENTANA_PREVIA,
            "semilla": v5.RANDOM_STATE,
            "hiperparametros": {k: v for k, v in v5.HIPERPARAMETROS.items()
                                if k != "n_jobs"},
        },
        "metricas_establecimiento": met,
        "metricas_por_region": met_region,
        "sesgo_por_region_vs_v7": {
            r: {"v7": ref_region_v7[r]["sesgo_pct"],
                "v8": met_region[r]["sesgo_pct"],
                "delta_pp": round(met_region[r]["sesgo_pct"]
                                  - ref_region_v7[r]["sesgo_pct"], 2)}
            for r in met_region
        },
        "comparativa": {
            "v7": {k: ref_v7[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct", "n"]},
            "v8": met,
        },
        "importancia_features": imp.head(20).to_dict("records"),
        "sanity_check": {
            "r2_mayor_a_0_9_sospechoso": fuga,
            "r2_observado": met["R2"],
        },
        "tiempo_entrenamiento_segundos": round(t_entrenamiento, 1),
        "tiempo_total_segundos": round(t_total, 1),
        "limitaciones": [
            "Sigue siendo un split temporal de 2 años: la corrección de "
            "inercia se valida en 2025; con un solo año de test no se puede "
            "distinguir si la tendencia captura un cambio estructural real o "
            "el ruido de un año.",
            "Region_Level_vs_Train usa la media de train 2024 como referencia: "
            "en producción habría que recalcularla con la ventana móvil de "
            "2024 más reciente disponible.",
            "La tendencia usa reporte efectivo por región: si la cobertura de "
            "establecimientos cambia dentro del año, la serie de nivel refleja "
            "ese cambio además de la demanda real.",
        ],
    }
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 74)
    print("✅ v8 COMPLETADO")
    print(f"  Modelo:   {RUTA_MODELO_OUT.name}")
    print(f"  Metadata: {RUTA_SALIDA.name}")
    print(f"  Tiempo total: {t_total:.1f} s")
    print("=" * 74)


if __name__ == "__main__":
    main()
