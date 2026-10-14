from sqlalchemy import Boolean, CheckConstraint, Column, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.orm import relationship
from app.db.session import Base

class Establishment(Base):
    __tablename__ = "establecimientos"
    __table_args__ = (
        UniqueConstraint("id_establecimiento", name="uq_establecimientos_codigo_deis"),
        CheckConstraint("tipo IN ('CEAR', 'Hospital', 'SAPU', 'SAR', 'SUR')", name="ck_establecimientos_tipo"),
    )

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column("name", String, nullable=False)
    comuna = Column("commune", String, nullable=False)
    region = Column(String, nullable=False)
    capacidad_camas = Column("bed_capacity", Integer, default=50)
    # Son opcionales en la base actual mientras se completa el catálogo real.
    id_establecimiento = Column(Text, nullable=True)
    tipo = Column(Text, nullable=True)
    activo = Column(Boolean, nullable=False, server_default=true())

    ingresos = relationship("DailyIntake", back_populates="establecimiento")
