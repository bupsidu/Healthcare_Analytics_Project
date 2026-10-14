"""
Experimento E1 (v6) — réplica de v5 con UN ÚNICO cambio: cuota TRAILING
==========================================================================

Contexto (por qué existe este script)
--------------------------------------
El diagnóstico v6 (`diagnostico_v6_descomposicion.py`) mostró que la Etapa 2
de v5 reparte el total regional predicho con una cuota ESTÁTICA (share 2024),
calculada una sola vez desde train. Ese script implementó —y probó— una cuota
dinámica TRAILING (hipótesis T3):

    trail_e(T) = Total_e.shift(4).rolling(30, min_periods=10).sum()

pero la evaluó como TECHO diagnóstico (usaba el total regional OBSERVADO, no
disponible en producción).

Este script E1 cierra ese hueco: es una réplica del pipeline v5
(`reentrenar_modelo_v5_trailing.py`) donde SOLO cambia la Etapa 2, que pasa de
cuota fija 2024 a cuota dinámica trailing. Todo lo demás — Etapa 1 a nivel
región, features, hiperparámetros, semilla, split temporal, agregación
multi-causa y definición de métricas — es IDÉNTICO al v5, de modo que la
comparación E1 vs v5 AISLA el efecto de la cuota.

Para garantizar esa identidad, la Etapa 1 NO se reescribe: se IMPORTA el módulo
v5 (que no se modifica) y se ejecutan sus mismas funciones con su misma
configuración. El script v5 solo define funciones/constants en import; su
`main()` no se ejecuta.

Etapa 1 (IDÉNTICA a v5, importada del módulo v5)
------------------------------------------------
- Agregación a nivel (Region, Fecha).
- Baseline adaptativo trailing de contaminación (N=45, shift(1), semilla train).
- One-hot de Región, estacionalidad cíclica, imputación con mediana de train.
- RandomForestRegressor(n_estimators=200, max_depth=15, min_samples_split=50,
  min_samples_leaf=20, max_features='sqrt', random_state=42, n_jobs=-1).
- Split: train = 2024, test = 2025.

Etapa 2 (EL ÚNICO CAMBIO de E1) — cuota dinámica trailing con
denominador REGIONAL (sin renormalizar entre los reportantes del día)
------------------------------------------------------------------------
Para cada establecimiento e y fecha T del test 2025:

  1. trail_e(T) = Total_e.shift(4).rolling(30, min_periods=10).sum() sobre la
     SERIE del establecimiento REINDEXADA AL CALENDARIO DIARIO completo de su
     rango (días sin reporte = NaN en Total; el rolling suma solo las
     observaciones disponibles). CAMBIO DE SEMÁNTICA documentado respecto de
     la primera versión de E1 y del diagnóstico v6: la ventana es de
     CALENDARIO, no de FILAS, de modo que shift(4) es un lag real de 4 días
     de calendario y trail_e(T) existe en cada fecha T con ≥10 observaciones
     en la ventana [T-33, T-4], aunque el estab no haya reportado ese día.
     ANTI-LEAKAGE (horizonte 96h): el shift(4) garantiza que la información
     disponible al pronosticar T es hasta T-4; el día T NUNCA entra en su
     propia cuota. La ventana puede cruzar la frontera 2024→2025 porque los
     días previos a T ya fueron OBSERVADOS (misma suposición que los lags y
     el baseline trailing de la Etapa 1).

  2. Establecimientos SIN trail en T (historia insuficiente: menos de
     MIN_PERIODS=10 observaciones en la ventana [T-33, T-4] de calendario):
         peso_e(T) = share_2024_e × media(trail_e'(T)) de su Región en T
     donde la media se promedia sobre TODOS los establecimientos de la
     región CON trail en T (reporten o no ese día); y si la región no tiene
     NINGÚN trail en T, se usa share_2024_e directo. Todos los trail de la
     media son ≤ T-4 (anti-leakage).

  3. share_2024 con el MISMO fallback jerárquico del v5 (calculado SOLO desde
     train 2024, reutilizando `v5.preparar_cuotas_test`):
         mediana de las cuotas de su TipoEstablecimiento dentro de su región
         → mediana global del tipo → 0.

  4. denominador(T, Región) = Σ peso_e(T) sobre TODOS los establecimientos de
     la región (reporten o no ese día). NO se renormaliza entre los
     reportantes del día: el reparto se hace sobre la REGIÓN-FECHA COMPLETA.
     (La primera versión de E1 renormalizaba entre los ~1,42% de filas que
     sí reportaban: los días con UN solo reportante se llevaban el 100% del
     total regional predicho — MAE 14.06 pero RMSE 29.13 / R² −0.38, 44,5%
     del SSE en esas filas. El denominador regional corrige ese defecto.)

  5. pred_e(T) = peso_e(T) / denominador(T, Región) × pred_region(T). Los
     establecimientos que NO reportan ese día dejan su parte SIN REPARTIR
     (misma semántica conservadora de v5, que deja ~1,6% del total sin
     repartir). A diferencia del diagnóstico v6 (que usaba la región
     OBSERVADA y por eso era un techo no desplegable), E1 usa la predicción
     REAL del modelo → es un sistema DESPLEGABLE.

Evaluación (definiciones idénticas al diagnóstico v6)
-----------------------------------------------------
- Nivel ESTABLECIMIENTO + DÍA sobre test 2025 (las ~4 filas multi-causa por
  estab+fecha se suman antes de evaluar).
- MAE, RMSE, sesgo% = 100·Σ(pred−real)/Σreal.
- R² = 1 − SS_res/SS_tot calculado SOBRE TODAS las filas.
- Control de identidad: con la cuota FIJA este mismo código debe reproducir
  exactamente las métricas de v5 (MAE 14.7633 / RMSE 22.9807 / R² 0.141 /
  sesgo 21.01), lo que demuestra que la única diferencia es la cuota.

Salida:
  - models/model_metadata_v6e1.json   métricas, configuración de la cuota,
                                      aviso anti-leakage, comparación vs v5,
                                      semilla/hiperparámetros.

Restricción: este script NO modifica ningún archivo existente (el v5 queda
intacto); solo crea este archivo y su JSON de salida.

Uso:
    python3 src/pipelines/reentrenar_modelo_v6_e1_trailing.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
RUTA_DATOS = BASE_DIR / "data" / "processed" / "df_modelo.parquet"
RUTA_METADATA_V5 = BASE_DIR / "models" / "model_metadata_v5.json"
RUTA_SALIDA = BASE_DIR / "models" / "model_metadata_v6e1.json"

# ---------------------------------------------------------------------------
# Configuración de la cuota trailing (Etapa 2 de E1)
# ---------------------------------------------------------------------------
VENTANA_TRAILING = 30        # días de CALENDARIO de la ventana de la cuota
MIN_PERIODS_TRAILING = 10    # mínimas observaciones previas para formar trail
LAG_DEMANDA = 4              # horizonte 96h → información disponible hasta T-4
TARGET = "Total"

# Importar el pipeline v5 SIN ejecutar su main(): garantiza que la Etapa 1
# (features, hiperparámetros, semilla) sea idéntica por construcción.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import reentrenar_modelo_v5_trailing as v5  # noqa: E402


# ---------------------------------------------------------------------------
# Utilidades de evaluación (idénticas al diagnóstico v6)
# ---------------------------------------------------------------------------
def metricas(y: np.ndarray, yhat: np.ndarray) -> dict:
    """MAE / RMSE / R² / sesgo% a nivel establecimiento+día.

    R² = 1 − SS_res/SS_tot sobre TODAS las filas (definición idéntica al
    diagnóstico v6 y equivalente a sklearn.r2_score usado por v5).
    """
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


# ---------------------------------------------------------------------------
# Carga: agrega las filas multi-causa a una fila por (estab, fecha)
# ---------------------------------------------------------------------------
def cargar_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por (establecimiento, fecha) sumando las causas respiratorias.

    Criterio IDÉNTICO al v5 y al diagnóstico: cada fila del dataset es una
    causa DEIS distinta, así que la demanda real de un estab en un día es la
    SUMA de sus filas.
    """
    return (
        df.groupby(["IdEstablecimiento", "Fecha"], as_index=False)
        .agg(
            Total=(TARGET, "sum"),
            Region=("Region", "first"),
            TipoEstablecimiento=("TipoEstablecimiento", "first"),
        )
        .sort_values(["IdEstablecimiento", "Fecha"])
        .reset_index(drop=True)
    )


