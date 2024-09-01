from fastapi import FastAPI
from routes import auth

app = FastAPI()

# Incluir las rutas de auth
app.include_router(auth.router)

@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI application CoffeeTech!"}
