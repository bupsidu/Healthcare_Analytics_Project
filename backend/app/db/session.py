from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Motor de conexión directo a PostgreSQL vía psycopg2
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependencia de FastAPI para inyectar la sesión de PostgreSQL en cada petición
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