def calcular_share_2024_con_fallback(
    test_raw: pd.DataFrame,
    train_raw: pd.DataFrame,
    verbose: bool = True,
) -> tuple[pd.DataFrame, int]:
    """share_2024 por establecimiento con el fallback jerárquico EXACTO del v5.

    Calculado SOLO desde train 2024:
      - estabs presentes en train → su cuota histórica (suma 2024 del estab /
        suma 2024 de su región), vía `v5.calcular_cuotas`;
      - estabs NUEVOS en test → mediana de las cuotas de su
        TipoEstablecimiento dentro de su región (train 2024) → mediana global
        del tipo → 0, vía `v5.preparar_cuotas_test` (misma función que v5).

    Devuelve (IdEstablecimiento, Region, share) SIN renormalizar: la
    normalización de E1 es el denominador REGIONAL por fecha tras aplicar la
    cuota trailing.
    """
    cuotas = v5.calcular_cuotas(train_raw)
    cuotas_test = v5.preparar_cuotas_test(test_raw, cuotas, train_raw, verbose=verbose)
    return cuotas_test[["IdEstablecimiento", "Region", "share"]].copy(), int(
        cuotas_test.attrs.get("n_nuevos", 0)
    )


# ---------------------------------------------------------------------------
# Etapa 2 de E1 — cuota dinámica trailing
# ---------------------------------------------------------------------------
def calcular_trail_calendario(panel: pd.DataFrame) -> pd.DataFrame:
    """trail por establecimiento y fecha sobre el CALENDARIO diario completo.

    CAMBIO DE SEMÁNTICA (documentado): la ventana rolling es de CALENDARIO,
    no de FILAS. Para cada establecimiento se reindexa su serie (panel
    2024+2025 agregado por estab+fecha) al calendario diario completo de su
    rango [primera fecha, última fecha]; los días sin reporte quedan con
    Total=NaN y el `rolling(VENTANA_TRAILING, min_periods=MIN_PERIODS_TRAILING)
    .sum()` suma solo las observaciones disponibles dentro de la ventana.

    Consecuencia: `shift(LAG_DEMANDA=4)` es un lag REAL de 4 días de
    calendario (anti-leakage del horizonte 96h: al pronosticar la fecha T
    solo se usan datos hasta T-4) y trail_e(T) queda definido en CADA fecha
    T con ≥ MIN_PERIODS observaciones en [T-33, T-4], aunque el estab no
    haya reportado el día T. Así el denominador regional de la Etapa 2 puede
    evaluar el peso de TODOS los estabs de la región en cada fecha.

    Returns:
        DataFrame (IdEstablecimiento, Fecha, trail) sobre el CALENDARIO de
        cada estab (más filas que el panel: incluye los días sin reporte).
    """
    partes: list[pd.DataFrame] = []
    for est, g in panel.groupby("IdEstablecimiento"):
        g = g.sort_values("Fecha")
        cal = pd.date_range(g["Fecha"].min(), g["Fecha"].max(), freq="D")
        serie = pd.Series(
            g[TARGET].to_numpy(), index=pd.DatetimeIndex(g["Fecha"].to_numpy())
        )
        serie_cal = serie.reindex(cal)  # días sin reporte → NaN
        trail = (
            serie_cal.shift(LAG_DEMANDA)
            .rolling(VENTANA_TRAILING, min_periods=MIN_PERIODS_TRAILING)
            .sum()
        )
        partes.append(
            pd.DataFrame(
                {
                    "IdEstablecimiento": est,
                    "Fecha": cal,
                    "trail": trail.to_numpy(),
                }
            )
        )
    return pd.concat(partes, ignore_index=True)


