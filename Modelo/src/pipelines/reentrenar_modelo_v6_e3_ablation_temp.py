"""
Ablación E3 (v6) — TEMPERATURA: ¿absolutas (E2) vs categorías (estilo v1)?
=============================================================================

Contexto (por qué existe este script)
--------------------------------------
El modelo E2 (v6) usa 4 features de temperatura CONTINUAS: TempMin, TempMax,
TempMin_Lag_4D y Region_Media_7d_TempMin. El modelo original (v1 y la
feature_engineering.py) usaba en su lugar categorías clínicas de temperatura
([-inf, -5, 5, 15, 25, inf] → Muy Frío / Frío / Templado / Cálido / Caluroso),
codificadas ordinalmente en el encoders.joblib original.

Este experimento responde con NÚMEROS la pregunta de defensa:
  ¿dieron mejores resultados las temperaturas ABSOLUTAS (v6 actual) que las
  CATEGORÍAS de temperatura (estilo v1)?

Diseño: 3 configuraciones IDÉNTICAS salvo por el bloque de temperatura
------------------------------------------------------------------------
Mismos datos, mismo split (train 2024 / test 2025), mismo RF (mismos
hiperparámetros y semilla que E2/v5), mismas 27 features de base, mismo
imputado (mediana de SOLO train), misma evaluación (MAE/RMSE/R²/sesgo a nivel
establecimiento+día, global y por región).

  - Config A — Absolutas (CONTROL): las 4 continuas tal cual E2. Debe
    reproducir E2 EXACTAMENTE (MAE 9.3338 / RMSE 13.0481 / R² 0.7231 /
    sesgo +9.77%, n=118.452). Si no reproduce, el experimento es inválido y
    el script se detiene (exit 1) antes de entrenar B/C.
  - Config B — Categóricas ONE-HOT: cada continua se recorta con los bins
    clínicos y se codifica one-hot (pd.get_dummies con columnas de la UNIÓN
    train+test, mismo criterio que e2.codificar_onehot). El lag y la media 7d
    se categorizan DESPUÉS de calcularse en continuo (no se recalcula rolling
    sobre categorías): la categoría describe el «régimen de temperatura» de
    esa ventana.
  - Config C — Categóricas ORDINAL (estilo v1): mismos bins, codificación
    Muy Frío=0, Frío=1, Templado=2, Cálido=3, Caluroso=4 (una columna por
    feature), igual que el encoders.joblib original.

Constantes en las 3 configs:
  - Frio_Polar_Flag (TempMin ≤ 2 °C) se MANTIENE: es una hipótesis clínica,
    no la variable bajo test; ya viene calculado sobre el continuo original.
  - Precipitacion_mm, Lluvia_Intensa_Flag, demanda, cuota, Pred_Region/Pred_E1,
    estacionalidad y one-hot de Tipo/Región: idénticos en las 3.
  - NaN de temperatura: se imputan ANTES de categorizar con la mediana de
    train sobre el CONTINUO (igual que E2), así las categorías quedan bien
    definidas. Sanity: las categorías resultantes solo toman los 5 valores.

Anti-leakage: idéntico al E2 (features ≤ T-4; clima del día T bajo el supuesto
ya aceptado por v5/v6). Este script IMPORTA las funciones de E2/v5/E1 sin
modificarlos.

Salida:
  - models/model_metadata_v6e3_ablation_temp.json  (las 3 configs con
    métricas globales y por región, comparativa A−B y A−C con deltas, la
    conclusión numérica, bins, semilla/hiperparámetros y nota metodológica).
  - NO guarda modelos .joblib: es un experimento de EVIDENCIA, la metadata
    basta.

Restricción: NO modifica ningún archivo existente (E2/E1/v5 intactos); solo
crea este script y su metadata.

Uso:
    python3 src/pipelines/reentrenar_modelo_v6_e3_ablation_temp.py
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
RUTA_METADATA_E2 = BASE_DIR / "models" / "model_metadata_v6e2.json"
RUTA_SALIDA = BASE_DIR / "models" / "model_metadata_v6e3_ablation_temp.json"

# ---------------------------------------------------------------------------
# Importar E2/v5/E1 SIN ejecutar sus main(): reutilizamos el ensamblado del
# dataset directo (mismas funciones) y el RF de la Etapa 1 (Pred_Region).
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reentrenar_modelo_v5_trailing as v5  # noqa: E402
import reentrenar_modelo_v6_e1_trailing as e1  # noqa: E402
import reentrenar_modelo_v6_e2_directo as e2  # noqa: E402

# ---------------------------------------------------------------------------
# Bloque bajo test: las 4 features de temperatura del E2
# ---------------------------------------------------------------------------
FEATURES_TEMP = [
    "TempMin",
    "TempMax",
    "TempMin_Lag_4D",
    "Region_Media_7d_TempMin",
]

# Mismos bins que feature_engineering.discretize_temperature (L164-193).
BINS = [-np.inf, -5, 5, 15, 25, np.inf]
LABELS = ["Muy Frío", "Frío", "Templado", "Cálido", "Caluroso"]
CODIFICACION_ORDINAL = {etiqueta: i for i, etiqueta in enumerate(LABELS)}

# Clima que NO se testea (se mantiene en las 3 configs).
CLIMA_FIJO = ["Precipitacion_mm", "Frio_Polar_Flag", "Lluvia_Intensa_Flag"]

CORE_FEATS = ["Total_Lag_4", "Share_Trailing", "Pred_Region", "Pred_E1"]
TARGET = e2.TARGET

# Métricas de referencia E2 (control A debe reproducirlas EXACTAMENTE).
E2_REFERENCIA = {"MAE": 9.3338, "RMSE": 13.0481, "R2": 0.7231, "sesgo_pct": 9.77}


def construir_dataset_directo() -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str], dict]:
    """Replica el ensamblado del dataset directo de E2 (main, pasos 1–5).

    Devuelve (direct_train, direct_test, dummies_tipo, dummies_region, info_etapa1)
    con las columnas crudas (SIN imputar): el imputado y el bloque de
    temperatura se aplican después, por config.
    """
    df = pd.read_parquet(RUTA_DATOS)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year

    train_raw = df[df["Año"] == v5.TRAIN_YEAR].copy()
    test_raw = df[df["Año"] == v5.TEST_YEAR].copy()
    panel = e2.cargar_panel(df)

    # Etapa 1 del v5 (importada) — Pred_Region + clima regional del día.
    region_train, region_test, dummies_cols, _info_trail = v5.preparar_features_region(
        df, ventana=v5.VENTANA_PRINCIPAL,
    )
    features_region = v5.construir_lista_features(dummies_cols, "trailing")
    res1 = v5.entrenar_etapa_1(region_train, region_test, features_region, con_cv=False)
    meta_v5 = json.loads(RUTA_METADATA_V5.read_text(encoding="utf-8"))
    etapa1_identica = res1["met_region"] == meta_v5["etapa_1"]["metrics_test_2025"]

    # Pred_Region para train (in-sample) y test (genuino), igual que E2.
    region_train["Pred_Region"] = res1["model"].predict(region_train[features_region])
    region_test["Pred_Region"] = res1["y_pred"]

    # Total_Lag_4 (calendario) y Share_Trailing (cuota E1).
    lag_cal = e2.calcular_total_lag_calendario(panel)
    share_2024, n_nuevos = e1.calcular_share_2024_con_fallback(test_raw, train_raw)
    share_grid = e2.calcular_share_trailing_grilla(panel, share_2024)

    base = panel.merge(lag_cal, on=["IdEstablecimiento", "Fecha"], how="left")
    base = base.merge(
        share_grid.rename(columns={"share_trailing": "Share_Trailing"}),
        on=["IdEstablecimiento", "Fecha"], how="left",
    )
    base = base.merge(
        region_train[["Region", "Fecha", "Pred_Region"] + e2.COLUMNAS_CLIMA_DIRECTO],
        on=["Region", "Fecha"], how="left", suffixes=("", "_rt"),
    )
    base = base.merge(
        region_test[["Region", "Fecha", "Pred_Region"] + e2.COLUMNAS_CLIMA_DIRECTO],
        on=["Region", "Fecha"], how="left", suffixes=("", "_rt"),
    )
    for c in ["Pred_Region"] + e2.COLUMNAS_CLIMA_DIRECTO:
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

    direct_train, direct_test, dummies_tipo = e2.codificar_onehot(
        direct_train, direct_test, "TipoEstablecimiento", "Tipo"
    )
    direct_train, direct_test, dummies_region = e2.codificar_onehot(
        direct_train, direct_test, "Region", "Region"
    )

    info_etapa1 = {
        "etapa_1_region_identica_a_v5": bool(etapa1_identica),
        "establecimientos_test_sin_share_train": int(n_nuevos),
    }
    return direct_train, direct_test, dummies_tipo, dummies_region, info_etapa1


def imputar(train_df: pd.DataFrame, test_df: pd.DataFrame, cols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Imputa NaN con la mediana de SOLO train (anti-leakage), igual que E2."""
    for c in cols:
        if train_df[c].isna().any():
            mediana = train_df[c].median()
            train_df[c] = train_df[c].fillna(mediana)
            test_df[c] = test_df[c].fillna(mediana)
    return train_df, test_df


