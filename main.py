from fastapi import FastAPI
from endpoints import auth
from endpoints import farm
from dataBase import engine
from models.user import Base

# Crear todas las tablas
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Incluir las rutas de auth con prefijo y etiqueta
app.include_router(auth.router, prefix="/auth", tags=["Autenticación"])

# Incluir las rutas de farm con prefijo y etiqueta
app.include_router(farm.router, prefix="/farms", tags=["Gestión de Fincas"])

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI application CoffeeTech!"}
