from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.db.session import Base

class Establishment(Base):
    __tablename__ = "establecimientos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column("name", String, nullable=False)
    comuna = Column("commune", String, nullable=False)
    region = Column(String, nullable=False)
    capacidad_camas = Column("bed_capacity", Integer, default=50)

    ingresos = relationship("DailyIntake", back_populates="establecimiento")