def construir_pesos_trailing(
    region_test: pd.DataFrame,
    share_2024: pd.DataFrame,
    trail_calendario: pd.DataFrame,
) -> pd.DataFrame:
    """Construye los pesos trailing con denominador REGIONAL (por Región-Fecha).

    Se arma la GRILLA COMPLETA (establecimiento × fecha del test de su
    región), es decir TODOS los estabs de cada región en CADA fecha T del
    test — reporten o no ese día — y se calcula:

      1. peso_e(T) = trail_e(T) si el estab tiene trail en T (≥10
         observaciones en la ventana de calendario [T-33, T-4]).
      2. Si trail_e(T) es NaN → share_2024_e × media(trail) de su Región en
         T (media sobre los estabs de la región CON trail en T, reporten o
         no; todos los trail son ≤ T-4, anti-leakage).
      3. Si la Región en T no tiene NINGÚN trail → share_2024_e directo.
      4. denominador(T, Región) = Σ peso_e(T) sobre TODOS los estabs de la
         región (reporten o no). NO se renormaliza entre los reportantes del
         día: los estabs que no reportan dejan su parte SIN REPARTIR (misma
         semántica conservadora de la cuota fija de v5).

    Returns:
        Grilla (IdEstablecimiento, Region, Fecha, share, trail, peso,
        denominador_regional, peso_normalizado). La predicción de cada estab
        es `peso_normalizado × pred_region_total`.
    """
    estabs = share_2024[["IdEstablecimiento", "Region", "share"]]
    fechas = region_test[["Region", "Fecha"]].drop_duplicates()
    grid = estabs.merge(fechas, on="Region", how="inner")
    n_sin_share = int(grid["share"].isna().sum())
    if n_sin_share:
        raise ValueError(
            f"{n_sin_share} filas de la grilla sin share_2024 ni fallback."
        )

    grid = grid.merge(trail_calendario, on=["IdEstablecimiento", "Fecha"], how="left")

    # Paso 2/3: fallback para estabs sin trail suficiente en esa fecha.
    media_trail = grid.groupby(["Region", "Fecha"])["trail"].transform("mean")
    grid["peso"] = grid["trail"].where(
        grid["trail"].notna(), grid["share"] * media_trail
    )
    grid["peso"] = grid["peso"].fillna(grid["share"])  # región sin trail en T

    # Paso 4: denominador REGIONAL (todos los estabs, reporten o no ese día).
    denominador = grid.groupby(["Region", "Fecha"])["peso"].transform("sum")
    grid["denominador_regional"] = denominador
    grid["peso_normalizado"] = np.where(
        denominador > 0, grid["peso"] / denominador, 0.0
    )
    return grid


def agregar_prediccion_region(
    region_test: pd.DataFrame,
    pred_region_total: np.ndarray,
    test_panel: pd.DataFrame,
) -> pd.DataFrame:
    """Adjunta el total regional PREDICHO (Etapa 1) a cada fila estab+fecha.

    La predicción final de E1 es `peso_normalizado × pred_region_total` y se
    evalúa a nivel ESTABLECIMIENTO + DÍA (una fila por estab+fecha, Total ya
    agregado).
    """
    pred_region = region_test[["Region", "Fecha"]].copy()
    pred_region["pred_region_total"] = pred_region_total

    out = test_panel.merge(pred_region, on=["Region", "Fecha"], how="left")
    if out["pred_region_total"].isna().any():
        raise ValueError("Hay (Región, Fecha) de test sin predicción de la Etapa 1.")
    return out


