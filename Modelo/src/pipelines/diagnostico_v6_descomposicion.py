"""
Diagnóstico v6 — T2: Descomposición del error a nivel establecimiento (test 2025).

Responde a las hipótesis T2-T4 del plan v6 (odd/tasks/modelo-v6.md):

  A. Techo climatológico:   share_2024 × media regional train 2024 del mismo MM-DD.
                            (útil solo en las 6 regiones con datos en 2024)
  B. Techo Etapa 1 perfecta: share_2024 × TOTAL REGIONAL REAL del día.
                            (mide el techo de la arquitectura dos-etapas con
                            cuota fija: cuánto del error restante es ruido
                            propio del establecimiento)
  C. v5 reportado:          métricas leyendo de model_metadata_v5.json (no
                            re-entrena ni re-evalúa; referencia).
  D. Cuota trailing:        share dinámico (ventana 30 filas con shift(4),
                            anti-leakage horizonte 96h) × TOTAL REGIONAL REAL.
                            (aisla el efecto de la cuota dinámica vs fija)

  Señal de lags de demanda (T4): persistencia pura (pred = Total lag 4),
  correlación del residuo de B con el lag 4, y R² incremental de
  Total ~ pred_B + lag4 vs Total ~ pred_B (OLS con numpy).

Evaluación SIEMPRE nivel establecimiento+día, test 2025 (agregando las
filas multi-causa por estab+fecha con suma de Total).

Salida: models/diagnostico_v6_t2.json + reporte en consola (español).

Uso:
    python3 src/pipelines/diagnostico_v6_descomposicion.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parents[2]
RUTA_DATOS = BASE / "data" / "processed" / "df_modelo.parquet"
RUTA_CUOTAS = BASE / "models" / "cuotas_establecimiento_v5.csv"
RUTA_METADATA_V5 = BASE / "models" / "model_metadata_v5.json"
RUTA_SALIDA = BASE / "models" / "diagnostico_v6_t2.json"

VENTANA_TRAILING = 30   # filas (días) de la ventana de cuota dinámica
MIN_PERIODS_TRAILING = 10
LAG_DEMANDA = 4         # horizonte 96h → información disponible hasta T-4


# ---------------------------------------------------------------- utilidades

def metricas(y: np.ndarray, yhat: np.ndarray) -> dict:
    """MAE / RMSE / R² / sesgo% a nivel establecimiento+día."""
    ok = ~np.isnan(yhat)
    y, yhat = y[ok], yhat[ok]
    resid = yhat - y
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        "n": int(ok.sum()),
        "MAE": round(float(np.mean(np.abs(resid))), 4),
        "RMSE": round(float(np.sqrt(np.mean(resid**2))), 4),
        "R2": round(1 - ss_res / ss_tot, 4) if ss_tot > 0 else None,
        "sesgo_pct": round(100 * float(np.sum(resid)) / float(np.sum(y)), 2)
        if np.sum(y) > 0
        else None,
    }


def ols_r2(y: np.ndarray, X: np.ndarray) -> float:
    """R² de mínimos cuadrados con intercepto (numpy, sin statsmodels)."""
    Xd = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(Xd, y, rcond=None)
    resid = y - Xd @ beta
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return 1 - ss_res / ss_tot if ss_tot > 0 else np.nan


def corr_parcial(resid: np.ndarray, lag: np.ndarray, base: np.ndarray) -> float:
    """Correlación residuo–lag después de purgar la parte lineal de `base`."""
    A = np.column_stack([np.ones(len(resid)), base])
    b_res = resid - A @ np.linalg.lstsq(A, resid, rcond=None)[0]
    b_lag = lag - A @ np.linalg.lstsq(A, lag, rcond=None)[0]
    if b_res.std() == 0 or b_lag.std() == 0:
        return float("nan")
    return float(np.corrcoef(b_res, b_lag)[0, 1])


# ---------------------------------------------------------------- carga

def cargar_panel() -> pd.DataFrame:
    """Agrega las filas multi-causa: una fila por (establecimiento, fecha)."""
    df = pd.read_parquet(RUTA_DATOS)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    panel = (
        df.groupby(["IdEstablecimiento", "Fecha"], as_index=False)
        .agg(
            Total=("Total", "sum"),
            Region=("Region", "first"),
            Tipo=("TipoEstablecimiento", "first"),
        )
        .sort_values(["IdEstablecimiento", "Fecha"])
        .reset_index(drop=True)
    )
    return panel


def shares_con_fallback(panel: pd.DataFrame) -> pd.Series:
    """Cuota fija 2024 (v5) con fallback jerárquico v5 para estabs nuevos.

    Fallback: mediana de las cuotas de su Tipo dentro de su región → mediana
    global del tipo → 0. La normalización dentro de región+fecha se hace
    después, al construir la predicción.
    """
    cuotas = pd.read_csv(RUTA_CUOTAS)  # columnas: IdEstablecimiento, Region, share
    base = dict(zip(cuotas["IdEstablecimiento"], cuotas["share"]))

    # La cuota CSV no trae Tipo: calcular medianas por tipo desde train 2024.
    train = panel[panel["Fecha"].dt.year == 2024]
    dem_reg = train.groupby("Region")["Total"].transform("sum")
    share_train = train["Total"] / dem_reg
    tmp = train.assign(share=share_train)
    med_reg_tipo = tmp.groupby(["Region", "Tipo"])["share"].median()
    med_tipo = tmp.groupby("Tipo")["share"].median()

    out = []
    for est, region, tipo in panel[["IdEstablecimiento", "Region", "Tipo"]].itertuples(index=False):
        if est in base:
            out.append(base[est])
            continue
        s = med_reg_tipo.get((region, tipo), np.nan)
        if pd.isna(s):
            s = med_tipo.get(tipo, 0.0)
        out.append(float(s))
    return pd.Series(out, index=panel.index, name="share")


# ---------------------------------------------------------------- modelos A/B/D

def construir_predicciones(panel: pd.DataFrame) -> pd.DataFrame:
    panel = panel.copy()
    panel["share"] = shares_con_fallback(panel)

    train = panel[panel["Fecha"].dt.year == 2024]
    test = panel[panel["Fecha"].dt.year == 2025].copy()

    # Total regional real por región+fecha (sobre el panel agregado).
    real_reg = panel.groupby(["Region", "Fecha"])["Total"].sum()
    test["reg_real"] = test.set_index(["Region", "Fecha"]).index.map(real_reg)

    # ---- A: share × media regional train 2024 del mismo MM-DD --------------
    train_dia = train.copy()
    train_dia["mmdd"] = train_dia["Fecha"].dt.strftime("%m-%d")
    # Cada fecha 2024 es única → total regional de ese MM-DD = suma de Total.
    media_reg_2024 = train_dia.groupby(["Region", "mmdd"])["Total"].sum()
    test["mmdd"] = test["Fecha"].dt.strftime("%m-%d")
    test["reg_media_2024"] = test.set_index(["Region", "mmdd"]).index.map(media_reg_2024)
    # Renormalizar shares dentro de región+fecha y proyectar.
    test["share_norm"] = test.groupby(["Region", "Fecha"])["share"].transform(
        lambda s: s / s.sum() if s.sum() > 0 else s * 0
    )
    test["pred_A"] = test["share_norm"] * test["reg_media_2024"]

    # ---- B: share × total regional real (techo Etapa 1 perfecta) -----------
    test["pred_B"] = test["share_norm"] * test["reg_real"]

    # ---- D: cuota trailing (30 filas, shift 4) × total regional real -------
    test = test.sort_values(["IdEstablecimiento", "Fecha"]).reset_index(drop=True)
    test["trail"] = test.groupby("IdEstablecimiento")["Total"].transform(
        lambda s: s.shift(LAG_DEMANDA).rolling(VENTANA_TRAILING, min_periods=MIN_PERIODS_TRAILING).sum()
    )
    media_trail = test.groupby(["Region", "Fecha"])["trail"].transform("mean")
    test["peso_D"] = test["trail"].where(test["trail"].notna(), test["share"] * media_trail)
    test["peso_D"] = test["peso_D"].fillna(test["share"])  # región sin ningún trailing
    test["share_D"] = test.groupby(["Region", "Fecha"])["peso_D"].transform(
        lambda s: s / s.sum() if s.sum() > 0 else s * 0
    )
    test["pred_D"] = test["share_D"] * test["reg_real"]

    # ---- lags de demanda (T4) ---------------------------------------------
    test["lag4"] = test.groupby("IdEstablecimiento")["Total"].shift(LAG_DEMANDA)
    test["pred_persist"] = test["lag4"]

    return test


# ---------------------------------------------------------------- análisis

def main() -> None:
    print("=" * 70)
    print("DIAGNÓSTICO v6 (T2–T4): descomposición del error a nivel establecimiento")
    print("=" * 70)

    panel = cargar_panel()
    test = construir_predicciones(panel)

    y = test["Total"].to_numpy(float)
    regiones_2024 = sorted(panel.loc[panel["Fecha"].dt.year == 2024, "Region"].unique())
    mask_hist = test["Region"].isin(regiones_2024)
    mask_nuevas = ~mask_hist

    resultados: dict = {
        "descripcion": "Diagnóstico T2-T4 v6: descomposición de error nivel establecimiento+día, test 2025.",
        "panel": {
            "filas_estab_dia_test": int(len(test)),
            "establecimientos_test": int(test["IdEstablecimiento"].nunique()),
            "regiones_con_train_2024": regiones_2024,
            "regiones_nuevas_sin_train_2024": sorted(test.loc[mask_nuevas, "Region"].unique()),
            "nota_multi_causa": "Filas multi-causa agregadas por (estab, fecha) con suma de Total.",
        },
        "C_v5_reportado_desde_metadata": json.loads(RUTA_METADATA_V5.read_text())[
            "metrics_sistema_completo"
        ],
    }

    # ---- métricas globales --------------------------------------------------
    print("\n--- Métricas test 2025 (nivel establecimiento+día) ---")
    tablas = {
        "A_techo_climatologico_share_x_media_2024": test["pred_A"].to_numpy(float),
        "B_techo_etapa1_perfecta_share_x_reg_real": test["pred_B"].to_numpy(float),
        "D_cuota_trailing30_shift4_x_reg_real": test["pred_D"].to_numpy(float),
        "pura_persistencia_pred_Total_lag4": test["pred_persist"].to_numpy(float),
    }
    for nombre, pred in tablas.items():
        m = metricas(y, pred)
        resultados[nombre] = m
        print(f"{nombre:52s} MAE={m['MAE']:>9.3f}  R2={m['R2']!s:>8}  sesgo%={m['sesgo_pct']}  (n={m['n']})")

    # A solo aplica en las 6 regiones con train.
    mA = metricas(y[mask_hist.to_numpy()], test.loc[mask_hist, "pred_A"].to_numpy(float))
    resultados["A_solo_regiones_con_train_2024"] = mA
    print(f"{'A solo 6 regiones con train 2024':52s} MAE={mA['MAE']:>9.3f}  R2={mA['R2']!s:>8}  (n={mA['n']})")

    # ---- B y D por región ---------------------------------------------------
    print("\n--- B (techo) y D (trailing) por región ---")
    por_region = {}
    for reg, grp in test.groupby("Region"):
        gy = grp["Total"].to_numpy(float)
        mb = metricas(gy, grp["pred_B"].to_numpy(float))
        md = metricas(gy, grp["pred_D"].to_numpy(float))
        por_region[reg] = {"B": mb, "D": md}
        print(f"  {reg:22s} B: MAE={mb['MAE']:>8.3f} R2={str(mb['R2']):>8} | D: MAE={md['MAE']:>8.3f} R2={str(md['R2']):>8}")
    resultados["por_region_B_vs_D"] = por_region

    # Regiones nuevas (Antofagasta/Atacama): solo B/D aplican con share fallback.
    for etiqueta, mask in (("regiones_con_train", mask_hist), ("regiones_nuevas", mask_nuevas)):
        sub = test[mask.to_numpy()]
        resultados[f"B_{etiqueta}"] = metricas(sub["Total"].to_numpy(float), sub["pred_B"].to_numpy(float))
        resultados[f"D_{etiqueta}"] = metricas(sub["Total"].to_numpy(float), sub["pred_D"].to_numpy(float))

    # ---- suelo de ruido: variabilidad dentro de región+fecha ---------------
    std_dentro = test.groupby(["Region", "Fecha"])["Total"].std()
    resultados["suelo_ruido"] = {
        "std_dentro_region_fecha_media": round(float(std_dentro.mean()), 3),
        "std_dentro_region_fecha_mediana": round(float(std_dentro.median()), 3),
        "interpretacion": "Dispersion del Total real entre estabs de la misma región+fecha; cualquier modelo basado en share llega como máximo hasta este suelo.",
    }

    # ---- T4: señal de lags de demanda --------------------------------------
    print("\n--- T4: señal de lags de demanda (lag 4 / 96h) ---")
    sub = test.dropna(subset=["lag4"])
    y_s = sub["Total"].to_numpy(float)
    b_s = sub["pred_B"].to_numpy(float)
    d_s = sub["pred_D"].to_numpy(float)
    lag = sub["lag4"].to_numpy(float)

    r2_b = ols_r2(y_s, b_s.reshape(-1, 1))
    r2_b_lag = ols_r2(y_s, np.column_stack([b_s, lag]))
    r2_d = ols_r2(y_s, d_s.reshape(-1, 1))
    r2_d_lag = ols_r2(y_s, np.column_stack([d_s, lag]))

    resid_b = y_s - b_s
    correl_directa = float(np.corrcoef(resid_b, lag)[0, 1])
    correl_parcial = corr_parcial(resid_b, lag, b_s)

    resultados["T4_senal_lag4"] = {
        "n_filas": int(len(sub)),
        "OLS_R2_total_sobre_pred_B": round(float(r2_b), 4),
        "OLS_R2_total_sobre_pred_B_mas_lag4": round(float(r2_b_lag), 4),
        "delta_R2_por_lag4_sobre_B": round(float(r2_b_lag - r2_b), 4),
        "OLS_R2_total_sobre_pred_D": round(float(r2_d), 4),
        "OLS_R2_total_sobre_pred_D_mas_lag4": round(float(r2_d_lag), 4),
        "delta_R2_por_lag4_sobre_D": round(float(r2_d_lag - r2_d), 4),
        "correl_residuo_B_con_lag4": round(correl_directa, 4),
        "correl_parcial_residuo_B_vs_lag4_dado_pred_B": round(correl_parcial, 4),
        "interpretacion": "delta_R2 > 0.05 y correl_parcial moderada ⇒ la demanda propia a T-4 explica varianza más allá de la cuota; es candidata a feature de la v6.",
    }

    # ---- comparación directa B vs D (efecto de la cuota dinámica) -----------
    mB = resultados["B_techo_etapa1_perfecta_share_x_reg_real"]
    mD = resultados["D_cuota_trailing30_shift4_x_reg_real"]
    resultados["T3_cuota_trailing_vs_fija"] = {
        "B_cuota_fija_2024": mB,
        "D_cuota_trailing_30d": mD,
        "delta_MAE_D_menos_B": round(mD["MAE"] - mB["MAE"], 4),
        "delta_R2_D_menos_B": round((mD["R2"] or 0) - (mB["R2"] or 0), 4),
        "interpretacion": "Si delta_MAE ≈ 0 o > 0, la cuota trailing NO supera a la fija con Etapa 1 perfecta (hipótesis T3 descartada).",
    }

    # ---- persistencia con shift estricto de calendario ----------------------
    resultados["nota_limitaciones"] = [
        "El shift(4)/rolling(30) es por FILAS: si un estab tiene fechas faltantes, el lag no es exactamente T-4 de calendario.",
        "A usa el total regional observado de 2024 (mismo MM-DD); Antofagasta/Atacama no existen en 2024 → excluidas de A.",
        "B y D usan el total regional REAL (información no disponible en producción): son TECHOS diagnósticos, no modelos desplegables.",
        "Las métricas C (v5) se leen de model_metadata_v5.json sin re-entrenar.",
    ]

    RUTA_SALIDA.write_text(json.dumps(resultados, indent=2, ensure_ascii=False))
    print(f"\n✅ Resultados guardados en: {RUTA_SALIDA}")

    # ---- resumen ejecutivo ---------------------------------------------------
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"C (v5, referencia):        MAE={resultados['C_v5_reportado_desde_metadata']['MAE']}  R2={resultados['C_v5_reportado_desde_metadata']['R2']}")
    print(f"B (techo cuota fija):      MAE={mB['MAE']}  R2={mB['R2']}")
    print(f"D (cuota trailing):        MAE={mD['MAE']}  R2={mD['R2']}")
    print(f"A (climatológico 2024):    MAE={mA['MAE']}  R2={mA['R2']}")
    print(f"Persistencia lag4:         MAE={resultados['pura_persistencia_pred_Total_lag4']['MAE']}  R2={resultados['pura_persistencia_pred_Total_lag4']['R2']}")
    print(f"ΔR² por lag4 sobre B:      {resultados['T4_senal_lag4']['delta_R2_por_lag4_sobre_B']}")


if __name__ == "__main__":
    main()