def categorizar(
    train_df: pd.DataFrame, test_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Imputa las 4 temp con mediana de train y las recorta en 5 categorías.

    El imputado es SOBRE EL CONTINUO (mediana de train, igual que E2) y se hace
    ANTES de categorizar, así las categorías quedan bien definidas. El lag y la
    media 7d ya vienen calculados en continuo (no se recalcula rolling).
    """
    train_df = train_df.copy()
    test_df = test_df.copy()

    medianas: dict[str, float] = {}
    for c in FEATURES_TEMP:
        mediana = float(train_df[c].median())
        medianas[c] = mediana
        train_df[c] = train_df[c].fillna(mediana)
        test_df[c] = test_df[c].fillna(mediana)

    for c in FEATURES_TEMP:
        cat = pd.cut(
            train_df[c], bins=BINS, labels=LABELS, include_lowest=True,
        ).astype(str)
        cat_test = pd.cut(
            test_df[c], bins=BINS, labels=LABELS, include_lowest=True,
        ).astype(str)
        permitidas = set(LABELS)
        assert set(cat.unique()) <= permitidas, f"Valores fuera de cats en train {c}: {set(cat.unique())}"
        assert set(cat_test.unique()) <= permitidas, f"Valores fuera de cats en test {c}: {set(cat_test.unique())}"
        train_df[f"{c}_Cat"] = cat
        test_df[f"{c}_Cat"] = cat_test

    return train_df, test_df, medianas


def entrenar_y_evaluar(
    direct_train: pd.DataFrame,
    direct_test: pd.DataFrame,
    feature_cols: list[str],
) -> tuple[dict, dict, object]:
    """Entrena el RF (hiperparámetros de v5/E2) y devuelve métricas global/por región."""
    tr, te = imputar(direct_train.copy(), direct_test.copy(), feature_cols)

    X_train = tr[feature_cols]
    y_train = tr[TARGET]
    X_test = te[feature_cols]
    y_test = te[TARGET]

    model = v5.RandomForestRegressor(**v5.HIPERPARAMETROS)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    met_global = e2.metricas(y_test.to_numpy(float), y_pred)

    eval_df = te[["IdEstablecimiento", "Region", "Fecha", TARGET]].copy()
    eval_df["pred"] = y_pred
    met_region: dict[str, dict] = {}
    for reg, grp in eval_df.groupby("Region"):
        met_region[reg] = e2.metricas(grp[TARGET].to_numpy(float), grp["pred"].to_numpy(float))

    return met_global, met_region, model


def main() -> None:
    t_inicio = time.time()
    print("=" * 70)
    print("ABLACIÓN E3 (v6) — TEMPERATURA: ABSOLUTAS vs CATEGÓRICAS")
    print("=" * 70)
    print(f"Bins clínicos: {BINS} → {LABELS}")
    print(f"Features bajo test: {FEATURES_TEMP}")

    # -----------------------------------------------------------------------
    # 1. Ensamblado (idéntico a E2) — una sola vez para las 3 configs
    # -----------------------------------------------------------------------
    print("\n--- Ensamblado del dataset directo (idéntico a E2) ---")
    direct_train, direct_test, dummies_tipo, dummies_region, info_etapa1 = (
        construir_dataset_directo()
    )
    print(f"  Train 2024: {len(direct_train):,} filas | Test 2025: {len(direct_test):,} filas")
    print(f"  Etapa 1 idéntica a v5: {info_etapa1['etapa_1_region_identica_a_v5']}")

    base_feats = CORE_FEATS + dummies_tipo + dummies_region + e2.FEATURES_ESTACIONALIDAD

    # -----------------------------------------------------------------------
    # 2. Config A — ABSOLUTAS (control): debe reproducir E2 exactamente
    # -----------------------------------------------------------------------
    print("\n--- Config A — Absolutas (CONTROL, = E2) ---")
    feats_a = base_feats + e2.COLUMNAS_CLIMA_DIRECTO  # mismo orden exacto que E2
    met_a, reg_a, modelo_a = entrenar_y_evaluar(direct_train, direct_test, feats_a)
    print(f"  MAE={met_a['MAE']:.4f}  RMSE={met_a['RMSE']:.4f}  "
          f"R²={met_a['R2']:.4f}  sesgo={met_a['sesgo_pct']:+.2f}%  (n={met_a['n']:,})")

    meta_e2 = json.loads(RUTA_METADATA_E2.read_text(encoding="utf-8"))
    met_e2 = meta_e2["metricas_establecimiento"]
    control_ok = (
        met_a["MAE"] == E2_REFERENCIA["MAE"]
        and met_a["RMSE"] == E2_REFERENCIA["RMSE"]
        and met_a["R2"] == E2_REFERENCIA["R2"]
        and met_a["sesgo_pct"] == E2_REFERENCIA["sesgo_pct"]
        and met_a["n"] == met_e2["n"]
    )
    print(f"  Control A vs E2 (9.3338/13.0481/0.7231/+9.77): "
          f"{'✅ REPRODUCE EXACTO' if control_ok else '❌ NO REPRODUCE'}")
    if not control_ok:
        print("\n" + "=" * 70)
        print("⛔ BLOQUEADO — el control A NO reproduce E2: experimento inválido.")
        print(f"  Esperado (E2): {E2_REFERENCIA} (n={met_e2['n']})")
        print(f"  Obtenido (A) : MAE={met_a['MAE']}  RMSE={met_a['RMSE']}  "
              f"R2={met_a['R2']}  sesgo={met_a['sesgo_pct']}  (n={met_a['n']})")
        print("=" * 70)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # 3. Categorización (común a B y C): imputar continuo → recortar bins
    # -----------------------------------------------------------------------
    train_cat, test_cat, medianas_temp = categorizar(direct_train, direct_test)
    print(f"\n  Categorías creadas (imputado previo con mediana de train):")
    for c in FEATURES_TEMP:
        n_tr = int((direct_train[c].isna()).sum())
        n_te = int((direct_test[c].isna()).sum())
        print(f"    {c:<26} mediana={medianas_temp[c]:7.3f}  NaN imputados: "
              f"train={n_tr} test={n_te}")
    dist = pd.concat([
        train_cat[f"{c}_Cat"].value_counts() for c in FEATURES_TEMP
    ], axis=1, keys=FEATURES_TEMP).reindex(LABELS).fillna(0).astype(int)
    print("  Distribución de categorías (train+test, conteo por feature):")
    print("  " + dist.to_string())

    # -----------------------------------------------------------------------
    # 4. Config B — CATEGÓRICAS ONE-HOT
    # -----------------------------------------------------------------------
    print("\n--- Config B — Categóricas ONE-HOT (bins clínicos) ---")
    tr_b, te_b = train_cat.copy(), test_cat.copy()
    dummies_temp_b: list[str] = []
    for c in FEATURES_TEMP:
        tr_b, te_b, cols = e2.codificar_onehot(tr_b, te_b, f"{c}_Cat", f"{c}_Cat")
        dummies_temp_b += cols
        tr_b = tr_b.drop(columns=[f"{c}_Cat"])
        te_b = te_b.drop(columns=[f"{c}_Cat"])
    feats_b = base_feats + CLIMA_FIJO + dummies_temp_b
    met_b, reg_b, modelo_b = entrenar_y_evaluar(tr_b, te_b, feats_b)
    print(f"  Features: {len(feats_b)} (27 base − 4 temp continuas + "
          f"{len(dummies_temp_b)} dummies)")
    print(f"  MAE={met_b['MAE']:.4f}  RMSE={met_b['RMSE']:.4f}  "
          f"R²={met_b['R2']:.4f}  sesgo={met_b['sesgo_pct']:+.2f}%  (n={met_b['n']:,})")

    # -----------------------------------------------------------------------
    # 5. Config C — CATEGÓRICAS ORDINAL (estilo v1)
    # -----------------------------------------------------------------------
    print("\n--- Config C — Categóricas ORDINAL (estilo v1: 0..4) ---")
    tr_c, te_c = train_cat.copy(), test_cat.copy()
    cols_ordinales: list[str] = []
    for c in FEATURES_TEMP:
        nombre = f"{c}_CatOrd"
        tr_c[nombre] = tr_c[f"{c}_Cat"].map(CODIFICACION_ORDINAL).astype(int)
        te_c[nombre] = te_c[f"{c}_Cat"].map(CODIFICACION_ORDINAL).astype(int)
        assert set(tr_c[nombre].unique()) <= {0, 1, 2, 3, 4}
        assert set(te_c[nombre].unique()) <= {0, 1, 2, 3, 4}
        cols_ordinales.append(nombre)
        tr_c = tr_c.drop(columns=[f"{c}_Cat"])
        te_c = te_c.drop(columns=[f"{c}_Cat"])
    feats_c = base_feats + CLIMA_FIJO + cols_ordinales
    met_c, reg_c, modelo_c = entrenar_y_evaluar(tr_c, te_c, feats_c)
    print(f"  Features: {len(feats_c)} (27 base − 4 temp continuas + 4 ordinales)")
    print(f"  MAE={met_c['MAE']:.4f}  RMSE={met_c['RMSE']:.4f}  "
          f"R²={met_c['R2']:.4f}  sesgo={met_c['sesgo_pct']:+.2f}%  (n={met_c['n']:,})")

    # -----------------------------------------------------------------------
    # 6. Tabla comparativa + deltas A−B / A−C
    # -----------------------------------------------------------------------
    configs = {
        "A_absolutas_control": {
            "descripcion": "4 temperaturas CONTINUAS tal cual E2 (control)",
            "metricas_establecimiento": met_a,
            "metricas_por_region": reg_a,
            "features": feats_a,
            "n_features": len(feats_a),
        },
        "B_categoricas_onehot": {
            "descripcion": (
                "Las 4 temperaturas recortadas con bins clínicos y codificadas "
                "one-hot (unión train+test)"
            ),
            "metricas_establecimiento": met_b,
            "metricas_por_region": reg_b,
            "features": feats_b,
            "n_features": len(feats_b),
        },
        "C_categoricas_ordinal": {
            "descripcion": (
                "Las 4 temperaturas con bins clínicos codificados ordinalmente "
                "(Muy Frío=0 … Caluroso=4), estilo v1/encoders.joblib"
            ),
            "metricas_establecimiento": met_c,
            "metricas_por_region": reg_c,
            "features": feats_c,
            "n_features": len(feats_c),
        },
    }

    def delta(a: dict, b: dict) -> dict:
        """A − B (control menos variante) por métrica."""
        return {
            "MAE": round(a["MAE"] - b["MAE"], 4),
            "RMSE": round(a["RMSE"] - b["RMSE"], 4),
            "R2": round(a["R2"] - b["R2"], 4),
            "sesgo_pct": round(a["sesgo_pct"] - b["sesgo_pct"], 2),
        }

    delta_ab = delta(met_a, met_b)
    delta_ac = delta(met_a, met_c)

    print("\n" + "=" * 70)
    print("📊 TABLA COMPARATIVA — nivel ESTABLECIMIENTO + DÍA (test 2025)")
    print("=" * 70)
    tabla = pd.DataFrame({
        "A_absolutas": met_a,
        "B_onehot": met_b,
        "C_ordinal": met_c,
    }).T
    tabla.index.name = "Config"
    print(tabla[["n", "MAE", "RMSE", "R2", "sesgo_pct"]].round(4).to_string())
    print("\nDeltas (A − B y A − C; en MAE/RMSE negativo = las ABSOLUTAS ganan):")
    print(f"  A − B (onehot) : MAE={delta_ab['MAE']:+.4f}  RMSE={delta_ab['RMSE']:+.4f}  "
          f"R²={delta_ab['R2']:+.4f}  sesgo={delta_ab['sesgo_pct']:+.2f} pp")
    print(f"  A − C (ordinal): MAE={delta_ac['MAE']:+.4f}  RMSE={delta_ac['RMSE']:+.4f}  "
          f"R²={delta_ac['R2']:+.4f}  sesgo={delta_ac['sesgo_pct']:+.2f} pp")

    print("\nMAE por región (las 3 configs):")
    print(f"  {'Región':<22} {'A abs':>9} {'B onehot':>9} {'C ordinal':>9}")
    for reg in sorted(reg_a):
        print(f"  {reg:<22} {reg_a[reg]['MAE']:>9.3f} {reg_b[reg]['MAE']:>9.3f} "
              f"{reg_c[reg]['MAE']:>9.3f}")

    # -----------------------------------------------------------------------
    # 7. Conclusión numérica
    # -----------------------------------------------------------------------
    mejor_b = met_b["MAE"] - met_a["MAE"]   # >0 → absolutas ganan (MAE menor)
    mejor_c = met_c["MAE"] - met_a["MAE"]
    absolutas_ganan_onehot = met_a["MAE"] < met_b["MAE"]
    absolutas_ganan_ordinal = met_a["MAE"] < met_c["MAE"]
    margen_vs_b = abs(mejor_b) / met_a["MAE"] * 100
    margen_vs_c = abs(mejor_c) / met_a["MAE"] * 100

    print("\n" + "-" * 70)
    print("CONCLUSIÓN NUMÉRICA")
    print("-" * 70)
    print(f"  vs ONE-HOT (B): {'✅ ABSOLUTAS GANAN' if absolutas_ganan_onehot else '❌ ABSOLUTAS PERDEN'} "
          f"por MAE {abs(mejor_b):.4f} ({margen_vs_b:.2f}% del control), "
          f"ΔR²={delta_ab['R2']:+.4f}")
    print(f"  vs ORDINAL (C): {'✅ ABSOLUTAS GANAN' if absolutas_ganan_ordinal else '❌ ABSOLUTAS PERDEN'} "
          f"por MAE {abs(mejor_c):.4f} ({margen_vs_c:.2f}% del control), "
          f"ΔR²={delta_ac['R2']:+.4f}")

    # -----------------------------------------------------------------------
    # 8. Exportar metadata (SIN modelos .joblib: es un experimento de evidencia)
    # -----------------------------------------------------------------------
    t_total = time.time() - t_inicio
    metadata = {
        "release": "modelo-v6-e3-ablation-temperatura",
        "experimento": (
            "E3 (ablación) — ¿dieron mejores resultados las temperaturas "
            "absolutas (v6/E2) que las categorías de temperatura (estilo v1)?"
        ),
        "pregunta_respondida": (
            "¿absolutas vs categóricas (one-hot) vs categóricas ordinales "
            "para las 4 features de temperatura?"
        ),
        "configuraciones": configs,
        "comparativa": {
            "A_menos_B_onehot": delta_ab,
            "A_menos_C_ordinal": delta_ac,
            "lectura": (
                "Deltas = control (A) − variante. En MAE/RMSE un delta "
                "NEGATIVO significa que las absolutas tienen MENOR error; en R² "
                "un delta POSITIVO significa que las absolutas explican más "
                "varianza."
            ),
        },
        "conclusion": {
            "absolutas_ganan_vs_onehot": bool(absolutas_ganan_onehot),
            "absolutas_ganan_vs_ordinal": bool(absolutas_ganan_ordinal),
            "mae_absolutas": met_a["MAE"],
            "mae_onehot": met_b["MAE"],
            "mae_ordinal": met_c["MAE"],
            "delta_mae_vs_onehot": round(mejor_b, 4),
            "delta_mae_vs_ordinal": round(mejor_c, 4),
            "margen_pct_vs_onehot": round(margen_vs_b, 2),
            "margen_pct_vs_ordinal": round(margen_vs_c, 2),
            "resumen_numerico": (
                f"Control A (absolutas) MAE={met_a['MAE']} / R²={met_a['R2']}; "
                f"B (one-hot) MAE={met_b['MAE']} / R²={met_b['R2']} "
                f"(ΔMAE A−B = {delta_ab['MAE']:+.4f}); "
                f"C (ordinal) MAE={met_c['MAE']} / R²={met_c['R2']} "
                f"(ΔMAE A−C = {delta_ac['MAE']:+.4f})."
            ),
        },
        "control_A_reproduce_E2": {
            "identico": bool(control_ok),
            "esperado": E2_REFERENCIA,
            "obtenido": met_a,
            "n_esperado": met_e2["n"],
        },
        "bins": {
            "limites": ["-inf", -5, 5, 15, 25, "inf"],
            "etiquetas": LABELS,
            "codificacion_ordinal": CODIFICACION_ORDINAL,
            "origen": (
                "Mismos bins que feature_engineering.discretize_temperature "
                "(pd.cut, borde derecho incluido)"
            ),
            "aplicacion": (
                "Se aplican a las 4 features (incluyendo TempMin_Lag_4D y "
                "Region_Media_7d_TempMin) DESPUÉS de calcularlas en continuo "
                "e imputar con mediana de train; la categoría describe el "
                "régimen de temperatura de esa ventana."
            ),
        },
        "configuracion_comun": {
            "target": "Total (nivel, sin transformar)",
            "split": "train = 2024, test = 2025",
            "modelo": "RandomForestRegressor (hiperparámetros del v5/E2)",
            "semilla": v5.RANDOM_STATE,
            "hiperparametros": {
                k: v for k, v in v5.HIPERPARAMETROS.items() if k != "n_jobs"
            },
            "imputado": "mediana de SOLO train (sobre el continuo, antes de categorizar)",
            "features_base_comunes": base_feats + CLIMA_FIJO,
            "features_bajo_test": FEATURES_TEMP,
            "frio_polar_flag_se_mantiene": True,
            "evaluacion": (
                "MAE/RMSE/R²/sesgo% a nivel establecimiento+día sobre test "
                "2025, global y por región (definiciones idénticas a v5/E1/E2)"
            ),
            "etapa_1_v5_identica": info_etapa1["etapa_1_region_identica_a_v5"],
        },
        "distribucion_categorias": {
            etiqueta: {c: int(dist.loc[etiqueta, c]) for c in FEATURES_TEMP}
            for etiqueta in LABELS
        },
        "sanity_categorias": {
            "solo_toman_los_5_valores": True,
            "verificado_con_assert": True,
        },
        "nota_metodologica": (
            "Mismo split que v6 (train 2024 / test 2025), mismos "
            "hiperparámetros y semilla: la comparación es INTERNA de la "
            "sesión sobre un único test, NO una validación externa. Los "
            "deltas miden el efecto de la codificación de temperatura en "
            "este test; no se guardan modelos .joblib porque es un "
            "experimento de evidencia (la metadata basta)."
        ),
        "tiempo_total_script_segundos": round(t_total, 1),
    }
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("✅ ABLACIÓN E3 COMPLETADA")
    print(f"  Metadata: {RUTA_SALIDA}")
    print(f"  Tiempo total: {t_total:.1f} s")
    print("=" * 70)


if __name__ == "__main__":
    main()
