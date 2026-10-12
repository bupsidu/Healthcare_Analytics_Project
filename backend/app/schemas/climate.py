from datetime import datetime

from pydantic import BaseModel, Field


class ClimateHour(BaseModel):
    fecha_hora: datetime
    temperatura_c: float | None = Field(allow_inf_nan=False)
    humedad_relativa_pct: float | None = Field(ge=0, le=100, allow_inf_nan=False)
    precipitacion_mm: float | None = Field(ge=0, allow_inf_nan=False)
    viento_kmh: float | None = Field(ge=0, allow_inf_nan=False)
    pm10_ug_m3: float | None = Field(ge=0, allow_inf_nan=False)
    pm2_5_ug_m3: float | None = Field(ge=0, allow_inf_nan=False)
    ozono_ug_m3: float | None = Field(ge=0, allow_inf_nan=False)
    indice_calidad_aire_us: float | None = Field(ge=0, allow_inf_nan=False)


class ClimateResponse(BaseModel):
    latitud: float
    longitud: float
    zona_horaria: str
    horas_pronosticadas: int
    fuente: str = "Open-Meteo / CAMS"
    pronostico_horario: list[ClimateHour]
