from fastapi import FastAPI
from endpoints import auth
from dataBase import engine
from models.user import Base

# Crear todas las tablas
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Incluir las rutas de auth
app.include_router(auth.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI application CoffeeTech!"}
