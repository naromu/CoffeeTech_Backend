from fastapi import FastAPI
from endpoints import auth
from endpoints import utils
from endpoints import farm 
from endpoints import invitation
from endpoints import notification 
from endpoints import collaborators
from endpoints import plots
from endpoints import flowering

from dataBase import engine
from models.models import Base

# Crear todas las tablas
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Incluir las rutas de auth con prefijo y etiqueta
app.include_router(auth.router, prefix="/auth", tags=["Autenticación"])

# Incluir las rutas de utilidades (roles y unidades de medida)
app.include_router(utils.router, prefix="/utils", tags=["Utilidades"])

# Incluir las rutas de gestión de fincas
app.include_router(farm.router, prefix="/farm", tags=["Fincas"])

# Incluir las rutas de invitaciones
app.include_router(invitation.router, prefix="/invitation", tags=["Invitaciones"])


# Incluir las rutas de gestión de lotes
app.include_router(plots.router, prefix="/plots", tags=["Lotes"])

# Incluir las rutas de gestión de floraciones
app.include_router(flowering.router, prefix="/flowering", tags=["Floraciones"])

# Incluir las rutas de notificaciones
app.include_router(notification.router, prefix="/notification", tags=["Notificaciones"])

# Incluir las rutas de colaboradores
app.include_router(collaborators.router, prefix="/collaborators", tags=["Collaborators"])



# Incluir las rutas de farm con prefijo y etiqueta

@app.get("/")
def read_root():
    """
    Ruta raíz que retorna un mensaje de bienvenida.

    Returns:
        dict: Un diccionario con un mensaje de bienvenida.
    """
    return {"message": "Welcome to the FastAPI application CoffeeTech!"}
