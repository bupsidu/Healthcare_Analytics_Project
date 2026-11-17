"""
v9 — v8 + PATRÓN SEMANAL (interacción día-de-semana × tipo de establecimiento)
==============================================================================

Diagnóstico que motiva v9
-------------------------
v8 logra MAE 8.009 / R2 0.7648, pero un análisis de la estructura del error
reveló una señal que el modelo NO usa: el día de la semana.

Evidencia (test 2025, nivel establecimiento-día):

    día      demanda normalizada      perfil Hospital    perfil SAPU
    Lun            1.120                   1.18               1.07
    Mar            1.048                   1.10               1.01
    Mié            0.966                   1.01               0.92
    Jue            0.915                   0.98               0.86
    Vie            0.872                   0.94               0.81
    Sáb            0.998                   0.86               1.10
    Dom            1.080                   0.92               1.21

    Hospital: pega el LUNES y cae el SÁBADO (max/min = 1.38x)
    SAPU:     cae el VIERNES y pega el DOMINGO (max/min = 1.49x)
    → perfiles OPUESTOS: sin `dow`, el modelo promedia ambos y pierde la señal.

Los perfiles son ESTABLES entre años (correlación 2024 vs 2025):
    global 0.981 | Hospital 0.991 | SAPU 0.987 | SAR 0.963 | SUR 0.985
Esa estabilidad interanual es lo que hace legítimo usar el día de semana como
feature (no es un patrón idiosincrático de un año).

Qué agrega v9
-------------
  1. `DOW`             día de la semana (0=lunes .. 6=domingo), numérico.
  2. `DOW_Sin`/`DOW_Cos` codificación cíclica (domingo y lunes son contiguos;
                        evita que el árbol parta el ciclo a la mitad).
  3. `Es_Finde`        1 si sábado o domingo.
  4. `DOW_Esperado`    demanda esperada del establecimiento para ese día de la
                        semana, derivada del **perfil de TRAIN 2024**:
                        media(estab, dow) del train, con fallback jerárquico a
                        media(estab) → media(tipo, dow) → media global.
                        ANTI-LEAKAGE: constante calculada SOLO con 2024.

`DOW_Esperado` es la feature de mayor valor esperado: le da al árbol el nivel
esperado para ESE día en ESE establecimiento, que es exactamente lo que el
error semanal revelaba que faltaba.

Todo lo demás es idéntico a v8 (mismas features base, hiperparámetros, split),
así que la comparación aísla el aporte del calendario semanal.

Artefactos (models/):
  - model_rf_directo_v9.joblib
  - model_metadata_v9.json
v8 queda intacto.

Uso:
    python3 src/pipelines/reentrenar_modelo_v9_calendario.py
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
RUTA_MODELO_OUT = BASE_DIR / "models" / "model_rf_directo_v9.joblib"
RUTA_SALIDA = BASE_DIR / "models" / "model_metadata_v9.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reentrenar_modelo_v8_tendencia as v8  # noqa: E402
import reentrenar_modelo_v7_features_fix as v7  # noqa: E402
import reentrenar_modelo_v5_trailing as v5  # noqa: E402

TARGET = v7.TARGET

FEATURES_CALENDARIO = ["DOW", "DOW_Sin", "DOW_Cos", "Es_Finde", "DOW_Esperado"]


def construir_dow_esperado(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, dict]:
    """Demanda esperada por (establecimiento, día de semana) usando SOLO train.

    Fallback jerárquico (de más a menos específico):
      1. media(estab, dow) sobre train 2024
      2. media(estab) sobre train 2024            (estab sin ese dow)
      3. media(tipo, dow) sobre train 2024        (estab ausente en train)
      4. media(tipo) sobre train 2024
      5. media global de train 2024

    ANTI-LEAKAGE: todas las medias provienen exclusivamente de train 2024; el
    valor se aplica como constante a las filas de test.
    """
    tr = train.copy()
    tr["dow"] = tr["Fecha"].dt.dayofweek

    m_est_dow = tr.groupby(["IdEstablecimiento", "dow"])[TARGET].mean()
    m_est = tr.groupby("IdEstablecimiento")[TARGET].mean()
    m_tipo_dow = tr.groupby(["TipoEstablecimiento", "dow"])[TARGET].mean()
    m_tipo = tr.groupby("TipoEstablecimiento")[TARGET].mean()
    m_global = float(tr[TARGET].mean())

    def aplicar(df: pd.DataFrame) -> pd.Series:
        idx = pd.MultiIndex.from_arrays([df["IdEstablecimiento"], df["dow"]])
        vals = pd.Series(
            m_est_dow.reindex(idx).to_numpy(), index=df.index, dtype=float
        )
        faltan = vals.isna()
        if faltan.any():
            sub = df[faltan]
            v = sub["IdEstablecimiento"].map(m_est).astype(float)
            f2 = v.isna()
            if f2.any():
                idx2 = pd.MultiIndex.from_arrays(
                    [sub.loc[f2, "TipoEstablecimiento"], sub.loc[f2, "dow"]]
                )
                v2 = pd.Series(
                    m_tipo_dow.reindex(idx2).to_numpy(), index=sub.loc[f2].index,
                    dtype=float,
                )
                f3 = v2.isna()
                if f3.any():
                    v3 = sub.loc[f3, "TipoEstablecimiento"].map(m_tipo).astype(float)
                    v2.loc[f3] = v3.fillna(m_global)
                v.loc[f2] = v2
            vals.loc[faltan] = v
        return vals

    tr["dow"] = train["Fecha"].dt.dayofweek
    te = test.copy()
    te["dow"] = te["Fecha"].dt.dayofweek

    info = {
        "nivel_estab_dow_usado": int(m_est_dow.reindex(
            pd.MultiIndex.from_arrays([te["IdEstablecimiento"], te["dow"]])
        ).notna().sum()),
        "filas_test": len(te),
    }
    return aplicar(tr), aplicar(te), info


def agregar_calendario(df: pd.DataFrame, dow_esperado: pd.Series) -> pd.DataFrame:
    df = df.copy()
    dow = df["Fecha"].dt.dayofweek
    df["DOW"] = dow
    df["DOW_Sin"] = np.sin(2 * np.pi * dow / 7.0)
    df["DOW_Cos"] = np.cos(2 * np.pi * dow / 7.0)
    df["Es_Finde"] = (dow >= 5).astype(int)
    df["DOW_Esperado"] = dow_esperado.to_numpy()
    return df


def main() -> None:
    t0 = time.time()
    print("=" * 74)
    print("v9 — v8 + PATRÓN SEMANAL (dow × tipo de establecimiento)")
    print("=" * 74)

    df = pd.read_parquet(RUTA_DATOS)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year
    train_raw = df[df["Año"] == v5.TRAIN_YEAR].copy()
    test_raw = df[df["Año"] == v5.TEST_YEAR].copy()
    panel = v7.cargar_panel(df)
    print(f"  Panel estab+fecha: {len(panel):,}")

    # --- Etapa 1 (idéntica a v8) -----------------------------------------
    print("\n--- Etapa 1 (v5, importada): Pred_Region ---")
    region_train, region_test, dummies_cols, _ = v5.preparar_features_region(
        df, ventana=v5.VENTANA_PRINCIPAL,
    )
    features_region = v5.construir_lista_features(dummies_cols, "trailing")
    res1 = v5.entrenar_etapa_1(region_train, region_test, features_region, con_cv=False)
    region_train["Pred_Region"] = res1["model"].predict(region_train[features_region])
    region_test["Pred_Region"] = res1["y_pred"]
    print(f"  Región (test 2025): MAE={res1['met_region']['MAE']:.3f} "
          f"R2={res1['met_region']['R2']:.4f}")

    # --- Total_Lag_4 + Share_Trailing (idéntico a v8) --------------------
    print("\n--- Total_Lag_4 + Share_Trailing ---")
    lag_cal = v7.calcular_total_lag_calendario(panel)
    share_2024, n_nuevos = e1_share(test_raw, train_raw)
    share_grid = v7.calcular_share_trailing_grilla(panel, share_2024)

    # --- Tendencia regional (idéntico a v8) ------------------------------
    print("\n--- Tendencia regional (v8) ---")
    media_train_region = (
        train_raw.groupby("Region")[TARGET].sum()
        / train_raw.groupby("Region")["Fecha"].nunique()
    )
    reg_feats, estab_feats = v8.calcular_features_tendencia(panel, media_train_region)

    # --- Ensamblado ------------------------------------------------------
    print("\n--- Ensamblado ---")
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

    # --- NUEVO v9: calendario semanal ------------------------------------
    print("\n--- NUEVO v9: patrón semanal ---")
    dtr, dte, info_dow = construir_dow_esperado(direct_train, direct_test)
    direct_train = agregar_calendario(direct_train, dtr)
    direct_test = agregar_calendario(direct_test, dte)
    print(f"  DOW_Esperado resuelto a nivel (estab, dow) en "
          f"{info_dow['nivel_estab_dow_usado']:,}/{info_dow['filas_test']:,} filas de test")

    direct_train, direct_test, dummies_tipo = v7.codificar_onehot(
        direct_train, direct_test, "TipoEstablecimiento", "Tipo"
    )
    direct_train, direct_test, dummies_region = v7.codificar_onehot(
        direct_train, direct_test, "Region", "Region"
    )

    nuevas_v8 = [
        "Region_Total_Lag_4", "Region_Media_28d_lag4",
        "Region_Trend_Ratio", "Region_Level_vs_Train", "Estab_Media_28d_lag4",
    ]
    core = ["Total_Lag_4", "Share_Trailing", "Pred_Region", "Pred_E1"]
    feature_cols = (
        core + nuevas_v8 + FEATURES_CALENDARIO
        + dummies_tipo + dummies_region
        + v7.FEATURES_ESTACIONALIDAD + v7.COLUMNAS_CLIMA_DIRECTO
    )
    print(f"  Features finales ({len(feature_cols)}; v8 tenía "
          f"{len(feature_cols) - len(FEATURES_CALENDARIO)})")

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
    corrs = {}
    for f in FEATURES_CALENDARIO:
        c = float(direct_train[f].corr(direct_train[TARGET]))
        corrs[f] = round(c, 4)
        print(f"  {f:16} corr(train, target)={c:+.3f}")
        assert abs(c) < 0.995, f"{f} sospechosa de fuga: {c}"
    print(f"  DOW_Esperado usa SOLO medias de train 2024 (anti-leakage OK)")

    # --- Entrenamiento ---------------------------------------------------
    print("\n" + "-" * 70)
    print("ENTRENAMIENTO — RandomForest v9")
    print("-" * 70)
    X_tr, y_tr = direct_train[feature_cols], direct_train[TARGET]
    X_te, y_te = direct_test[feature_cols], direct_test[TARGET]
    print(f"  Train: {len(X_tr):,} | Test: {len(X_te):,} | {len(feature_cols)} features")

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

    eval_df = direct_test[["IdEstablecimiento", "Region", "Fecha", TARGET]].copy()
    eval_df["pred"] = y_pred
    eval_df["dow"] = eval_df["Fecha"].dt.dayofweek
    met_region = {
        r: v7.metricas(g[TARGET].to_numpy(float), g["pred"].to_numpy(float))
        for r, g in eval_df.groupby("Region")
    }

    # --- Comparativas ----------------------------------------------------
    meta_v8 = json.loads((BASE_DIR / "models" / "model_metadata_v8.json").read_text())
    ref8 = meta_v8["metricas_establecimiento"]
    ref8_reg = meta_v8["metricas_por_region"]

    print("\n=== MAE POR DÍA DE LA SEMANA: v8 → v9 ===")
    nombres = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    mae_dow = {}
    for d in range(7):
        g = eval_df[eval_df["dow"] == d]
        mae_dow[nombres[d]] = v7.metricas(
            g[TARGET].to_numpy(float), g["pred"].to_numpy(float)
        )
        print(f"  {nombres[d]}: MAE {mae_dow[nombres[d]]['MAE']:>6.3f} "
              f"(n={mae_dow[nombres[d]]['n']:,})")

    print("\n=== SESGO POR REGIÓN: v8 → v9 ===")
    print(f"  {'Región':<22} {'v8 sesgo':>9} {'v9 sesgo':>9} {'Δ pp':>7} {'v8 R2':>7} {'v9 R2':>7}")
    filas = []
    for r in sorted(met_region):
        s8 = ref8_reg[r]["sesgo_pct"]; s9 = met_region[r]["sesgo_pct"]
        filas.append((r, s8, s9))
        print(f"  {r:<22} {s8:>+8.1f}% {s9:>+8.1f}% {s9 - s8:>+7.1f} "
              f"{ref8_reg[r]['R2']:>7.3f} {met_region[r]['R2']:>7.3f}")
    mejoras = [abs(a) - abs(b) for _, a, b in filas]
    print(f"\n  Reducción media |sesgo|: {np.mean(mejoras):+.2f} pp | "
          f"regiones que mejoran: {sum(1 for m in mejoras if m > 0)}/{len(mejoras)}")

    print("\n=== TABLA COMPARATIVA ===")
    comp = pd.DataFrame([
        {"versión": "v8", **{k: ref8[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct"]}},
        {"versión": "v9 (+ calendario)", **{k: met[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct"]}},
    ])
    print(comp.round(4).to_string(index=False))

    imp = pd.DataFrame({"feature": feature_cols,
                        "importance": model.feature_importances_}) \
        .sort_values("importance", ascending=False)
    print("\nTop 12 features:")
    for _, row in imp.head(12).iterrows():
        marca = " ←NUEVA" if row["feature"] in FEATURES_CALENDARIO else ""
        print(f"  {row['feature']:<28} {row['importance']:.4f}{marca}")

    # --- Exportar --------------------------------------------------------
    joblib.dump(model, RUTA_MODELO_OUT)
    t_total = time.time() - t0
    metadata = {
        "release": "modelo-v9-calendario",
        "experimento": (
            "v9 — v8 + patrón semanal (día de semana × tipo de establecimiento)"
        ),
        "descripcion": (
            "v8 no usaba el día de la semana. La evidencia muestra un patrón "
            "fuerte y estable: perfil semanal correlaciona 0.981 entre 2024 y "
            "2025 (Hospital 0.991, SAPU 0.987, SAR 0.963, SUR 0.985), y los "
            "perfiles de Hospital y SAPU son OPUESTOS (Hospital pega el lunes "
            "1.18 y cae el sábado 0.86; SAPU cae el viernes 0.81 y pega el "
            "domingo 1.21). v9 agrega DOW, DOW_Sin/Cos, Es_Finde y "
            "DOW_Esperado (media estab×dow de TRAIN 2024 con fallback "
            "jerárquico)."
        ),
        "justificacion_diagnostica": {
            "correlacion_perfil_semanal_2024_vs_2025": 0.981,
            "correlacion_por_tipo": {
                "Hospital": 0.991, "SAPU": 0.987, "SAR": 0.963, "SUR": 0.985,
            },
            "ratio_max_min_demanda_semanal": {
                "global": 1.28, "Hospital": 1.38, "SAPU": 1.49,
            },
            "contraste_hospital_sapu": (
                "Hospital: lun 1.18 / sáb 0.86 (max/min 1.38x). "
                "SAPU: vie 0.81 / dom 1.21 (max/min 1.49x). Perfiles opuestos: "
                "sin DOW el modelo promedia y pierde la señal."
            ),
            "contribucion_error_por_region_v8": (
                "Metropolitana concentra 28.2% del error absoluto total "
                "(MAE 9.39 × 54.326 filas), Biobío 12.2%, Valparaíso 9.6%."
            ),
        },
        "features_nuevas": {
            "DOW": "día de la semana 0..6",
            "DOW_Sin": "sen(2π·dow/7)",
            "DOW_Cos": "cos(2π·dow/7)",
            "Es_Finde": "1 si sábado o domingo",
            "DOW_Esperado": "media(estab, dow) de TRAIN 2024 con fallback estab → tipo×dow → tipo → global",
        },
        "anti_leakage": {
            "dow_esperado_usa_solo_train_2024": True,
            "fallback_jerarquico": [
                "media(estab, dow)", "media(estab)", "media(tipo, dow)",
                "media(tipo)", "media global",
            ],
            "filas_test_resueltas_a_nivel_estab_dow": info_dow["nivel_estab_dow_usado"],
            "filas_test": info_dow["filas_test"],
            "correlaciones_train": corrs,
            "verificacion": verif,
        },
        "features_totales": feature_cols,
        "n_features": len(feature_cols),
        "n_features_v8": len(feature_cols) - len(FEATURES_CALENDARIO),
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
        "metricas_por_dia_semana": mae_dow,
        "sesgo_por_region_vs_v8": {
            r: {"v8": ref8_reg[r]["sesgo_pct"], "v9": met_region[r]["sesgo_pct"],
                "delta_pp": round(met_region[r]["sesgo_pct"]
                                  - ref8_reg[r]["sesgo_pct"], 2)}
            for r in met_region
        },
        "comparativa": {
            "v8": {k: ref8[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct", "n"]},
            "v9": met,
        },
        "importancia_features": imp.head(20).to_dict("records"),
        "sanity_check": {"r2_mayor_a_0_9_sospechoso": fuga, "r2_observado": met["R2"]},
        "tiempo_entrenamiento_segundos": round(t_ent, 1),
        "tiempo_total_segundos": round(t_total, 1),
        "limitaciones": [
            "Sigue siendo un split de 2 años: el patrón semanal se valida en "
            "2025, pero no se puede probar estabilidad más allá de dos años.",
            "DOW_Esperado es una media histórica: no captura cambios en el "
            "calendario de dotación (turnos, feriados irregulares).",
            "Los feriados chilenos no se modelan explícitamente; aparecen como "
            "días con demanda atípica que ninguna feature marca.",
        ],
    }
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 74)
    print("✅ v9 COMPLETADO")
    print(f"  Modelo:   {RUTA_MODELO_OUT.name}")
    print(f"  Metadata: {RUTA_SALIDA.name}")
    print(f"  Tiempo total: {t_total:.1f} s")
    print("=" * 74)


def e1_share(test_raw, train_raw):
    """Wrapper para no ensuciar el namespace del main."""
    import reentrenar_modelo_v6_e1_trailing as e1
    return e1.calcular_share_2024_con_fallback(test_raw, train_raw)


if __name__ == "__main__":
    main()
