"""
v10 — v9 + CALENDARIO DE FERIADOS CHILENOS
==========================================

Diagnóstico que motiva v10
--------------------------
v9 (con patrón semanal) logra MAE 7.236 / R2 0.8066. Pero el calendario
semanal no cubre los feriados, y la evidencia muestra que son una fuente de
error sistemática y ESTABLE entre años:

    Año    media feriado   media no-feriado   ratio
    2024       32.51            29.38         1.106
    2025       30.49            27.13         1.124

Los feriados mueven la demanda +11-12%, y varios de los días de mayor demanda
relativa del año son feriados (21-may rel=1.62, 15-ago rel=1.46, 20-jun
rel=1.40). Como el ratio es casi idéntico en ambos años, es una señal
estructural y no un artefacto.

El problema para el modelo es doble:
  1. Un feriado que cae lunes se comporta distinto de un lunes normal, y el
     árbol no tiene cómo saberlo.
  2. El "efecto feriado" se arrastra a los días contiguos (víspera y día
     siguiente), no solo al feriado mismo.

Qué agrega v10 (todas calculadas con el calendario, sin target)
--------------------------------------------------------------
  1. `Es_Feriado`        1 si la fecha es feriado nacional.
  2. `Es_Feriado_Largo`  1 si el feriado cae lunes o viernes (fin de semana
                          largo, el patrón de viaje cambia).
  3. `Dias_Al_Feriado`   distancia en días (±) al feriado más cercano, clip
                          a [-7, 7]. Captura víspera y resaca.
  4. `Feriado_Irrumpido` 1 si la fecha es un día hábil entre feriados/fines de
                          semana (los llamados "sandwich").

NOTA de honestidad metodológica: el calendario de feriados es información
pública conocida de antemano (no es el target ni se deriva de él), así que no
hay leakage. Se declara explícitamente en el código para que la tesis sea
auditable y reproducible sin dependencias externas.

Todo lo demás es idéntico a v9: la comparación aísla el aporte del calendario
de feriados.

Artefactos (models/):
  - model_rf_directo_v10.joblib
  - model_metadata_v10.json
v9 queda intacto.

Uso:
    python3 src/pipelines/reentrenar_modelo_v10_feriados.py
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
RUTA_MODELO_OUT = BASE_DIR / "models" / "model_rf_directo_v10.joblib"
RUTA_SALIDA = BASE_DIR / "models" / "model_metadata_v10.json"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reentrenar_modelo_v8_tendencia as v8  # noqa: E402
import reentrenar_modelo_v9_calendario as v9  # noqa: E402
import reentrenar_modelo_v7_features_fix as v7  # noqa: E402
import reentrenar_modelo_v5_trailing as v5  # noqa: E402

TARGET = v7.TARGET

# ---------------------------------------------------------------------------
# Calendario de feriados nacionales de Chile, 2024–2025.
#
# Fuente: Ley 19.973 y Ley 20.215 (feriados legales). Incluye los móviles
# relevantes (Viernes y Sábado Santo) y excluye los feriados regionales
# (p.ej. 20 de septiembre en Coquimbo, 21 de mayo en Iquique) porque el
# dataset no distingue su aplicación por comuna.
#
# Es información pública conocida de antemano: no es leakage.
# ---------------------------------------------------------------------------
FERIADOS_CHILE: dict[int, list[str]] = {
    2024: [
        "2024-01-01",  # Año Nuevo
        "2024-03-29",  # Viernes Santo
        "2024-03-30",  # Sábado Santo
        "2024-05-01",  # Día del Trabajo
        "2024-05-21",  # Día de las Glorias Navales
        "2024-06-20",  # Día Nacional de los Pueblos Indígenas
        "2024-06-29",  # San Pedro y San Pablo
        "2024-07-16",  # Virgen del Carmen
        "2024-08-15",  # Asunción de la Virgen
        "2024-09-18",  # Independencia Nacional
        "2024-09-19",  # Glorias del Ejército
        "2024-09-20",  # Feriado adicional (ley 20.215)
        "2024-10-12",  # Encuentro de Dos Mundos
        "2024-10-31",  # Día de las Iglesias Evangélicas
        "2024-11-01",  # Todos los Santos
        "2024-11-02",  # Feriado adicional (ley 20.215)
        "2024-12-08",  # Inmaculada Concepción
        "2024-12-25",  # Navidad
    ],
    2025: [
        "2025-01-01",  # Año Nuevo
        "2025-04-18",  # Viernes Santo
        "2025-04-19",  # Sábado Santo
        "2025-05-01",  # Día del Trabajo
        "2025-05-21",  # Día de las Glorias Navales
        "2025-06-20",  # Día Nacional de los Pueblos Indígenas
        "2025-06-29",  # San Pedro y San Pablo
        "2025-07-16",  # Virgen del Carmen
        "2025-08-15",  # Asunción de la Virgen
        "2025-09-18",  # Independencia Nacional
        "2025-09-19",  # Glorias del Ejército
        "2025-10-12",  # Encuentro de Dos Mundos
        "2025-10-31",  # Día de las Iglesias Evangélicas
        "2025-11-01",  # Todos los Santos
        "2025-11-02",  # Feriado adicional (ley 20.215)
        "2025-12-08",  # Inmaculada Concepción
        "2025-12-25",  # Navidad
    ],
}

FEATURES_FERIADOS = [
    "Es_Feriado", "Es_Feriado_Largo", "Dias_Al_Feriado", "Feriado_Irrumpido",
]


def construir_calendario_feriados(fechas: pd.Series) -> pd.DataFrame:
    """Features de feriado para un conjunto de fechas (sin usar el target).

    - Es_Feriado:        la fecha es feriado nacional.
    - Es_Feriado_Largo:  feriado que cae lunes o viernes (fin de semana largo).
    - Dias_Al_Feriado:   distancia con signo al feriado más cercano, clip ±7.
    - Feriado_Irrumpido: día hábil con un feriado a ≤2 días (puente/sándwich).
    """
    festivos = set()
    for lst in FERIADOS_CHILE.values():
        festivos.update(pd.Timestamp(x).normalize() for x in lst)
    festivos = sorted(festivos)
    festivos_idx = np.array(
        [pd.Timestamp(f_).to_datetime64() for f_ in festivos]
    ).astype("datetime64[D]").astype("int64")

    f = pd.to_datetime(pd.Series(fechas)).dt.normalize()
    # Días desde epoch para comparaciones y distancias (evita la ambigüedad de
    # DatetimeIndex sobre enteros: interpreta nanosegundos, no días).
    vals = f.to_numpy().astype("datetime64[D]").astype("int64")
    dow = pd.DatetimeIndex(f).dayofweek.to_numpy()

    es_fer = np.isin(vals, festivos_idx)
    es_largo = es_fer & np.isin(dow, [0, 4])

    # Distancia en días al feriado más cercano (con signo).
    pos = np.searchsorted(festivos_idx, vals)
    prev = np.clip(pos - 1, 0, len(festivos_idx) - 1)
    nxt = np.clip(pos, 0, len(festivos_idx) - 1)
    d_prev = vals - festivos_idx[prev]
    d_next = festivos_idx[nxt] - vals
    dist = np.where(np.abs(d_next) <= np.abs(d_prev), d_next, -np.abs(d_prev))
    dist = np.clip(dist, -7, 7)

    irrumpido = (~es_fer) & (np.abs(dist) <= 2) & np.isin(dow, [0, 1, 2, 3, 4])

    return pd.DataFrame({
        "Es_Feriado": es_fer.astype(int),
        "Es_Feriado_Largo": es_largo.astype(int),
        "Dias_Al_Feriado": dist,
        "Feriado_Irrumpido": irrumpido.astype(int),
    }, index=fechas.index if hasattr(fechas, "index") else None)


def main() -> None:
    t0 = time.time()
    print("=" * 74)
    print("v10 — v9 + CALENDARIO DE FERIADOS CHILENOS")
    print("=" * 74)

    df = pd.read_parquet(RUTA_DATOS)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year
    train_raw = df[df["Año"] == v5.TRAIN_YEAR].copy()
    test_raw = df[df["Año"] == v5.TEST_YEAR].copy()
    panel = v7.cargar_panel(df)
    print(f"  Panel estab+fecha: {len(panel):,}")

    print("\n--- Etapa 1 (v5): Pred_Region ---")
    region_train, region_test, dummies_cols, _ = v5.preparar_features_region(
        df, ventana=v5.VENTANA_PRINCIPAL,
    )
    features_region = v5.construir_lista_features(dummies_cols, "trailing")
    res1 = v5.entrenar_etapa_1(region_train, region_test, features_region, con_cv=False)
    region_train["Pred_Region"] = res1["model"].predict(region_train[features_region])
    region_test["Pred_Region"] = res1["y_pred"]
    print(f"  Región (test 2025): MAE={res1['met_region']['MAE']:.3f} "
          f"R2={res1['met_region']['R2']:.4f}")

    print("\n--- Total_Lag_4 + Share_Trailing ---")
    lag_cal = v7.calcular_total_lag_calendario(panel)
    import reentrenar_modelo_v6_e1_trailing as e1
    share_2024, _ = e1.calcular_share_2024_con_fallback(test_raw, train_raw)
    share_grid = v7.calcular_share_trailing_grilla(panel, share_2024)

    print("\n--- Tendencia regional (v8) ---")
    media_train_region = (
        train_raw.groupby("Region")[TARGET].sum()
        / train_raw.groupby("Region")["Fecha"].nunique()
    )
    reg_feats, estab_feats = v8.calcular_features_tendencia(panel, media_train_region)

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

    print("\n--- Patrón semanal (v9) ---")
    dtr, dte, info_dow = v9.construir_dow_esperado(direct_train, direct_test)
    direct_train = v9.agregar_calendario(direct_train, dtr)
    direct_test = v9.agregar_calendario(direct_test, dte)

    print("\n--- NUEVO v10: calendario de feriados ---")
    fer_tr = construir_calendario_feriados(direct_train["Fecha"])
    fer_te = construir_calendario_feriados(direct_test["Fecha"])
    for c in FEATURES_FERIADOS:
        direct_train[c] = fer_tr[c].to_numpy()
        direct_test[c] = fer_te[c].to_numpy()
    print(f"  Feriados en train: {int(direct_train['Es_Feriado'].sum()):,} filas "
          f"({direct_train['Es_Feriado'].mean()*100:.1f}%) | "
          f"en test: {int(direct_test['Es_Feriado'].sum()):,} "
          f"({direct_test['Es_Feriado'].mean()*100:.1f}%)")

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
        core + nuevas_v8 + v9.FEATURES_CALENDARIO + FEATURES_FERIADOS
        + dummies_tipo + dummies_region
        + v7.FEATURES_ESTACIONALIDAD + v7.COLUMNAS_CLIMA_DIRECTO
    )
    print(f"  Features finales ({len(feature_cols)}; v9 tenía "
          f"{len(feature_cols) - len(FEATURES_FERIADOS)})")

    for c in feature_cols:
        if direct_train[c].isna().any():
            mediana = direct_train[c].median()
            direct_train[c] = direct_train[c].fillna(mediana)
            direct_test[c] = direct_test[c].fillna(mediana)

    print("\n" + "-" * 70)
    print("VERIFICACIÓN ANTI-LEAKAGE")
    print("-" * 70)
    verif = v7.verificar_anti_leakage(direct_train, direct_test, feature_cols)
    corrs = {}
    for f in FEATURES_FERIADOS:
        c = float(direct_train[f].corr(direct_train[TARGET]))
        corrs[f] = round(c, 4)
        print(f"  {f:20} corr(train, target)={c:+.3f}")
        assert abs(c) < 0.995, f"{f} sospechosa de fuga: {c}"
    print("  Feriados: calendario público conocido de antemano (no es leakage).")

    print("\n" + "-" * 70)
    print("ENTRENAMIENTO — RandomForest v10")
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
    eval_df["es_fer"] = direct_test["Es_Feriado"].to_numpy()
    eval_df["dow"] = eval_df["Fecha"].dt.dayofweek

    met_region = {
        r: v7.metricas(g[TARGET].to_numpy(float), g["pred"].to_numpy(float))
        for r, g in eval_df.groupby("Region")
    }

    # MAE separado feriado / no feriado: la prueba directa del aporte.
    print("\n=== MAE FERIADO vs NO FERIADO (test 2025) ===")
    met_fer = {}
    for etiqueta, mask in [("Feriado", eval_df["es_fer"] == 1),
                           ("No feriado", eval_df["es_fer"] == 0)]:
        g = eval_df[mask]
        if len(g) == 0:
            continue
        met_fer[etiqueta] = v7.metricas(g[TARGET].to_numpy(float),
                                        g["pred"].to_numpy(float))
        print(f"  {etiqueta:12} MAE {met_fer[etiqueta]['MAE']:>6.3f} "
              f"sesgo {met_fer[etiqueta]['sesgo_pct']:>+6.2f}% "
              f"(n={met_fer[etiqueta]['n']:,})")

    print("\n=== MAE POR DÍA DE LA SEMANA ===")
    nombres = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    mae_dow = {}
    for d in range(7):
        g = eval_df[eval_df["dow"] == d]
        mae_dow[nombres[d]] = v7.metricas(g[TARGET].to_numpy(float),
                                          g["pred"].to_numpy(float))
        print(f"  {nombres[d]}: MAE {mae_dow[nombres[d]]['MAE']:>6.3f} "
              f"(n={mae_dow[nombres[d]]['n']:,})")

    meta_v9 = json.loads((BASE_DIR / "models" / "model_metadata_v9.json").read_text())
    ref9 = meta_v9["metricas_establecimiento"]
    ref9_reg = meta_v9["metricas_por_region"]

    print("\n=== SESGO POR REGIÓN: v9 → v10 ===")
    print(f"  {'Región':<22} {'v9 sesgo':>9} {'v10 sesgo':>9} {'Δ pp':>7} {'v9 R2':>7} {'v10 R2':>7}")
    filas = []
    for r in sorted(met_region):
        s9 = ref9_reg[r]["sesgo_pct"]; s10 = met_region[r]["sesgo_pct"]
        filas.append((r, s9, s10))
        print(f"  {r:<22} {s9:>+8.1f}% {s10:>+8.1f}% {s10 - s9:>+7.1f} "
              f"{ref9_reg[r]['R2']:>7.3f} {met_region[r]['R2']:>7.3f}")
    mejoras = [abs(a) - abs(b) for _, a, b in filas]
    r2_up = sum(1 for r in met_region if met_region[r]["R2"] > ref9_reg[r]["R2"])
    print(f"\n  Reducción media |sesgo|: {np.mean(mejoras):+.2f} pp | "
          f"regiones que mejoran sesgo: {sum(1 for m in mejoras if m > 0)}/{len(mejoras)} | "
          f"R2 mejora en {r2_up}/{len(met_region)}")

    print("\n=== TABLA COMPARATIVA ===")
    comp = pd.DataFrame([
        {"versión": "v9", **{k: ref9[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct"]}},
        {"versión": "v10 (+ feriados)", **{k: met[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct"]}},
    ])
    print(comp.round(4).to_string(index=False))

    imp = pd.DataFrame({"feature": feature_cols,
                        "importance": model.feature_importances_}) \
        .sort_values("importance", ascending=False)
    print("\nTop 14 features:")
    for _, row in imp.head(14).iterrows():
        marca = " ←NUEVA" if row["feature"] in FEATURES_FERIADOS else ""
        print(f"  {row['feature']:<28} {row['importance']:.4f}{marca}")

    joblib.dump(model, RUTA_MODELO_OUT)
    t_total = time.time() - t0
    metadata = {
        "release": "modelo-v10-feriados",
        "experimento": "v10 — v9 + calendario de feriados nacionales de Chile",
        "descripcion": (
            "Los feriados mueven la demanda +11-12% de forma estable entre años "
            "(2024 ratio 1.106, 2025 ratio 1.124) y varios de los días de mayor "
            "demanda relativa del año son feriados. v9 no los modelaba: un "
            "feriado que cae lunes se trataba como lunes normal. v10 agrega "
            "Es_Feriado, Es_Feriado_Largo, Dias_Al_Feriado (víspera/resaca) y "
            "Feriado_Irrumpido (puentes)."
        ),
        "justificacion_diagnostica": {
            "ratio_demanda_feriado_vs_no_feriado": {"2024": 1.106, "2025": 1.124},
            "dias_top_demanda_relativa_2025": {
                "2025-05-21": {"rel": 1.62, "feriado": True},
                "2025-08-15": {"rel": 1.46, "feriado": True},
                "2025-06-20": {"rel": 1.40, "feriado": True},
            },
        },
        "fuente_calendario": (
            "Ley 19.973 y Ley 20.215. Feriados nacionales declarados en el "
            "módulo, sin dependencias externas, para reproducibilidad "
            "auditable. Excluye feriados regionales (no distinguibles por "
            "comuna en el dataset)."
        ),
        "features_nuevas": {
            "Es_Feriado": "la fecha es feriado nacional",
            "Es_Feriado_Largo": "feriado cae lunes o viernes",
            "Dias_Al_Feriado": "distancia con signo al feriado más cercano, clip ±7",
            "Feriado_Irrumpido": "día hábil con feriado a ≤2 días (puente)",
        },
        "anti_leakage": {
            "calendario_publico_conocido_de_antemano": True,
            "correlaciones_train": corrs,
            "verificacion": verif,
        },
        "features_totales": feature_cols,
        "n_features": len(feature_cols),
        "n_features_v9": len(feature_cols) - len(FEATURES_FERIADOS),
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
        "metricas_feriado_vs_no_feriado": met_fer,
        "sesgo_por_region_vs_v9": {
            r: {"v9": ref9_reg[r]["sesgo_pct"], "v10": met_region[r]["sesgo_pct"],
                "delta_pp": round(met_region[r]["sesgo_pct"]
                                  - ref9_reg[r]["sesgo_pct"], 2)}
            for r in met_region
        },
        "comparativa": {
            "v9": {k: ref9[k] for k in ["MAE", "RMSE", "R2", "sesgo_pct", "n"]},
            "v10": met,
        },
        "importancia_features": imp.head(20).to_dict("records"),
        "sanity_check": {"r2_mayor_a_0_9_sospechoso": fuga, "r2_observado": met["R2"]},
        "tiempo_entrenamiento_segundos": round(t_ent, 1),
        "tiempo_total_segundos": round(t_total, 1),
        "limitaciones": [
            "Split de 2 años: el efecto feriado se valida en 2025, sin "
            "posibilidad de probar estabilidad más allá.",
            "Los feriados regionales (20-sep en Coquimbo, 21-may en Iquique, "
            "etc.) no se modelan porque el dataset no distingue comuna.",
            "El calendario está hardcodeado para 2024-2025; para producción "
            "hay que extenderlo o instalar `holidays`.",
        ],
    }
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 74)
    print("✅ v10 COMPLETADO")
    print(f"  Modelo:   {RUTA_MODELO_OUT.name}")
    print(f"  Metadata: {RUTA_SALIDA.name}")
    print(f"  Tiempo total: {t_total:.1f} s")
    print("=" * 74)


if __name__ == "__main__":
    main()
