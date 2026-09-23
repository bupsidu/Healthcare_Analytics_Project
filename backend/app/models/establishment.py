from sqlalchemy import Column, Integer, String
from app.db.session import Base

class Establishment(Base):
    __tablename__ = "establecimientos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    comuna = Column(String, nullable=False)
    region = Column(String, nullable=False)
    capacidad_camas = Column(Integer, default=50)
