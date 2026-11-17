"""
v7-ab — Ablación sin persistencia (directivas T2) — MODELO DIRECTO a nivel
establecimiento
================================================================================

Linaje / propósito
------------------
Directiva T2 (`Modelo/docs/DIRECTIVAS_REVISION_PENDIENTE.md`): en v7, tres
codificaciones de la MISMA señal de persistencia concentran 0,728 de la
importancia total (Pred_E1 0,311 + Total_Lag_4 0,304 + Share_Trailing 0,113).
Sin una ablación no se puede responder la pregunta P0 de la defensa: ¿cuánto
del R² 0,7250 lo aportan clima+calendario y cuánto la autocorrelación de la
demanda?

Este script es un CLON CONTROLADO de `reentrenar_modelo_v7_features_fix.py`
(no lo modifica): construye la MISMA matriz de features (mismo parquet, mismo
panel, mismo pipeline, mismas funciones importadas del módulo v7) y entrena
DOS RandomForestRegressor quitando columnas ANTES de ajustar:

  Corrida B (sin persistencia): quita Pred_E1, Total_Lag_4, Share_Trailing,
      Pred_Region → 23 features (one-hot tipo/region + Doy* + 7 climáticas).
  Corrida C (sin persistencia ni calendario): B además quita Doy, Doy_Sin,
      Doy_Cos → 20 features.

RESTRICCIONES (directivas T2 — verificadas por construcción):
  - MISMOS hiperparámetros del RF y MISMA semilla que v7: se importan de
    `v5.HIPERPARAMETROS` / `v5.RANDOM_STATE` (el script v7 base usa exactamente
    los mismos objetos; NO se redefine ni se tunrea nada).
  - Mismo split (train 2024 / test 2025), mismo parquet, mismo protocolo de
    evaluación (nivel establecimiento + día).
  - NO se vuelca joblib de ningún modelo (los dumps de 44 MB no aportan a la
    defensa; solo se crean 2 JSON de metadata).

La Etapa 1 regional SÍ se ejecuta dentro del pipeline (genera Pred_Region
antes de quitarlo de la matriz de B/C), idéntica a v7.

Interpretaciones PRE-REGISTRADAS (odd/tasks/ablacion-sin-persistencia.md):
  - B ≈ 0,2 → el sistema vive de la persistencia.
  - B ≈ 0,5 → el resto (clima+calendario+tipo) aporta sustantivamente.
  - C ≪ B → parte de B era estacionalidad de calendario.
R² NO es aditivo entre corridas: se reportan caídas observadas
("de 0,7250 a X"), nunca fracciones aritméticas.

Salida (models/):
  - model_metadata_v7_ab_sin_persistencia.json       corrida B (23 features)
  - model_metadata_v7_ab_sin_persist_sin_doy.json    corrida C (20 features)

Restricción: este script NO modifica ningún archivo existente; solo crea
estos 2 JSON. No copia, no toca artefactos v6/v7 base.

Uso:
    python3 src/pipelines/reentrenar_v7_ablation.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
RUTA_DATOS = BASE_DIR / "data" / "processed" / "df_modelo.parquet"
RUTA_METADATA_V5 = BASE_DIR / "models" / "model_metadata_v5.json"
RUTA_SALIDA_B = BASE_DIR / "models" / "model_metadata_v7_ab_sin_persistencia.json"
RUTA_SALIDA_C = BASE_DIR / "models" / "model_metadata_v7_ab_sin_persist_sin_doy.json"

TARGET = "Total"
LAG_DEMANDA = 4

# Importar v5, E1 y el módulo v7 SIN ejecutar sus main(): reutilizamos la
# Etapa 1 del v5 (Pred_Region), la cuota trailing de E1 (Share_Trailing) y
# las funciones de construcción/evaluación del v7 para garantizar que la
# matriz sea EXACTAMENTE la misma (clon controlado).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reentrenar_modelo_v5_trailing as v5  # noqa: E402
import reentrenar_modelo_v6_e1_trailing as e1  # noqa: E402
import reentrenar_modelo_v7_features_fix as v7  # noqa: E402

# ---------------------------------------------------------------------------
# Columnas quitadas por corrida (antes de ajustar)
# ---------------------------------------------------------------------------
QUITA_B = ["Pred_E1", "Total_Lag_4", "Share_Trailing", "Pred_Region"]
QUITA_C = QUITA_B + ["Doy", "Doy_Sin", "Doy_Cos"]

# Base A (v7) declarada — comparación obligatoria en los artefactos.
BASE_A = {
    "release": "modelo-v7-features-fix",
    "metricas_test_2025": {
        "n": 118308,
        "MAE": 9.3011,
        "RMSE": 13.0099,
        "R2": 0.7250,
        "sesgo_pct": 8.78,
    },
    "fuente": "models/model_metadata_v7.json",
    "parquet": "data/processed/df_modelo.parquet (base declarada: v7 / 2026-11-15)",
}


def construir_dataset() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Construye el dataset directo EXACTAMENTE como v7 (pasos 1–6 de
    `reentrenar_modelo_v7_features_fix.main`), reutilizando sus funciones.

    Returns:
        (direct_train, direct_test, info) con info = {
            feature_cols_full, core_feats, dummies_tipo, dummies_region,
            etapa1_identica, verificacion, met_region_etapa1,
        }
    """
    df = pd.read_parquet(RUTA_DATOS)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year

    train_raw = df[df["Año"] == v5.TRAIN_YEAR].copy()
    test_raw = df[df["Año"] == v5.TEST_YEAR].copy()
    panel = v7.cargar_panel(df)
    print(f"  Filas crudas: {len(df):,} | panel estab+fecha: {len(panel):,}")

    # --- Etapa 1 (v5 importada): genera Pred_Region (se quita después) -----
    region_train, region_test, dummies_cols, _ = v5.preparar_features_region(
        df, ventana=v5.VENTANA_PRINCIPAL,
    )
    features_region = v5.construir_lista_features(dummies_cols, "trailing")
    res1 = v5.entrenar_etapa_1(region_train, region_test, features_region, con_cv=False)
    print(f"  Etapa 1 (test 2025): MAE={res1['met_region']['MAE']:9.3f}  "
          f"RMSE={res1['met_region']['RMSE']:9.3f}  R²={res1['met_region']['R2']:8.4f}")
    meta_v5 = json.loads(RUTA_METADATA_V5.read_text(encoding="utf-8"))
    etapa1_identica = res1["met_region"] == meta_v5["etapa_1"]["metrics_test_2025"]
    print(f"  Identidad vs model_metadata_v5.json: "
          f"{'✅ COINCIDEN' if etapa1_identica else '⚠️  DIFIEREN'}")

    region_train["Pred_Region"] = res1["model"].predict(region_train[features_region])
    region_test["Pred_Region"] = res1["y_pred"]

    # --- Total_Lag_4 y Share_Trailing (idénticos a v7) ---------------------
    lag_cal = v7.calcular_total_lag_calendario(panel)
    share_2024, n_nuevos = e1.calcular_share_2024_con_fallback(test_raw, train_raw)
    share_grid = v7.calcular_share_trailing_grilla(panel, share_2024)
    print(f"  Grilla share: {len(share_grid):,} filas | "
          f"estabs test sin cuota train: {n_nuevos}")

    # --- Ensamblado (idéntico a v7) ---------------------------------------
    base = panel.merge(lag_cal, on=["IdEstablecimiento", "Fecha"], how="left")
    base = base.merge(
        share_grid.rename(columns={"share_trailing": "Share_Trailing"}),
        on=["IdEstablecimiento", "Fecha"], how="left",
    )
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

    # --- Features completas A (27) + imputación train-only -----------------
    core_feats = ["Total_Lag_4", "Share_Trailing", "Pred_Region", "Pred_E1"]
    feature_cols_full = (
        core_feats
        + dummies_tipo
        + dummies_region
        + v7.FEATURES_ESTACIONALIDAD
        + v7.COLUMNAS_CLIMA_DIRECTO
    )
    assert len(feature_cols_full) == 27, (
        f"Se esperaban 27 features (base A), hay {len(feature_cols_full)}."
    )
    for c in feature_cols_full:
        if direct_train[c].isna().any():
            mediana = direct_train[c].median()
            direct_train[c] = direct_train[c].fillna(mediana)
            direct_test[c] = direct_test[c].fillna(mediana)

    # Verificación anti-leakaje sobre la matriz COMPLETA (idéntica a v7):
    # confirma que la base construida es la misma de la que se recortan B/C.
    verificacion = v7.verificar_anti_leakage(
        direct_train, direct_test, feature_cols_full,
    )
    print(f"  Verificación anti-leakage (matriz base A): "
          f"corr Total_Lag_4 vs Total = "
          f"{verificacion['correlacion_total_lag_4_vs_total']:.4f}")

    info = {
        "feature_cols_full": feature_cols_full,
        "core_feats": core_feats,
        "dummies_tipo": dummies_tipo,
        "dummies_region": dummies_region,
        "etapa1_identica": bool(etapa1_identica),
        "met_region_etapa1": res1["met_region"],
        "verificacion": verificacion,
    }
    return direct_train, direct_test, info


