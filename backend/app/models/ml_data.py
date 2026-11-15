"""Tablas de preparación/auditoría creadas manualmente en PostgreSQL."""

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint, func

from app.db.session import Base


class DailyDemand(Base):
    __tablename__ = "demanda_diaria"
    __table_args__ = (CheckConstraint("total >= 0"),)

    id_establecimiento = Column(Text, ForeignKey("establecimientos.id_establecimiento"), primary_key=True)
    fecha = Column(Date, primary_key=True)
    total = Column(Integer, nullable=False)


class DailyClimate(Base):
    __tablename__ = "clima_diario"

    region = Column(Text, primary_key=True)
    fecha = Column(Date, primary_key=True)
    temp_min = Column(Numeric, nullable=True)
    temp_max = Column(Numeric, nullable=True)
    precipitacion_mm = Column(Numeric, nullable=True)


class StoredPrediction(Base):
    __tablename__ = "predicciones"
    __table_args__ = (
        CheckConstraint("pacientes_predichos >= 0"),
        UniqueConstraint("id_establecimiento", "fecha", "modelo_version"),
    )

    id = Column(Integer, primary_key=True)
    id_establecimiento = Column(Text, ForeignKey("establecimientos.id_establecimiento"), nullable=False)
    fecha = Column(Date, nullable=False)
    pacientes_predichos = Column(Integer, nullable=False)
    modelo_version = Column(Text, nullable=False)
    fecha_hora_prediccion = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
