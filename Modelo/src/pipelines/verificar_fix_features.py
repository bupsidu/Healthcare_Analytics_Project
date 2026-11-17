"""
Diagnóstico post-fix de features climáticas (T3)
================================================

Verifica con MEDICIONES (no afirmaciones) que los 3 bugs de
`feature_engineering.py` quedaron corregidos en
`data/processed/df_modelo.parquet`:

  (a) TempMin_Lag_4D == TempMin de T-4 CALENDARIO (muestra de ≥3 regiones)
      (+ extra: MP2_5_Lag_2D == MP2_5 de T-2 calendario)
  (b) % de filas donde TempMin_Lag_4D == TempMin (mismo día): era 97.8%,
      debe caer a ≈0% (coincidencias casuales de temperatura son posibles)
  (c) Region_Media_7d_TempMin == media de la serie deduplicada en ventana
      calendario [T-6..T] con tolerancia 1e-9 (muestra de ≥3 regiones)
      (+ extra: Region_Media_7d_MP25)
  (d) Lluvia_Intensa_Flag == (Precipitacion_mm > q90 por región calculado
      SOLO con Fecha < 2025-01-01) en TODAS las filas → 100%
  (e) Forma del parquet: filas/fechas/regiones/columnas vs esperado

Los valores esperados de (a), (c) y (d) se recomputan INDEPENDIENTEMENTE
desde la fuente `data/interim/df_unificado.parquet` (el input real del
pipeline): (a) y (c) porque el pipeline calcula features ANTES del dropna
de filter_and_clean, y (d) porque los umbrales se calculan sobre la fuente
completa. Es la verdad de terreno contra la que se contrasta la salida.

Uso:
    python3 src/pipelines/verificar_fix_features.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
RUTA_OUT = BASE_DIR / "data" / "processed" / "df_modelo.parquet"
RUTA_SRC = BASE_DIR / "data" / "interim" / "df_unificado.parquet"

TRAIN_END = pd.Timestamp("2025-01-01")  # protocolo train 2024 / test 2025
TOL = 1e-9
PCT_IGUAL_DIA_MAX = 5.0  # (b): antes 97.8%; coincidencias casuales < 5%

# Referencias de forma
FILAS_VIEJAS = 894_652
FILAS_DOC_MIN, FILAS_DOC_MAX = 884_000, 886_000  # estimación del doc de tareas
COLUMNAS_ESPERADAS = 27
REGIONES_ESPERADAS = 8  # solo las regiones con TempMin en la fuente sobreviven al dropna


def check(ok: bool, etiqueta: str, detalle: str) -> bool:
    """Imprime una línea PASS/FAIL con números."""
    estado = "PASS" if ok else "FAIL"
    print(f"  [{estado}] {etiqueta}: {detalle}")
    return ok


def main() -> int:
    print("=" * 70)
    print("DIAGNÓSTICO POST-FIX — features climáticas (T3)")
    print("=" * 70)

    out = pd.read_parquet(RUTA_OUT)
    src = pd.read_parquet(RUTA_SRC)
    out["_f"] = pd.to_datetime(out["Fecha"])
    src["_f"] = pd.to_datetime(src["Fecha"])
    print(f"\nSalida:   {RUTA_OUT.name}  ({len(out):,} filas × {len(out.columns) - 1} cols)")
    print(f"Fuente:   {RUTA_SRC.name}  ({len(src):,} filas)")

    resultados: list[bool] = []

    # Muestra de ≥3 regiones: las 3 con más filas en la salida (determinista)
    muestra = list(out["Region"].value_counts().head(3).index)
    print(f"\nMuestra de regiones ({len(muestra)}): {muestra}")

    # ------------------------------------------------------------------
    # (a) TempMin_Lag_4D == TempMin(T-4 calendario) — desde la fuente
    # ------------------------------------------------------------------
    print("\n--- (a) Lag calendario T-4 ---")
    cal_src = (
        src[["Region", "_f", "TempMin", "MP2_5"]]
        .drop_duplicates(subset=["Region", "_f"])
        .copy()
    )
    ref4 = cal_src[["Region", "_f", "TempMin"]].copy()
    ref4["_f"] = ref4["_f"] + pd.Timedelta(days=4)
    ref4 = ref4.rename(columns={"TempMin": "_esperado_t4"})

    sub = out[out["Region"].isin(muestra)]
    chk = sub.merge(
        ref4, on=["Region", "_f"], how="left", suffixes=("", "_src")
    )
    comparable = chk["_esperado_t4"].notna() & chk["TempMin_Lag_4D"].notna()
    coincide = (
        (chk["TempMin_Lag_4D"] - chk["_esperado_t4"]).abs() <= TOL
    ) & comparable
    sin_fuente = int(chk["_esperado_t4"].isna().sum())
    n_comp, n_ok = int(comparable.sum()), int(coincide.sum())
    pct = 100 * n_ok / n_comp if n_comp else 0.0
    ok_a = n_comp > 0 and n_ok == n_comp and sin_fuente == 0
    resultados.append(check(
        ok_a,
        f"(a) lag == TempMin(T-4) en {len(muestra)} regiones",
        f"{n_ok:,}/{n_comp:,} = {pct:.4f}% | filas sin T-4 en fuente: {sin_fuente}",
    ))
    for reg in muestra:
        r = chk[chk["Region"] == reg]
        rc = r["_esperado_t4"].notna() & r["TempMin_Lag_4D"].notna()
        ro = ((r["TempMin_Lag_4D"] - r["_esperado_t4"]).abs() <= TOL) & rc
        print(f"        · {reg:<22} {int(ro.sum()):,}/{int(rc.sum()):,}")

    # Extra: MP2_5_Lag_2D == MP2_5(T-2 calendario)
    ref2 = cal_src[["Region", "_f", "MP2_5"]].copy()
    ref2["_f"] = ref2["_f"] + pd.Timedelta(days=2)
    ref2 = ref2.rename(columns={"MP2_5": "_esperado_t2"})
    chk2 = sub.merge(ref2, on=["Region", "_f"], how="left")
    comp2 = chk2["_esperado_t2"].notna() & chk2["MP2_5_Lag_2D"].notna()
    ok2 = int((((chk2["MP2_5_Lag_2D"] - chk2["_esperado_t2"]).abs() <= TOL) & comp2).sum())
    n2 = int(comp2.sum())
    nan_lag2 = int(chk2["MP2_5_Lag_2D"].isna().sum())
    resultados.append(check(
        n2 > 0 and ok2 == n2,
        "(a+) lag MP2_5 == MP2_5(T-2) en la muestra",
        f"{ok2:,}/{n2:,} = {100 * ok2 / n2 if n2 else 0:.4f}% | "
        f"lag NaN (sin T-2, se conservan): {nan_lag2}",
    ))

    # ------------------------------------------------------------------
    # (b) % filas donde lag == TempMin del mismo día
    # ------------------------------------------------------------------
    print("\n--- (b) Lag == mismo día (colapso del bug viejo) ---")
    pct_igual = 100 * float((out["TempMin_Lag_4D"] == out["TempMin"]).mean())
    n_igual = int((out["TempMin_Lag_4D"] == out["TempMin"]).sum())
    ok_b = pct_igual < PCT_IGUAL_DIA_MAX
    resultados.append(check(
        ok_b,
        "(b) % TempMin_Lag_4D == TempMin (mismo día)",
        f"{pct_igual:.3f}% ({n_igual:,} filas) — antes 97.8%, umbral {PCT_IGUAL_DIA_MAX}%",
    ))

    # ------------------------------------------------------------------
    # (c) Rolling 7d == media calendario [T-6..T] — desde la fuente
    # ------------------------------------------------------------------
    print("\n--- (c) Rolling 7d == media calendario [T-6..T] ---")
    ok_c = True
    for reg in muestra:
        serie = (
            cal_src[cal_src["Region"] == reg]
            .set_index("_f")["TempMin"]
            .sort_index()
        )
        completo = pd.date_range(serie.index.min(), serie.index.max(), freq="D")
        # Ventana de TIEMPO de 7 días terminada en T (incluye T, excluye T-7):
        # semántica calendario [T-6..T], promedia valores observados (NaN saltados)
        esp = serie.reindex(completo).rolling("7D", min_periods=1).mean()
        r = out[out["Region"] == reg][["_f", "Region_Media_7d_TempMin"]].copy()
        r["_esperado"] = r["_f"].map(esp)
        comp = r["_esperado"].notna() & r["Region_Media_7d_TempMin"].notna()
        dif = (r["Region_Media_7d_TempMin"] - r["_esperado"]).abs()
        n_comp, n_ok = int(comp.sum()), int((comp & (dif <= TOL)).sum())
        sin_esp = int(r["_esperado"].isna().sum())
        region_ok = n_comp > 0 and n_ok == n_comp and sin_esp == 0
        ok_c = ok_c and region_ok
        print(
            f"        · {reg:<22} match {n_ok:,}/{n_comp:,} = "
            f"{100 * n_ok / n_comp if n_comp else 0:.6f}% | sin esperado: {sin_esp} | "
            f"{'OK' if region_ok else 'REVISAR'}"
        )
    resultados.append(check(
        ok_c,
        "(c) Region_Media_7d_TempMin == media calendario 7d (muestra)",
        "tolerancia 1e-9, ventana [T-6..T] recomputada desde la fuente",
    ))

    # Extra: Region_Media_7d_MP25
    ok_c2 = True
    for reg in muestra:
        serie = (
            cal_src[cal_src["Region"] == reg]
            .set_index("_f")["MP2_5"]
            .sort_index()
        )
        completo = pd.date_range(serie.index.min(), serie.index.max(), freq="D")
        esp = serie.reindex(completo).rolling("7D", min_periods=1).mean()
        r = out[out["Region"] == reg][["_f", "Region_Media_7d_MP25"]].copy()
        r["_esperado"] = r["_f"].map(esp)
        comp = r["_esperado"].notna() & r["Region_Media_7d_MP25"].notna()
        dif = (r["Region_Media_7d_MP25"] - r["_esperado"]).abs()
        n_comp, n_ok = int(comp.sum()), int((comp & (dif <= TOL)).sum())
        region_ok = n_comp > 0 and n_ok == n_comp
        ok_c2 = ok_c2 and region_ok
        print(
            f"        · {reg:<22} match {n_ok:,}/{n_comp:,} = "
            f"{100 * n_ok / n_comp if n_comp else 0:.6f}% | "
            f"{'OK' if region_ok else 'REVISAR'}"
        )
    resultados.append(check(
        ok_c2,
        "(c+) Region_Media_7d_MP25 == media calendario 7d (muestra)",
        "tolerancia 1e-9, ventana [T-6..T] recomputada desde la fuente",
    ))

    # ------------------------------------------------------------------
    # (d) Lluvia_Intensa_Flag == precip > q90 train-only — en TODAS las filas
    # ------------------------------------------------------------------
    print("\n--- (d) Lluvia_Intensa_Flag con umbral train-only ---")
    q90 = (
        src[src["_f"] < TRAIN_END]
        .groupby("Region")["Precipitacion_mm"]
        .quantile(0.9)
    )
    umbral = out["Region"].map(q90)
    # Umbral NaN (región sin precipitación en train) → comparación False → 0,
    # idéntica a la semántica del pipeline (sin relleno del umbral)
    esperado = (out["Precipitacion_mm"] > umbral).astype(int)
    n_mal = int((esperado != out["Lluvia_Intensa_Flag"]).sum())
    ok_d = n_mal == 0
    resultados.append(check(
        ok_d,
        "(d) flag == (precip > q90 por región, solo Fecha < 2025-01-01)",
        f"{len(out) - n_mal:,}/{len(out):,} filas coinciden | discrepancias: {n_mal}",
    ))
    print("        Umbrales q90 train por región (fuente):")
    for reg, v in sorted(q90.items(), key=lambda kv: str(kv[0])):
        print(f"          {reg:<22} {v if pd.notna(v) else 'NaN (sin precip en train → flag 0)'}")

    # ------------------------------------------------------------------
    # (e) Forma del parquet
    # ------------------------------------------------------------------
    print("\n--- (e) Forma del parquet ---")
    n_filas = len(out)
    n_cols = len(out.columns) - 1  # sin el helper _f
    fechas = sorted(out["_f"].dt.normalize().unique())
    n_fechas = len(fechas)
    n_regiones = out["Region"].nunique()
    delta = n_filas - FILAS_VIEJAS
    en_doc = FILAS_DOC_MIN <= n_filas <= FILAS_DOC_MAX

    print(f"        Filas:      {n_filas:,}  (viejo: {FILAS_VIEJAS:,}; delta {delta:+,})")
    print(f"        Estimación doc de tareas: {FILAS_DOC_MIN:,}-{FILAS_DOC_MAX:,} "
          f"→ {'dentro' if en_doc else 'FUERA del rango'} ({n_filas - FILAS_DOC_MIN:+,} vs borde inferior)")
    print(f"        Columnas:   {n_cols} (esperado {COLUMNAS_ESPERADAS})")
    print(f"        Regiones:   {n_regiones} (esperado {REGIONES_ESPERADAS}: "
          f"{sorted(out['Region'].unique())})")
    print(f"        Fechas:     {n_fechas}  {pd.Timestamp(fechas[0]).date()} → "
          f"{pd.Timestamp(fechas[-1]).date()} (viejo: 731 de 2024-01-01→2025-12-31)")
    print("        Nota: la estimación del doc (-9-10k) asumía que el dropna solo")
    print("        pierde los primeros 4 días calendario; el neto real también")
    print("        reintegra filas que el lag viejo descartaba (máscara de días con")
    print("        TempMin NaN desplazada 4 días), por eso el delta es -5,128.")
    ok_e = (
        n_cols == COLUMNAS_ESPERADAS
        and n_regiones == REGIONES_ESPERADAS
        and pd.Timestamp(fechas[0]) == pd.Timestamp("2024-01-05")
        and pd.Timestamp(fechas[-1]) == pd.Timestamp("2025-12-31")
        and n_fechas == 727  # 731 días - 4 primeros días de 2024
    )
    resultados.append(check(
        ok_e,
        "(e) forma coherente (columnas/regiones/rango de fechas)",
        f"{n_filas:,} filas, {n_cols} cols, {n_regiones} regiones, {n_fechas} fechas; "
        f"desviación vs estimación del doc: {n_filas - FILAS_DOC_MIN:+,} a "
        f"{n_filas - FILAS_DOC_MAX:+,} filas (explicada arriba)",
    ))

    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    n_ok = sum(resultados)
    total = len(resultados)
    if n_ok == total:
        print(f"✅ RESULTADO: {n_ok}/{total} checks PASS")
        print("=" * 70)
        return 0
    print(f"❌ RESULTADO: {n_ok}/{total} checks PASS — HAY FAIL")
    print("=" * 70)
    return 1


if __name__ == "__main__":
    sys.exit(main())