def entrenar_y_evaluar(
    direct_train: pd.DataFrame,
    direct_test: pd.DataFrame,
    feature_cols: list[str],
    etiqueta: str,
) -> tuple[dict, float]:
    """Entrena UN RF con los hiperparámetros congelados de v5 y evalúa en
    test 2025 (nivel establecimiento + día, protocolo idéntico a v7).

    NO vuelca joblib: solo se reportan métricas.
    """
    X_train = direct_train[feature_cols]
    y_train = direct_train[TARGET]
    X_test = direct_test[feature_cols]
    y_test = direct_test[TARGET]
    print(f"\n  [{etiqueta}] Train: {len(X_train):,} filas | "
          f"Test: {len(X_test):,} filas | {len(feature_cols)} features")
    print(f"  [{etiqueta}] Features: {feature_cols}")

    t_fit = time.time()
    model = v5.RandomForestRegressor(**v5.HIPERPARAMETROS)
    model.fit(X_train, y_train)
    t_fit_seg = time.time() - t_fit

    y_pred = model.predict(X_test)
    if np.isnan(y_pred).any():
        raise RuntimeError(f"[{etiqueta}] predicciones con NaN: abortar y reportar.")
    met = v7.metricas(y_test.to_numpy(float), y_pred)

    print(f"  [{etiqueta}] ✅ RF en {t_fit_seg:.1f} s → "
          f"MAE={met['MAE']:.4f}  RMSE={met['RMSE']:.4f}  R²={met['R2']:.4f}  "
          f"sesgo={met['sesgo_pct']:+.2f}%  (n={met['n']:,})")

    # Guards anti-métricas-raras (directivas del contrato de ejecución).
    if met["R2"] is None or not np.isfinite(met["R2"]):
        raise RuntimeError(f"[{etiqueta}] R² inválido ({met['R2']}): abortar.")
    if met["R2"] > 0.9:
        raise RuntimeError(
            f"[{etiqueta}] R²={met['R2']:.4f} > 0.9 → sospechoso de fuga. "
            "Abortar y reportar."
        )
    if met["R2"] > BASE_A["metricas_test_2025"]["R2"]:
        print(f"  [{etiqueta}] ⚠️  ATENCIÓN: R² ({met['R2']:.4f}) > base A "
              f"({BASE_A['metricas_test_2025']['R2']:.4f}) — revisar antes de "
              "publicar.")

    return met, t_fit_seg


