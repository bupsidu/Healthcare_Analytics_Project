"""
Re-entrenamiento del modelo sin data leakage — Sistema MINSAL
=============================================================

Corrige el problema de leakage detectado en el modelo v1:
  - v1 usaba los conteos por rango etario (Menores_1 ... De_65_y_mas) como features.
  - Como Total == suma de esos rangos, el modelo aprendía a SUMAR, no a predecir.
  - Con eso no podía predecir días nuevos (2026), porque esos conteos no se conocen.

Este script re-entrena usando SOLO información climática y de contaminación:
  15 features reales, target = Total.

Réplica fiel de la configuración del notebook 02:
  - Split temporal: train=2024, test=2025
  - RandomForestRegressor: n_estimators=200, max_depth=15,
    min_samples_split=50, min_samples_leaf=20, max_features='sqrt',
    random_state=42
  - Validación cruzada: TimeSeriesSplit(n_splits=5), scoring neg_MAE

Salida:
  - models/model_rf_respiratorio_v2.joblib
  - models/features_v2.json
  - models/model_metadata_v2.json

Autor: Ignacio Fernández (Nafery) - ML Lead
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import LabelEncoder

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
BASE_DIR = Path("/Users/naferyh/Desktop/Proyectos/Proyecto de título")
PROCESSED = BASE_DIR / "data" / "processed" / "df_modelo.parquet"
MODELS_DIR = BASE_DIR / "models"

RANDOM_STATE = 42
TRAIN_YEAR = 2024
TEST_YEAR = 2025

# Features REALES: solo clima y contaminación (SIN rangos etarios)
FEATURE_COLS = [
    # Clima
    "TempMin", "TempMax", "Precipitacion_mm",
    # Contaminación
    "MP2_5", "MP10",
    # Lags biológicos
    "TempMin_Lag_4D", "MP2_5_Lag_2D",
    # Flags binarios
    "Frio_Polar_Flag", "Lluvia_Intensa_Flag", "Alerta_MP25_Flag",
    # Discretización y stats regionales
    "Cat_TempMin_Encoded", "Region_Media_7d_TempMin", "Region_Media_7d_MP25",
    # Codificadas
    "Region_Encoded", "TipoEstablecimiento_Encoded",
]

# Mapeo ordinal de temperatura (idéntico al notebook v1)
TEMP_ORDER = {
    "Muy Frío": 0, "Frío": 1, "Templado": 2, "Cálido": 3, "Caluroso": 4, "None": -1,
}

TARGET = "Total"


def main() -> None:
    print("=" * 60)
    print("RE-ENTRENAMIENTO SIN DATA LEAKAGE (modelo v2)")
    print("=" * 60)

    print("\nCargando dataset procesado...")
    df = pd.read_parquet(PROCESSED)

    # Codificar categóricas (mismos encoders que v1, reentrenados aquí para el split)
    df["Cat_TempMin_Encoded"] = (
        df["Cat_TempMin"].map(TEMP_ORDER).fillna(-1).astype(int)
    )
    le_region = LabelEncoder()
    df["Region_Encoded"] = le_region.fit_transform(df["Region"].astype(str))
    le_tipo = LabelEncoder()
    df["TipoEstablecimiento_Encoded"] = le_tipo.fit_transform(
        df["TipoEstablecimiento"].astype(str)
    )

    # Split temporal
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year

    train_df = df[df["Año"] == TRAIN_YEAR]
    test_df = df[df["Año"] == TEST_YEAR]

    X_train = train_df[FEATURE_COLS]
    y_train = train_df[TARGET]
    X_test = test_df[FEATURE_COLS]
    y_test = test_df[TARGET]

    print(f"\n📊 División temporal:")
    print(f"  Train ({TRAIN_YEAR}): {len(train_df):,} filas")
    print(f"  Test  ({TEST_YEAR}): {len(test_df):,} filas")
    print(f"  Features: {len(FEATURE_COLS)} (rangos etarios EXCLUIDOS)")
    print(f"  Target: {TARGET} (mean={y_train.mean():.1f}, std={y_train.std():.1f})")

    # Entrenar Random Forest (misma config que v1)
    print("\n--- Entrenando Random Forest Regressor ---")
    model = RandomForestRegressor(
        n_estimators=200,
        max_depth=15,
        min_samples_split=50,
        min_samples_leaf=20,
        max_features="sqrt",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2 = r2_score(y_test, y_pred)

    print(f"\n📊 Resultados (test {TEST_YEAR}):")
    print(f"  MAE:  {mae:.3f}")
    print(f"  RMSE: {rmse:.3f}")
    print(f"  R²:   {r2:.4f}")

    # Validación cruzada temporal
    print("\n--- Validación Cruzada Temporal (5-fold) ---")
    tscv = TimeSeriesSplit(n_splits=5)
    cv_scores = cross_val_score(
        model, X_train, y_train,
        cv=tscv,
        scoring="neg_mean_absolute_error",
        n_jobs=-1,
    )
    cv_mae = -cv_scores
    print(f"  MAE promedio: {cv_mae.mean():.3f} ± {cv_mae.std():.3f}")
    print(f"  Fold scores: {cv_mae.round(3).tolist()}")

    # Importancia de features
    print("\n📊 Top 10 features por importancia:")
    imp = pd.DataFrame({
        "feature": FEATURE_COLS,
        "importance": model.feature_importances_,
    }).sort_values("importance", ascending=False)
    for _, row in imp.head(10).iterrows():
        print(f"  {row['feature']:<30} {row['importance']:.4f}")

    # Exportar artefactos
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    model_path = MODELS_DIR / "model_rf_respiratorio_v2.joblib"
    features_path = MODELS_DIR / "features_v2.json"
    metadata_path = MODELS_DIR / "model_metadata_v2.json"

    joblib.dump(model, model_path)
    with open(features_path, "w", encoding="utf-8") as f:
        json.dump(FEATURE_COLS, f, ensure_ascii=False, indent=2)

    metadata = {
        "release": "modelo-v2",
        "model_type": "RandomForestRegressor",
        "target": TARGET,
        "features": FEATURE_COLS,
        "n_features": len(FEATURE_COLS),
        "train_year": TRAIN_YEAR,
        "test_year": TEST_YEAR,
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "metrics": {
            "MAE": round(float(mae), 4),
            "RMSE": round(rmse, 4),
            "R2": round(float(r2), 4),
            "CV_MAE_mean": round(float(cv_mae.mean()), 4),
            "CV_MAE_std": round(float(cv_mae.std()), 4),
        },
        "hyperparameters": {
            "n_estimators": 200,
            "max_depth": 15,
            "min_samples_split": 50,
            "min_samples_leaf": 20,
            "max_features": "sqrt",
            "random_state": RANDOM_STATE,
        },
        "leakage_fix": (
            "v2 excluye los conteos por rango etario (Menores_1 ... De_65_y_mas) "
            "porque Total == suma de esos rangos, lo que causaba data leakage en v1. "
            "v2 predice solo con clima y contaminación."
        ),
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("✅ RE-ENTRENAMIENTO COMPLETADO (modelo v2)")
    print(f"  Modelo:   {model_path}")
    print(f"  Features: {features_path}")
    print(f"  Metadata: {metadata_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
