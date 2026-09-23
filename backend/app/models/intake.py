from sqlalchemy import Column, Integer, String, Date, ForeignKey
from app.db.session import Base

class DailyIntake(Base):
    __tablename__ = "ingresos_diarios"

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(String, nullable=False, index=True) # YYYY-MM-DD
    establecimiento_id = Column(Integer, ForeignKey("establecimientos.id"), nullable=False)
    casos_respiratorios = Column(Integer, nullable=False)
    grupo_etario = Column(String, default="General") # 'Infantil', 'Adulto Mayor', 'General'
