import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

#carga

# Cargar variables de entorno desde el archivo .env
load_dotenv()

DB_HOST = os.getenv("PGHOST")
DB_PORT = os.getenv("PGPORT")
DB_NAME = os.getenv("PGDATABASE")
DB_USER = os.getenv("PGUSER")
DB_PASSWORD = os.getenv("PGPASSWORD")

SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(SQLALCHEMY_DATABASE_URL)

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("Conexión exitosa a la base de datos")
except Exception as e:
    print(f"Error al conectar a la base de datos: {e}")
    
    
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