def armar_metadata(
    *,
    release: str,
    experimento: str,
    descripcion: str,
    quita: list[str],
    feature_cols: list[str],
    met: dict,
    info: dict,
    salida: str,
    t_fit_seg: float,
    t_total_seg: float,
) -> dict:
    """Metadata al estilo de model_metadata_v7.json (campos exigidos T2)."""
    base_m = BASE_A["metricas_test_2025"]
    return {
        "release": release,
        "experimento": experimento,
        "descripcion": descripcion,
        "base_declarada": {
            "modelo_base": "v7 (modelo-v7-features-fix, E2 directo)",
            "parquet": BASE_A["parquet"],
            "script_base": "src/pipelines/reentrenar_modelo_v7_features_fix.py",
            "script_ablacion": "src/pipelines/reentrenar_v7_ablation.py",
            "motivo": (
                "Directiva T2: las 3 codificaciones de persistencia "
                "(Pred_E1 0,311 + Total_Lag_4 0,304 + Share_Trailing 0,113) "
                "suman 0,728 de la importancia total de v7; sin esta ablación "
                "no se puede atribuir el desempeño a clima/calendario vs "
                "autocorrelación."
            ),
        },
        "features": feature_cols,
        "n_features": len(feature_cols),
        "features_quitadas": quita,
        "configuracion": {
            "target": "Total (nivel, sin transformar)",
            "filas": "una por (establecimiento, fecha)",
            "split": "train = 2024, test = 2025 (idéntico a v7)",
            "modelo": "RandomForestRegressor (hiperparámetros del v5, SIN tuning)",
            "semilla": v5.RANDOM_STATE,
            "hiperparametros": {
                k: v for k, v in v5.HIPERPARAMETROS.items() if k != "n_jobs"
            },
            "hiperparametros_identicos_a_v7": True,
            "horizonte_horas": 96,
            "lag_dias": LAG_DEMANDA,
            "features_detalle": {
                "one_hot_tipo_establecimiento": info["dummies_tipo"],
                "one_hot_region": info["dummies_region"],
                "estacionalidad": [
                    c for c in v7.FEATURES_ESTACIONALIDAD if c in feature_cols
                ],
                "clima_regional_dia_T": v7.COLUMNAS_CLIMA_DIRECTO,
            },
        },
        "metricas_establecimiento": met,
        "comparativa_contra_base_A": {
            "base_A_v7": base_m,
            "fuente_base_A": BASE_A["fuente"],
            "caidas_observadas": {
                "MAE": round(met["MAE"] - base_m["MAE"], 4),
                "RMSE": round(met["RMSE"] - base_m["RMSE"], 4),
                "R2": round(base_m["R2"] - met["R2"], 4),
                "sesgo_pct_pts": round(met["sesgo_pct"] - base_m["sesgo_pct"], 2),
            },
            "nota_redaccion": (
                "R² NO es aditivo: 'caidas_observadas' son diferencias "
                "observadas en el mismo split (de 0,7250 a "
                f"{met['R2']}), NO fracciones del desempeño explicadas por "
                "las features quitadas."
            ),
        },
        "identidad_pipeline_vs_v7": {
            "mismo_parquet": True,
            "mismo_split": True,
            "mismos_hiperparametros_semilla": True,
            "etapa_1_identica_a_v5": info["etapa1_identica"],
            "etapa_1_metrics_test_2025": info["met_region_etapa1"],
            "matriz_base_A_verificada_anti_leakage": info["verificacion"],
            "nota": (
                "La matriz completa A (27 features) se construye con las "
                "mismas funciones del módulo v7 y se verifica anti-leakage "
                "ANTES de recortar; B/C son subconjuntos de esa misma matriz "
                "imputada con medianas de solo train."
            ),
        },
        "sanity_check": {
            "r2_mayor_a_0_9_sospechoso_de_fuga": bool(met["R2"] > 0.9),
            "predicciones_nan": False,
            "r2_mayor_que_base_A": bool(met["R2"] > base_m["R2"]),
        },
        "interpretacion_preregistrada": {
            "B_cerca_de_0_2": "el sistema vive de la persistencia",
            "B_cerca_de_0_5": "el resto (clima+calendario+tipo) aporta sustantivamente",
            "C_mmu_b": "parte del aporte de B era estacionalidad de calendario",
            "advertencia": "R² no es aditivo entre corridas.",
        },
        "sin_joblib": (
            "No se vuelca ningún modelo RF (los dumps de ~44 MB no aportan a "
            "la defensa T2); este JSON es el artefacto de evidencia."
        ),
        "salida": salida,
        "tiempo_entrenamiento_segundos": round(t_fit_seg, 1),
        "tiempo_total_script_segundos": round(t_total_seg, 1),
    }