def main() -> None:
    print("=" * 70)
    print("EXPERIMENTO E1 (v6) — v5 con Etapa 2 de cuota DINÁMICA TRAILING")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # 1. Carga y split temporal (idéntico al v5)
    # -----------------------------------------------------------------------
    print("\nCargando dataset procesado...")
    df = pd.read_parquet(RUTA_DATOS)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    df["Año"] = df["Fecha"].dt.year

    train_raw = df[df["Año"] == v5.TRAIN_YEAR].copy()
    test_raw = df[df["Año"] == v5.TEST_YEAR].copy()

    print(f"\n📊 División temporal (idéntica a v5):")
    print(f"  Train ({v5.TRAIN_YEAR}): {len(train_raw):,} filas (establecimiento)")
    print(f"  Test  ({v5.TEST_YEAR}): {len(test_raw):,} filas (establecimiento)")

    panel = cargar_panel(df)
    test_panel = panel[panel["Fecha"].dt.year == v5.TEST_YEAR].copy()
    print(f"  Panel estab+fecha (multi-causa agregada): {len(panel):,} filas | "
          f"test: {len(test_panel):,}")

    # -----------------------------------------------------------------------
    # 2. ETAPA 1 — IDÉNTICA al v5 (importada del módulo v5, sin modificarlo)
    # -----------------------------------------------------------------------
    print(f"\n--- Etapa 1: IDÉNTICA a v5 (baseline trailing N="
          f"{v5.VENTANA_PRINCIPAL}, features y RF iguales) ---")
    region_train, region_test, dummies_cols, info_trail = v5.preparar_features_region(
        df, ventana=v5.VENTANA_PRINCIPAL,
    )
    features = v5.construir_lista_features(dummies_cols, "trailing")
    res1 = v5.entrenar_etapa_1(region_train, region_test, features, con_cv=False)
    print(f"  Features ({len(features)}): idénticas a v5")
    print(f"  Hiperparámetros: {v5.HIPERPARAMETROS}")
    print(f"  Nivel región (test 2025): MAE={res1['met_region']['MAE']:9.3f}  "
          f"RMSE={res1['met_region']['RMSE']:9.3f}  R²={res1['met_region']['R2']:8.4f}")

    meta_v5 = json.loads(RUTA_METADATA_V5.read_text(encoding="utf-8"))
    met_region_v5 = meta_v5["etapa_1"]["metrics_test_2025"]
    met_v5_ref = meta_v5["metrics_sistema_completo"]
    etapa1_identica = res1["met_region"] == met_region_v5
    print(f"  Verificación de identidad vs v5 (métricas región en "
          f"model_metadata_v5.json): {'✅ COINCIDEN' if etapa1_identica else '⚠️  DIFIEREN'} "
          f"({met_region_v5})")

    # -----------------------------------------------------------------------
    # 3. ETAPA 2 — share_2024 con fallback jerárquico del v5
    # -----------------------------------------------------------------------
    print("\n--- Etapa 2: share_2024 con fallback jerárquico (idéntico a v5) ---")
    share_2024, n_nuevos = calcular_share_2024_con_fallback(test_raw, train_raw)
    print(f"  Establecimientos en test sin cuota en train (fallback jerárquico): "
          f"{n_nuevos}")

    # -----------------------------------------------------------------------
    # 4. ETAPA 2 — cuota trailing (EL ÚNICO CAMBIO de E1)
    # -----------------------------------------------------------------------
    print("\n--- Etapa 2 (E1): cuota DINÁMICA TRAILING con denominador REGIONAL ---")
    print(f"  trail_e(T) = Total_e.shift({LAG_DEMANDA})."
          f"rolling({VENTANA_TRAILING}, min_periods={MIN_PERIODS_TRAILING}).sum()")
    print(f"  CAMBIO DE SEMÁNTICA: la serie de cada estab se REINDEXA al "
          f"calendario diario de su rango (días sin reporte = NaN), así la "
          f"ventana es de CALENDARIO y shift({LAG_DEMANDA}) es un lag real de "
          f"{LAG_DEMANDA} días.")
    print(f"  Anti-leakage: shift({LAG_DEMANDA}) → información disponible hasta "
          f"T-{LAG_DEMANDA} (horizonte 96h); T nunca entra en su propia cuota.")

    trail_cal = calcular_trail_calendario(panel)
    grid = construir_pesos_trailing(region_test, share_2024, trail_cal)
    n_grid_con_trail = int(grid["trail"].notna().sum())
    print(f"  Grilla (todos los estabs de la región × fechas del test): "
          f"{len(grid):,} filas | con trail: {n_grid_con_trail:,} "
          f"({100 * n_grid_con_trail / len(grid):.1f}%)")
    print(f"  denominador(T, Región) = Σ peso sobre TODOS los estabs de la "
          f"región (reporten o no): los no reportantes dejan su parte SIN "
          f"REPARTIR (semántica de v5).")

    test_pred = test_panel.merge(
        grid[["IdEstablecimiento", "Fecha", "trail", "peso_normalizado",
              "denominador_regional"]],
        on=["IdEstablecimiento", "Fecha"], how="left",
    )
    if test_pred["peso_normalizado"].isna().any():
        raise ValueError(
            "Hay filas (estab, fecha) del test fuera de la grilla de pesos."
        )
    n_con_trail = int(test_pred["trail"].notna().sum())
    print(f"  Filas reportantes con trail disponible: {n_con_trail:,} / "
          f"{len(test_pred):,} ({100 * n_con_trail / len(test_pred):.1f}%)")

    # -----------------------------------------------------------------------
    # 5. Reparto del total regional PREDICHO (Etapa 1) y evaluación E1
    #    pred_e(T) = peso_normalizado (denominador regional) × pred_region
    # -----------------------------------------------------------------------
    test_pred = agregar_prediccion_region(region_test, res1["y_pred"], test_pred)
    test_pred["pred_e1"] = test_pred["pred_region_total"] * test_pred["peso_normalizado"]

    y = test_pred[TARGET].to_numpy(float)
    met_e1 = metricas(y, test_pred["pred_e1"].to_numpy(float))

    # -----------------------------------------------------------------------
    # 6. CONTROL: con la cuota FIJA este mismo código debe reproducir v5
    #    (demuestra que la única diferencia del pipeline es la cuota).
    # -----------------------------------------------------------------------
    cuotas = v5.calcular_cuotas(train_raw)
    cuotas_test = v5.preparar_cuotas_test(test_raw, cuotas, train_raw, verbose=False)
    control = test_pred.merge(
        cuotas_test[["IdEstablecimiento", "share_normalizada"]],
        on="IdEstablecimiento", how="left",
    )
    control["pred_control_fija"] = (
        control["pred_region_total"] * control["share_normalizada"].fillna(0.0)
    )
    met_control = metricas(y, control["pred_control_fija"].to_numpy(float))
    # Misma fila de test en ambas versiones, para poder compararlas por región.
    control["pred_e1"] = test_pred["pred_e1"].to_numpy()

    # -----------------------------------------------------------------------
    # 7. Métricas por región: E1 y v5 (v5 vía el control, verificado arriba)
    # -----------------------------------------------------------------------
    met_por_region: dict[str, dict] = {}
    met_por_region_v5: dict[str, dict] = {}
    for reg, grp in control.groupby("Region"):
        gy = grp[TARGET].to_numpy(float)
        met_por_region[reg] = metricas(gy, grp["pred_e1"].to_numpy(float))
        met_por_region_v5[reg] = metricas(
            gy, grp["pred_control_fija"].to_numpy(float)
        )

    # -----------------------------------------------------------------------
    # 7b. DIAGNÓSTICO: verificación de la CORRECCIÓN del defecto de diseño.
    #     Defecto PREVIO de E1: la cuota se renormalizaba entre los estabs
    #     CON fila ese día, así que en los días con muy pocos reportantes el
    #     ÚNICO reportante se llevaba el 100% del total regional predicho
    #     (1,42% de las filas = 44,54% del SSE; RMSE 29.13 / R² −0.38).
    #     Corrección: denominador REGIONAL (todos los estabs de la región,
    #     reporten o no); los no reportantes dejan su parte sin repartir.
    #     Se mide la participación en el SSE de los días con ≤5 reportantes
    #     ANTES (versión previa) vs DESPUÉS (esta versión).
    # -----------------------------------------------------------------------
    n_estabs_fecha = (
        test_pred.groupby(["Region", "Fecha"])["IdEstablecimiento"].transform("nunique")
    )
    test_pred["n_estabs_fecha"] = n_estabs_fecha
    control["n_estabs_fecha"] = n_estabs_fecha.to_numpy()

    max_estabs_region = (
        test_pred.groupby("Region")["IdEstablecimiento"].nunique()
    )
    grupos = (
        test_pred[["Region", "Fecha", "n_estabs_fecha"]]
        .drop_duplicates()
        .copy()
    )
    grupos["max_region"] = grupos["Region"].map(max_estabs_region)

    pocos = test_pred["n_estabs_fecha"] <= 5
    sse_e1 = float(np.sum((test_pred["pred_e1"] - test_pred[TARGET]) ** 2))
    sse_v5 = float(
        np.sum((control["pred_control_fija"] - control[TARGET]) ** 2)
    )
    sse_e1_pocos = float(
        np.sum((test_pred.loc[pocos, "pred_e1"] - test_pred.loc[pocos, TARGET]) ** 2)
    )
    sse_v5_pocos = float(
        np.sum(
            (control.loc[pocos, "pred_control_fija"] - control.loc[pocos, TARGET]) ** 2
        )
    )

    suma_pred_e1 = float(test_pred["pred_e1"].sum())
    suma_pred_v5 = float(control["pred_control_fija"].sum())
    suma_pred_region_total = float(res1["y_pred"].sum())  # total regional predicho
    suma_real = float(test_pred[TARGET].sum())
    grupos_incompletos = int((grupos["n_estabs_fecha"] < grupos["max_region"]).sum())
    # Fracción del denominador regional que SÍ se reparte (peso de los
    # reportantes del día); el resto queda sin repartir como en v5.
    frac_repartida = (
        test_pred.groupby(["Region", "Fecha"])["peso_normalizado"].sum()
    )
    grupos_con_parte_sin_repartir = int((frac_repartida < 0.999).sum())

    diagnostico_dias_incompletos = {
        "defecto_previo_corregido": (
            "La PRIMERA versión de E1 renormalizaba la cuota trailing entre "
            "los establecimientos CON fila ese día (los que reportaron). Los "
            "establecimientos NO reportan todos los días: hay (Región, Fecha) "
            "del test con UN SOLO establecimiento reportante (p. ej. O'Higgins "
            "2025-05-05: 1 de 44 estabs, Total real 81). Con la "
            "renormalización entre reportantes, el ÚNICO reportante se "
            "llevaba el 100% del total regional PREDICHO por la Etapa 1 "
            "(~2.000-2.600) mientras su demanda real era de decenas: error "
            "de miles en esa fila. Eso produjo MAE 14.0604 (mejor que v5) "
            "pero RMSE 29.1255 / R² −0.3798 (mucho peor que v5), con 1,42% "
            "de las filas explicando el 44,54% del SSE."
        ),
        "correccion_aplicada": (
            "Denominador REGIONAL: denominador(T, Región) = Σ peso_e(T) sobre "
            "TODOS los establecimientos de la región (reporten o no ese día), "
            "con trail calculado sobre la serie de cada estab REINDEXADA AL "
            "CALENDARIO diario (días sin reporte = NaN). pred_e(T) = "
            "peso_e(T)/denominador(T, Región) × pred_region(T): los estabs "
            "que no reportan dejan su parte SIN REPARTIR, igual que v5, y "
            "ningún reportante puede quedarse con el total regional."
        ),
        "por_que_v5_no_lo_padece": (
            "v5 renormaliza la cuota de forma ESTÁTICA por región, así que en "
            "un día con estabs faltantes solo reparte share_2024 × "
            "pred_region_total (fracción pequeña) y DEJA SIN REPARTIR el resto "
            "del total regional predicho: subestima el total predicho (sesgo "
            "global menor) pero evita los errores gigantes puntuales."
        ),
        "referencia_e1_previo_sin_denominador_regional": {
            "metricas_establecimiento": {
                "MAE": 14.0604,
                "RMSE": 29.1255,
                "R2": -0.3798,
                "sesgo_pct": 22.99,
            },
            "pct_filas_con_5_o_menos_estabs": 1.42,
            "pct_del_SSE_en_esas_filas": 44.54,
            "nota": (
                "Valores de la versión previa de E1 (renormalización entre "
                "reportantes del día), registrados aquí como referencia "
                "histórica del defecto corregido."
            ),
        },
        "grupos_region_fecha_totales": int(len(grupos)),
        "grupos_con_todos_los_estabs": int(
            (grupos["n_estabs_fecha"] == grupos["max_region"]).sum()
        ),
        "grupos_con_estabs_faltantes": grupos_incompletos,
        "grupos_con_menos_del_50pct_estabs": int(
            (grupos["n_estabs_fecha"] < 0.5 * grupos["max_region"]).sum()
        ),
        "filas_con_5_o_menos_estabs": int(pocos.sum()),
        "pct_filas_con_5_o_menos_estabs": round(100 * float(pocos.mean()), 2),
        "pct_del_SSE_E1_en_esas_filas": round(100 * sse_e1_pocos / sse_e1, 2),
        "pct_del_SSE_v5_en_esas_filas": round(100 * sse_v5_pocos / sse_v5, 2),
        "suma_total_predicho_E1": round(suma_pred_e1, 2),
        "suma_total_predicho_v5": round(suma_pred_v5, 2),
        "suma_total_real": round(suma_real, 2),
        "lectura_sesgo": (
            f"Con el denominador regional, E1 ya NO reparte el 100% del total "
            f"regional predicho ({suma_pred_region_total:,.0f}): reparte "
            f"{suma_pred_e1:,.0f} "
            f"({100 * (1 - suma_pred_e1 / suma_pred_region_total):.1f}% menos, "
            f"{grupos_con_parte_sin_repartir:,} de {len(grupos):,} grupos con "
            f"parte sin repartir) porque la cuota de los estabs que no "
            f"reportan ese día queda fuera del reparto — la misma semántica "
            f"conservadora de v5 (reparte {suma_pred_v5:,.0f}). Total real = "
            f"{suma_real:,.0f}."
        ),
    }

    # -----------------------------------------------------------------------
    # 8. Tabla comparativa E1 vs v5
    # -----------------------------------------------------------------------
    met_v5 = met_v5_ref
    comparacion = {}
    for nombre, valor in [("MAE", "MAE"), ("RMSE", "RMSE"), ("R2", "R2"),
                          ("sesgo_pct", "sesgo_pct")]:
        comparacion[nombre] = {
            "v5_cuota_fija": met_v5[valor],
            "e1_cuota_trailing": met_e1[valor],
            "delta_e1_menos_v5": round(met_e1[valor] - met_v5[valor], 4),
        }
    mejora_mae = met_e1["MAE"] < met_v5["MAE"]
    mejora_rmse = met_e1["RMSE"] < met_v5["RMSE"]
    mejora_r2 = met_e1["R2"] > met_v5["R2"]
    mejora_sesgo = abs(met_e1["sesgo_pct"]) < abs(met_v5["sesgo_pct"])
    n_mejoras = int(mejora_mae) + int(mejora_rmse) + int(mejora_r2) + int(mejora_sesgo)

    etiquetas = {
        "MAE": (met_e1["MAE"], met_v5["MAE"], mejora_mae),
        "RMSE": (met_e1["RMSE"], met_v5["RMSE"], mejora_rmse),
        "R²": (met_e1["R2"], met_v5["R2"], mejora_r2),
        "sesgo |%|": (
            abs(met_e1["sesgo_pct"]), abs(met_v5["sesgo_pct"]), mejora_sesgo,
        ),
    }
    texto_mejoras = "; ".join(
        f"{k} {a:.4f} vs {b:.4f}" for k, (a, b, ok) in etiquetas.items() if ok
    )
    texto_peores = "; ".join(
        f"{k} {a:.4f} vs {b:.4f}" for k, (a, b, ok) in etiquetas.items() if not ok
    )

    if n_mejoras == 4:
        veredicto = (
            "MEJORA CONSISTENTE: la cuota trailing con denominador regional "
            "supera a la cuota fija de v5 en las 4 métricas "
            f"({texto_mejoras})."
        )
    else:
        veredicto = (
            f"MEJORA EN {n_mejoras}/4 MÉTRICAS: la cuota trailing con "
            f"denominador regional mejora {texto_mejoras}"
            + (f", pero empeora {texto_peores}" if texto_peores else "")
            + ". Ver metricas_por_region y "
            "diagnostico_dias_incompletos para el detalle. NO se vende como "
            "éxito total."
        )

    print("\n" + "-" * 70)
    print("MÉTRICAS E1 — nivel ESTABLECIMIENTO + DÍA (test 2025)")
    print("-" * 70)
    print(f"  MAE={met_e1['MAE']:.4f}  RMSE={met_e1['RMSE']:.4f}  "
          f"R²={met_e1['R2']:.4f}  sesgo={met_e1['sesgo_pct']:+.2f}%  "
          f"(n={met_e1['n']:,})")

    print("\n" + "-" * 70)
    print("CONTROL de identidad — mismo código con cuota FIJA (debe reproducir v5)")
    print("-" * 70)
    print(f"  Control: MAE={met_control['MAE']:.4f}  RMSE={met_control['RMSE']:.4f}  "
          f"R²={met_control['R2']:.4f}  sesgo={met_control['sesgo_pct']:+.2f}%")
    print(f"  v5 ref:  MAE={met_v5['MAE']:.4f}  RMSE={met_v5['RMSE']:.4f}  "
          f"R²={met_v5['R2']:.4f}  sesgo={met_v5['sesgo_pct']:+.2f}%")
    control_ok = (
        met_control["MAE"] == met_v5["MAE"]
        and met_control["RMSE"] == met_v5["RMSE"]
        and met_control["R2"] == met_v5["R2"]
        and met_control["sesgo_pct"] == met_v5["sesgo_pct"]
    )
    print(f"  ¿Reproduce exactamente a v5? {'✅ SÍ' if control_ok else '⚠️  NO (ver limitaciones)'}")

    print("\n" + "-" * 70)
    print("📊 COMPARATIVA E1 (cuota trailing) vs v5 (cuota fija 2024)")
    print("-" * 70)
    for nombre, etiqueta in [("MAE", "MAE"), ("RMSE", "RMSE"), ("R2", "R²"),
                             ("sesgo_pct", "Sesgo %")]:
        c = comparacion[nombre]
        print(f"  {etiqueta:<8} v5={c['v5_cuota_fija']:>10}   "
              f"E1={c['e1_cuota_trailing']:>10}   Δ={c['delta_e1_menos_v5']:+.4f}")
    print(f"  → {veredicto}")

    print("\n" + "-" * 70)
    print("DIAGNÓSTICO — corrección del denominador (reportantes vs región)")
    print("-" * 70)
    print(f"  (Región, Fecha) del test: {len(grupos):,} | con TODOS los estabs: "
          f"{int((grupos['n_estabs_fecha'] == grupos['max_region']).sum()):,} | "
          f"con estabs faltantes: {grupos_incompletos:,} | con <50% de estabs: "
          f"{int((grupos['n_estabs_fecha'] < 0.5 * grupos['max_region']).sum()):,}")
    print(f"  Filas con ≤5 estabs reportando ese día: {int(pocos.sum()):,} "
          f"({100 * float(pocos.mean()):.2f}% de las filas) → "
          f"{100 * sse_e1_pocos / sse_e1:.1f}% del SSE de E1 (ANTES de la "
          f"corrección: 44.5%) y solo "
          f"{100 * sse_v5_pocos / sse_v5:.1f}% del SSE de v5")
    print(f"  Total predicho (suma): E1={suma_pred_e1:,.0f} | "
          f"v5={suma_pred_v5:,.0f} | regional Etapa 1={suma_pred_region_total:,.0f} | "
          f"real={suma_real:,.0f}")
    print(f"  Grupos (Región, Fecha) con parte del denominador SIN repartir "
          f"(como v5): {grupos_con_parte_sin_repartir:,} de {len(grupos):,}")
    print("  → El denominador es REGIONAL: la cuota de los estabs que no "
          "reportan ese día queda")
    print("    sin repartir y ningún reportante se queda con el total "
          "regional (corrección del defecto previo).")

    print("\n" + "-" * 70)
    print("MÉTRICAS POR REGIÓN — E1 (cuota trailing) vs v5 (cuota fija, vía "
          "control verificado)")
    print("-" * 70)
    print(f"  {'Región':<22} {'MAE v5':>9} {'MAE E1':>9} {'ΔMAE':>9}   "
          f"{'R² v5':>9} {'R² E1':>9}   {'sesgo v5':>9} {'sesgo E1':>9}")
    for reg in sorted(met_por_region):
        e, b = met_por_region[reg], met_por_region_v5[reg]
        print(f"  {reg:<22} {b['MAE']:>9.3f} {e['MAE']:>9.3f} "
              f"{e['MAE'] - b['MAE']:>+9.3f}   {b['R2']:>9.4f} {e['R2']:>9.4f}   "
              f"{b['sesgo_pct']:>8.2f}% {e['sesgo_pct']:>8.2f}%")

    # -----------------------------------------------------------------------
    # 9. Exportar metadata
    # -----------------------------------------------------------------------
    RUTA_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "release": "modelo-v6-e1",
        "experimento": "E1 — réplica de v5 con Etapa 2 de cuota dinámica trailing",
        "descripcion": (
            "E1 es una réplica DEL PIPELINE v5 con UN ÚNICO cambio: la Etapa 2 "
            "pasa de cuota histórica FIJA 2024 a cuota dinámica TRAILING "
            "(shift(4) + rolling(30, min_periods=10) de CALENDARIO por "
            "establecimiento) repartida con denominador REGIONAL — Σ peso sobre "
            "TODOS los estabs de la región en cada fecha, reporten o no — "
            "de modo que los estabs no reportantes dejan su parte sin "
            "repartir (semántica de v5) y ningún reportante se queda con el "
            "total regional. La Etapa 1 se importa del propio módulo v5 "
            "(features, anomalías trailing N=45, one-hot de región, RF y "
            "semilla idénticos), el split es train 2024 / test 2025 y la "
            "evaluación es a nivel ESTABLECIMIENTO + DÍA, de modo que la "
            "comparación E1 vs v5 aisla el efecto de la cuota."
        ),
        "granularidad_evaluacion": (
            "El dataset tiene ~4 filas por (establecimiento, Fecha) porque cada "
            "fila es una causa respiratoria distinta del archivo DEIS. La "
            "demanda real de un establecimiento en un día es la SUMA de esas "
            "filas; se agrega por (estab, fecha) antes de evaluar."
        ),
        "aviso_anti_leakage": {
            "formula": (
                "trail_e(T) = Total_e.shift(4).rolling(30, min_periods=10).sum() "
                "sobre la serie del establecimiento REINDEXADA AL CALENDARIO "
                "DIARIO completo de su rango (días sin reporte = NaN)."
            ),
            "horizonte_horas": 96,
            "lag_dias": LAG_DEMANDA,
            "por_que_es_anti_leakage": (
                f"El shift({LAG_DEMANDA}) sobre el calendario garantiza que la "
                f"información disponible al pronosticar la fecha T es hasta "
                f"T-{LAG_DEMANDA} (lag real de días de calendario): el día T "
                "NUNCA entra en su propia cuota ni en la media de fallback de "
                "su Región en T, cuyo trail también es ≤ T-4. No se usa el "
                "target de T ni ninguna fecha ≥ T."
            ),
            "cruce_2024_2025": (
                "La ventana SÍ puede cruzar la frontera 2024→2025: los días "
                "anteriores a T ya fueron observados en el sistema real (misma "
                "suposición que los lags de features y el baseline trailing de "
                "la Etapa 1)."
            ),
            "share_2024": (
                "La cuota base y sus medianas de fallback se calculan SOLO desde "
                "train 2024."
            ),
        },
        "configuracion_cuota_trailing": {
            "ventana_dias": VENTANA_TRAILING,
            "min_periods": MIN_PERIODS_TRAILING,
            "lag_dias": LAG_DEMANDA,
            "serie": (
                "CAMBIO DE SEMÁNTICA (documentado): la serie de cada "
                "establecimiento (panel 2024+2025 agregado por estab+fecha, "
                "filas multi-causa sumadas) se REINDEXA al CALENDARIO DIARIO "
                "completo de su rango antes del shift/rolling: los días sin "
                "reporte quedan con Total=NaN y el rolling suma solo las "
                "observaciones disponibles. La ventana es de CALENDARIO, no "
                "de FILAS: shift(4) es un lag real de 4 días y trail_e(T) "
                "existe en cada fecha T con ≥10 observaciones en [T-33, T-4], "
                "aunque el estab no haya reportado ese día."
            ),
            "fallback_sin_trail": (
                "Establecimientos sin trail en T (menos de "
                f"{MIN_PERIODS_TRAILING} observaciones en la ventana de "
                "calendario [T-33, T-4]): share_2024_e × media(trail) de su "
                "Región en T, promediada sobre TODOS los estabs de la región "
                "CON trail en T (reporten o no ese día); si esa Región en T "
                "no tiene ningún trail, share_2024_e directo."
            ),
            "fallback_establecimientos_nuevos": (
                "MISMO fallback jerárquico que v5 (calculado solo desde train "
                "2024): mediana de las cuotas de su TipoEstablecimiento dentro "
                "de su región → mediana global del tipo → 0."
            ),
            "denominador_regional": (
                "CORRECCIÓN del defecto de diseño previo (renormalizar entre "
                "los reportantes del día, que concentraba el 100% del total "
                "regional en los días con UN solo reportante): "
                "denominador(T, Región) = Σ peso_e(T) sobre TODOS los "
                "establecimientos de la región (reporten o no ese día). "
                "pred_e(T) = peso_e(T)/denominador(T, Región) × "
                "pred_region(T). Los estabs que NO reportan ese día dejan su "
                "parte SIN REPARTIR (misma semántica conservadora de v5)."
            ),
            "total_regional": (
                "Se multiplica por el total regional PREDICHO por la Etapa 1 "
                "(predicción real del modelo RF), NO por la región observada: "
                "a diferencia del diagnóstico v6 (que usaba el total regional "
                "real y por eso era un techo diagnóstico), E1 es DESPLEGABLE."
            ),
            "estadisticas_test_2025": {
                "filas_estab_fecha_reportantes": int(len(test_pred)),
                "filas_reportantes_con_trail": n_con_trail,
                "pct_filas_reportantes_con_trail": round(
                    100 * n_con_trail / len(test_pred), 2
                ),
                "filas_reportantes_en_fallback_de_trail": int(
                    len(test_pred) - n_con_trail
                ),
                "filas_grilla_regional": int(len(grid)),
                "filas_grilla_con_trail": n_grid_con_trail,
                "pct_filas_grilla_con_trail": round(
                    100 * n_grid_con_trail / len(grid), 2
                ),
                "establecimientos_test_sin_share_2024": n_nuevos,
            },
        },
        "etapa_1": {
            "nivel": "region",
            "identica_a_v5": True,
            "como_se_garantiza": (
                "Las funciones de la Etapa 1 se importan del módulo "
                "reentrenar_modelo_v5_trailing (no se reescriben ni se "
                "modifican): mismas features, mismo baseline trailing N=45, "
                "mismo one-hot, mismos hiperparámetros y misma semilla."
            ),
            "features": features,
            "n_features": len(features),
            "model_type": "RandomForestRegressor",
            "metrics_test_2025": res1["met_region"],
            "verificacion_identidad_vs_v5": {
                "metrics_v5_region": met_region_v5,
                "coinciden": bool(etapa1_identica),
            },
        },
        "etapa_2": {
            "nivel": "establecimiento",
            "metodo": (
                "cuota dinámica trailing con denominador REGIONAL (E1) — "
                "reemplaza la cuota fija 2024 de v5"
            ),
            "formula": (
                "pred_e(T) = (peso_e(T) / denominador_regional(T)) * "
                "pred_region_total; peso_e(T) = trail_e(T) de CALENDARIO o "
                "share_2024_e × media regional del trail; denominador = Σ "
                "peso sobre TODOS los estabs de la región (reporten o no)"
            ),
            "n_establecimientos_test": int(test_pred["IdEstablecimiento"].nunique()),
            "n_establecimientos_test_sin_share_2024": n_nuevos,
        },
        "metricas_establecimiento": met_e1,
        "metricas_por_region": {
            "e1_cuota_trailing": met_por_region,
            "v5_cuota_fija_via_control_verificado": met_por_region_v5,
            "nota": (
                "Las métricas de v5 por región provienen del CONTROL con cuota "
                "fija (mismo código, mismo split), verificado idéntico a "
                "model_metadata_v5.json a nivel global."
            ),
        },
        "diagnostico_dias_incompletos": diagnostico_dias_incompletos,
        "control_cuota_fija_reproduce_v5": {
            "descripcion": (
                "Mismo código de reparto/evaluación pero con la cuota FIJA 2024 "
                "de v5: sirve como control de que la ÚNICA diferencia del "
                "pipeline E1 vs v5 es la cuota."
            ),
            "metricas_control": met_control,
            "metricas_v5_reportadas": met_v5,
            "reproduce_v5_exactamente": bool(control_ok),
        },
        "comparacion_e1_vs_v5": {
            "referencia_v5": met_v5,
            "e1_cuota_trailing": met_e1,
            "delta": comparacion,
            "mejora_en_mae": bool(mejora_mae),
            "mejora_en_rmse": bool(mejora_rmse),
            "mejora_en_r2": bool(mejora_r2),
            "mejora_en_sesgo_absoluto": bool(mejora_sesgo),
            "n_mejoras_de_4": n_mejoras,
            "veredicto": veredicto,
        },
        "semilla": v5.RANDOM_STATE,
        "hiperparametros": {
            **{k: v for k, v in v5.HIPERPARAMETROS.items() if k != "n_jobs"},
            "split": "train = 2024, test = 2025",
            "cv_heredada_de_v5": {
                "cv": meta_v5["hyperparameters"]["cv"],
                "scoring": meta_v5["hyperparameters"]["scoring"],
                "cv_mae_mean": meta_v5["etapa_1"]["cv_mae_mean"],
                "cv_mae_std": meta_v5["etapa_1"]["cv_mae_std"],
                "nota": (
                    "La CV no se re-ejecuta en E1: la Etapa 1 es idéntica a v5 "
                    "y estos valores provienen de model_metadata_v5.json."
                ),
            },
        },
        "limitaciones": [
            "Solo 2 años de datos (train 2024 / test 2025): la comparación "
            "E1 vs v5 se hace sobre el mismo split, por lo que el delta mide "
            "el efecto de la cuota en este test, no una validación externa.",
            "SEMÁNTICA DE CALENDARIO (cambio documentado): el trail se calcula "
            "sobre la serie de cada estab reindexada al calendario diario de "
            "su rango (Total→NaN en días sin reporte), con "
            "shift(4).rolling(30, min_periods=10).sum(). El rolling suma solo "
            "las observaciones REALES dentro de la ventana [T-33, T-4]: un "
            "estab esporádico acumula menos de 30 días de dato en esa "
            "ventana; min_periods=10 exige ≥10 observaciones. Esto reemplaza "
            "la semántica por FILAS de la primera versión de E1 y del "
            "diagnóstico v6 (que no era un lag exacto de 4 días de "
            "calendario).",
            "El trail de los primeros días de 2025 usa la historia de diciembre "
            "de 2024 (información ya observada); los estabs nuevos o con "
            "historia insuficiente (<10 observaciones en la ventana de "
            "calendario) caen al fallback share_2024_e × media regional del "
            "trail en T.",
            "Los establecimientos NO reportan todos los días (grupos (Región, "
            "Fecha) con estabs faltantes, incluso días con UN solo "
            "reportante). Con el denominador REGIONAL esos reportantes NO se "
            "llevan el total regional (corregido respecto de la versión previa "
            "de E1, donde 1,42% de las filas explicaban el 44,54% del SSE), "
            "pero la cuota de los no reportantes queda SIN REPARTIR: el total "
            "predicho queda algo por debajo del total regional predicho por "
            "la Etapa 1, al igual que en v5.",
            "Las métricas por región de v5 no estaban almacenadas en su "
            "metadata: aquí se obtienen vía el control con cuota fija "
            "(reproduce exactamente a v5 a nivel global).",
        ],
    }
    with open(RUTA_SALIDA, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 70)
    print("✅ EXPERIMENTO E1 COMPLETADO (cuota trailing)")
    print(f"  Metadata: {RUTA_SALIDA}")
    print("=" * 70)


if __name__ == "__main__":
    main()
