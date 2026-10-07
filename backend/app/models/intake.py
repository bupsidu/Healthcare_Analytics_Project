from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship
from app.db.session import Base


class DailyIntake(Base):
    __tablename__ = "ingresos_diarios"
    __table_args__ = (
        CheckConstraint("respiratory_cases >= 0", name="ck_ingresos_casos_no_negativos"),
        CheckConstraint(
            "age_group IN ('Infantil', 'Adulto', 'Adulto Mayor', 'General')",
            name="ck_ingresos_grupo_etario",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Los atributos conservan el contrato JSON actual; las columnas SQL usan inglés.
    fecha = Column("date", Date, nullable=False, index=True)
    establecimiento_id = Column("establishment_id", Integer, ForeignKey("establecimientos.id"), nullable=False)
    casos_respiratorios = Column("respiratory_cases", Integer, nullable=False)
    grupo_etario = Column("age_group", String(30), nullable=False, default="General")
    created_by_user_id = Column(Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    establecimiento = relationship("Establishment", back_populates="ingresos")
    creado_por = relationship("User", back_populates="ingresos_creados")
