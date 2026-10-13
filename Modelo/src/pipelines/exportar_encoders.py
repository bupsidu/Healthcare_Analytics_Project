"""
Exportación de encoders — Sistema MINSAL
=========================================

Reentrena los encoders exactamente como en el notebook de modelado
y los exporta a models/encoders.joblib para que la API pueda
traducir datos crudos (texto) al formato numérico del modelo.

Nota: en el notebook original se reutilizaba la misma variable `le`,
por lo que el encoder de Región quedó sobreescrito por el de Tipo.
Aquí se reentrenan por separado sobre el mismo dataset para conservarlos.

Salida: models/encoders.joblib
"""

from pathlib import Path

import joblib
import pandas as pd
from sklearn.preprocessing import LabelEncoder

BASE_DIR = Path("/Users/naferyh/Desktop/Proyectos/Proyecto de título")
PROCESSED = BASE_DIR / "data" / "processed" / "df_modelo.parquet"
OUT_PATH = BASE_DIR / "models" / "encoders.joblib"

# Mapeo ordinal de temperatura (idéntico al notebook)
TEMP_ORDER = {
    "Muy Frío": 0,
    "Frío": 1,
    "Templado": 2,
    "Cálido": 3,
    "Caluroso": 4,
    "None": -1,
}

print("Cargando dataset procesado...")
df = pd.read_parquet(PROCESSED)

# Reentrenar encoder de Región
le_region = LabelEncoder()
le_region.fit(df["Region"].astype(str))

# Reentrenar encoder de TipoEstablecimiento
le_tipo = LabelEncoder()
le_tipo.fit(df["TipoEstablecimiento"].astype(str))

encoders = {
    "temp_order": TEMP_ORDER,
    "le_region": le_region,
    "le_tipo": le_tipo,
}

joblib.dump(encoders, OUT_PATH)

print(f"✅ Encoders exportados a: {OUT_PATH}")
print(f"   Regiones: {list(le_region.classes_)}")
print(f"   Tipos:    {list(le_tipo.classes_)}")
