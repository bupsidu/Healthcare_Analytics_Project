from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Motor de conexión a PostgreSQL especificando client_encoding utf8 para evitar errores de tildes en Windows
engine = create_engine(
    settings.database_url,
    client_encoding="utf8",
    connect_args={"options": "-c client_encoding=utf8"},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
