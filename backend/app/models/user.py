from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.db.session import Base

class User(Base):
    __tablename__ = "usuarios"
    __table_args__ = (CheckConstraint("role IN ('admin', 'medico')", name="ck_usuarios_rol"),)

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    # Roles: "admin" (ve todo y administra usuarios) y "medico" (solo su hospital).
    role = Column(String(30), nullable=False, default="medico")
    is_active = Column(Boolean, nullable=False, default=True)
    # Hospital al que pertenece el usuario. NULL para los admin y para cuentas antiguas.
    establecimiento_id = Column(
        Integer, ForeignKey("establecimientos.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    ingresos_creados = relationship("DailyIntake", back_populates="creado_por")
    establecimiento = relationship("Establishment", back_populates="usuarios")