def main() -> None:
    t_inicio = time.time()
    print("=" * 70)
    print("v7-ab — ABLACIÓN SIN PERSISTENCIA (directivas T2) — corridas B y C")
    print("=" * 70)

    print("\nConfiguración congelada (idéntica a v7, SIN tuning):")
    print(f"  HIPERPARAMETROS (v5.HIPERPARAMETROS): {v5.HIPERPARAMETROS}")
    print(f"  RANDOM_STATE (v5.RANDOM_STATE): {v5.RANDOM_STATE}")

    print("\n--- Construcción de la matriz (clon del pipeline v7) ---")
    direct_train, direct_test, info = construir_dataset()

    # -----------------------------------------------------------------------
    # Corrida B — sin persistencia (23 features)
    # -----------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("CORRIDA B — SIN PERSISTENCIA (quita Pred_E1, Total_Lag_4, "
          "Share_Trailing, Pred_Region)")
    print("-" * 70)
    feats_b = [c for c in info["feature_cols_full"] if c not in QUITA_B]
    assert len(feats_b) == 23, f"Se esperaban 23 features en B, hay {len(feats_b)}."
    met_b, t_fit_b = entrenar_y_evaluar(direct_train, direct_test, feats_b, "B")

    # -----------------------------------------------------------------------
    # Corrida C — sin persistencia ni calendario (20 features)
    # -----------------------------------------------------------------------
    print("\n" + "-" * 70)
    print("CORRIDA C — SIN PERSISTENCIA NI CALENDARIO (B quita Doy, Doy_Sin, "
          "Doy_Cos)")
    print("-" * 70)
    feats_c = [c for c in info["feature_cols_full"] if c not in QUITA_C]
    assert len(feats_c) == 20, f"Se esperaban 20 features en C, hay {len(feats_c)}."
    met_c, t_fit_c = entrenar_y_evaluar(direct_train, direct_test, feats_c, "C")

    # -----------------------------------------------------------------------
    # Tabla resumen A / B / C
    # -----------------------------------------------------------------------
    base_m = BASE_A["metricas_test_2025"]
    print("\n" + "=" * 70)
    print("TABLA A/B/C — nivel ESTABLECIMIENTO + DÍA (test 2025)")
    print("=" * 70)
    print(f"  {'Corrida':<34} {'n':>7} {'MAE':>9} {'RMSE':>9} {'R²':>8} {'Sesgo':>9}")
    filas = [
        ("A base v7 (27 feats)", base_m),
        (f"B sin persistencia ({len(feats_b)} feats)", met_b),
        (f"C sin persist+calendario ({len(feats_c)} feats)", met_c),
    ]
    for nombre, m in filas:
        print(f"  {nombre:<34} {m['n']:>7,} {m['MAE']:>9.4f} {m['RMSE']:>9.4f} "
              f"{m['R2']:>8.4f} {m['sesgo_pct']:>8.2f}%")

    t_total = time.time() - t_inicio

    # -----------------------------------------------------------------------
    # Artefactos (2 JSON, sin joblib)
    # -----------------------------------------------------------------------
    RUTA_SALIDA_B.parent.mkdir(parents=True, exist_ok=True)
    meta_b = armar_metadata(
        release="modelo-v7-ab-sin-persistencia",
        experimento=(
            "Corrida B — ablación sin persistencia: mismo pipeline/RF de v7 "
            "quitando las 4 features de persistencia (Pred_E1, Total_Lag_4, "
            "Share_Trailing, Pred_Region) antes de ajustar"
        ),
        descripcion=(
            "v7-ab B = matriz de v7 (27 features) menos las 4 codificaciones "
            "de la señal de persistencia → 23 features (one-hot tipo/región, "
            "Doy/Doy_Sin/Doy_Cos, 7 climáticas regionales). Responde a la P0 "
            "de la defensa: cuánto del desempeño de v7 requiere historia de "
            "la demanda. Mismo parquet, mismo split 2024/2025, mismos "
            "hiperparámetros y semilla que v7 (sin tuning), misma Etapa 1 "
            "regional (se ejecuta para construir la matriz y luego se quita)."
        ),
        quita=QUITA_B,
        feature_cols=feats_b,
        met=met_b,
        info=info,
        salida="models/model_metadata_v7_ab_sin_persistencia.json",
        t_fit_seg=t_fit_b,
        t_total_seg=t_total,
    )
    meta_c = armar_metadata(
        release="modelo-v7-ab-sin-persist-sin-doy",
        experimento=(
            "Corrida C — ablación sin persistencia ni calendario: corrida B "
            "además sin Doy, Doy_Sin, Doy_Cos (20 features)"
        ),
        descripcion=(
            "v7-ab C = matriz B (23 features) menos la estacionalidad de "
            "calendario Doy/Doy_Sin/Doy_Cos → 20 features (one-hot tipo/"
            "región + 7 climáticas regionales). Aísla clima+tipo puro: si "
            "C ≈ B, la estacionalidad de calendario NO es el motor del "
            "resto sustantivo. Mismas condiciones congeladas que v7."
        ),
        quita=QUITA_C,
        feature_cols=feats_c,
        met=met_c,
        info=info,
        salida="models/model_metadata_v7_ab_sin_persist_sin_doy.json",
        t_fit_seg=t_fit_c,
        t_total_seg=t_total,
    )
    with open(RUTA_SALIDA_B, "w", encoding="utf-8") as f:
        json.dump(meta_b, f, ensure_ascii=False, indent=2)
    with open(RUTA_SALIDA_C, "w", encoding="utf-8") as f:
        json.dump(meta_c, f, ensure_ascii=False, indent=2)

    print(f"\n✅ ABLACIÓN COMPLETADA — sin dumps de joblib")
    print(f"  B: {RUTA_SALIDA_B}")
    print(f"  C: {RUTA_SALIDA_C}")
    print(f"  Tiempo total: {t_total:.1f} s")
    print("=" * 70)


if __name__ == "__main__":
    main()
