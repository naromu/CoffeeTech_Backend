from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from models.models import Farm, UserRoleFarm, User, UnitOfMeasure, Role, Status, StatusType, Permission, RolePermission, Invitation, Plot, CoffeeVariety
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import Any, Dict, List
from utils.response import session_token_invalid_response
from utils.response import create_response
from utils.status import get_status

router = APIRouter()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modelos Pydantic para las solicitudes y respuestas
class CreatePlotRequest(BaseModel):
    name: str = Field(..., max_length=100)
    coffee_variety_name: str
    latitude: str
    longitude: str
    altitude: str
    farm_id: int

class UpdatePlotGeneralInfoRequest(BaseModel):
    plot_id: int
    name: str = Field(..., max_length=100)
    coffee_variety_name: str

class UpdatePlotLocationRequest(BaseModel):
    plot_id: int
    latitude: str
    longitude: str
    altitude: str


# Endpoint para crear un lote
@router.post("/create-plot")
def create_plot(request: CreatePlotRequest, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # Obtener los estados "Activo" para Farm y UserRoleFarm
    active_farm_status = get_status(db, "Activo", "Farm")
    if not active_farm_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Farm'")
        return create_response("error", "No se encontró el estado 'Activo' para el tipo 'Farm'", status_code=400)

    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'user_role_farm'")
        return create_response("error", "No se encontró el estado 'Activo' para el tipo 'user_role_farm'", status_code=400)

    # Obtener el estado "Activo" para Plot
    active_plot_status = get_status(db, "Activo", "Plot")
    if not active_plot_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Plot'")
        return create_response("error", "No se encontró el estado 'Activo' para el tipo 'Plot'", status_code=400)

    # Verificar que la finca existe y está activa
    farm = db.query(Farm).filter(Farm.farm_id == request.farm_id, Farm.status_id == active_farm_status.status_id).first()
    if not farm:
        logger.warning("La finca con ID %s no existe o no está activa", request.farm_id)
        return create_response("error", "La finca no existe o no está activa")

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == request.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", request.farm_id)
        return create_response("error", "No tienes permiso para agregar un lote en esta finca")

    # Verificar permiso 'add_plot'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "add_plot"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para agregar un lote en la finca")
        return create_response("error", "No tienes permiso para agregar un lote en esta finca")

    # Validar el nombre del lote
    if not request.name or not request.name.strip():
        logger.warning("El nombre del lote no puede estar vacío o solo contener espacios")
        return create_response("error", "El nombre del lote no puede estar vacío")
    if len(request.name) > 100:
        logger.warning("El nombre del lote es demasiado largo")
        return create_response("error", "El nombre del lote no puede tener más de 100 caracteres")

    # Verificar si ya existe un lote con el mismo nombre en la finca
    existing_plot = db.query(Plot).filter(
        Plot.name == request.name,
        Plot.farm_id == request.farm_id,
        Plot.status_id == active_plot_status.status_id  # Corregido a active_plot_status
    ).first()
    if existing_plot:
        logger.warning("Ya existe un lote con el nombre '%s' en la finca con ID %s", request.name, request.farm_id)
        return create_response("error", f"Ya existe un lote con el nombre '{request.name}' en esta finca")

    # Obtener la variedad de café
    coffee_variety = db.query(CoffeeVariety).filter(CoffeeVariety.name == request.coffee_variety_name).first()
    if not coffee_variety:
        logger.warning("La variedad de café '%s' no existe", request.coffee_variety_name)
        return create_response("error", f"La variedad de café '{request.coffee_variety_name}' no existe")

    # Crear el lote
    try:
        new_plot = Plot(
            name=request.name,
            coffee_variety_id=coffee_variety.coffee_variety_id,
            latitude=request.latitude,
            longitude=request.longitude,
            altitude=request.altitude,
            farm_id=request.farm_id,
            status_id=active_plot_status.status_id
        )
        db.add(new_plot)
        db.commit()
        db.refresh(new_plot)
        logger.info("Lote creado exitosamente con ID: %s", new_plot.plot_id)
        return create_response("success", "Lote creado correctamente", {
            "plot_id": new_plot.plot_id,
            "name": new_plot.name,
            "coffee_variety_name": coffee_variety.name,
            "latitude": new_plot.latitude,
            "longitude": new_plot.longitude,
            "altitude": new_plot.altitude,
            "farm_id": new_plot.farm_id
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al crear el lote: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al crear el lote: {str(e)}")

# Endpoint para actualizar información general del lote
@router.post("/update-plot-general-info")
def update_plot_general_info(request: UpdatePlotGeneralInfoRequest, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener el estado "Activo" para Plot
    active_plot_status = get_status(db, "Activo", "Plot")
    if not active_plot_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Plot'")
        return create_response("error", "No se encontró el estado 'Activo' para el tipo 'Plot'", status_code=400)

    # Obtener el lote
    plot = db.query(Plot).filter(Plot.plot_id == request.plot_id, Plot.status_id == active_plot_status.status_id).first()
    if not plot:
        logger.warning("El lote con ID %s no existe o no está activo", request.plot_id)
        return create_response("error", "El lote no existe o no está activo")

    # Obtener la finca asociada al lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe")

    # Obtener el estado "Activo" para UserRoleFarm
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'user_role_farm'")
        return create_response("error", "No se encontró el estado 'Activo' para el tipo 'user_role_farm'", status_code=400)

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm.farm_id)
        return create_response("error", "No tienes permiso para editar un lote en esta finca")

    # Verificar permiso 'edit_plot'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "edit_plot"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para editar el lote en la finca")
        return create_response("error", "No tienes permiso para editar un lote en esta finca")

    # Validar el nombre del lote
    if not request.name or not request.name.strip():
        logger.warning("El nombre del lote no puede estar vacío o solo contener espacios")
        return create_response("error", "El nombre del lote no puede estar vacío")
    if len(request.name) > 100:
        logger.warning("El nombre del lote es demasiado largo")
        return create_response("error", "El nombre del lote no puede tener más de 100 caracteres")

    # Verificar si ya existe un lote con el mismo nombre en la finca
    existing_plot = db.query(Plot).filter(
        Plot.name == request.name,
        Plot.farm_id == farm.farm_id,
        Plot.plot_id != request.plot_id,
        Plot.status_id == active_plot_status.status_id  # Aseguramos que sea el estado activo del lote
    ).first()
    if existing_plot:
        logger.warning("Ya existe un lote con el nombre '%s' en la finca con ID %s", request.name, farm.farm_id)
        return create_response("error", f"Ya existe un lote con el nombre '{request.name}' en esta finca")

    # Obtener la variedad de café
    coffee_variety = db.query(CoffeeVariety).filter(CoffeeVariety.name == request.coffee_variety_name).first()
    if not coffee_variety:
        logger.warning("La variedad de café '%s' no existe", request.coffee_variety_name)
        return create_response("error", f"La variedad de café '{request.coffee_variety_name}' no existe")

    # Actualizar el lote
    try:
        plot.name = request.name
        plot.coffee_variety_id = coffee_variety.coffee_variety_id
        db.commit()
        db.refresh(plot)
        logger.info("Lote actualizado exitosamente con ID: %s", plot.plot_id)
        return create_response("success", "Información general del lote actualizada correctamente", {
            "plot_id": plot.plot_id,
            "name": plot.name,
            "coffee_variety_name": coffee_variety.name
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al actualizar el lote: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al actualizar el lote: {str(e)}")

# Endpoint para actualizar la ubicación del lote
@router.post("/update-plot-location")
def update_plot_location(request: UpdatePlotLocationRequest, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener el estado "Activo" para Plot
    active_plot_status = get_status(db, "Activo", "Plot")
    if not active_plot_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Plot'")
        return create_response("error", "No se encontró el estado 'Activo' para el tipo 'Plot'", status_code=400)

    # Obtener el lote
    plot = db.query(Plot).filter(Plot.plot_id == request.plot_id, Plot.status_id == active_plot_status.status_id).first()
    if not plot:
        logger.warning("El lote con ID %s no existe o no está activo", request.plot_id)
        return create_response("error", "El lote no existe o no está activo")

    # Obtener la finca asociada al lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe")

    # Obtener el estado "Activo" para UserRoleFarm
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'user_role_farm'")
        return create_response("error", "No se encontró el estado 'Activo' para el tipo 'user_role_farm'", status_code=400)

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm.farm_id)
        return create_response("error", "No tienes permiso para editar un lote en esta finca")

    # Verificar permiso 'edit_plot'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "edit_plot"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para editar el lote en la finca")
        return create_response("error", "No tienes permiso para editar un lote en esta finca")

    # Actualizar la ubicación del lote
    try:
        plot.latitude = request.latitude
        plot.longitude = request.longitude
        plot.altitude = request.altitude
        db.commit()
        db.refresh(plot)
        logger.info("Ubicación del lote actualizada exitosamente con ID: %s", plot.plot_id)
        return create_response("success", "Ubicación del lote actualizada correctamente", {
            "plot_id": plot.plot_id,
            "latitude": plot.latitude,
            "longitude": plot.longitude,
            "altitude": plot.altitude
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al actualizar la ubicación del lote: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al actualizar la ubicación del lote: {str(e)}")

# Endpoint para listar todos los lotes de una finca
@router.get("/list-plots/{farm_id}")
def list_plots(farm_id: int, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener los estados "Activo"
    active_farm_status = get_status(db, "Activo", "Farm")
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    active_plot_status = get_status(db, "Activo", "Plot")

    # Verificar que la finca existe y está activa
    farm = db.query(Farm).filter(Farm.farm_id == farm_id, Farm.status_id == active_farm_status.status_id).first()
    if not farm:
        logger.warning("La finca con ID %s no existe o no está activa", farm_id)
        return create_response("error", "La finca no existe o no está activa")

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm_id)
        return create_response("error", "No tienes permiso para ver los lotes de esta finca")

    # Verificar permiso 'read_plots'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "read_plots"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para ver los lotes en la finca")
        return create_response("error", "No tienes permiso para ver los lotes de esta finca")

    # Obtener todos los lotes activos de la finca
    try:
        plots = db.query(Plot).filter(
            Plot.farm_id == farm_id,
            Plot.status_id == active_plot_status.status_id
        ).all()

        plot_list = []
        for plot in plots:
            coffee_variety = db.query(CoffeeVariety).filter(
                CoffeeVariety.coffee_variety_id == plot.coffee_variety_id
            ).first()
            plot_list.append({
                "plot_id": plot.plot_id,
                "name": plot.name,
                "coffee_variety_name": coffee_variety.name if coffee_variety else None,
                "latitude": plot.latitude,
                "longitude": plot.longitude,
                "altitude": plot.altitude
            })

        return create_response("success", "Lista de lotes obtenida exitosamente", {"plots": plot_list})

    except Exception as e:
        logger.error("Error al obtener la lista de lotes: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al obtener la lista de lotes: {str(e)}")

# Endpoint para obtener la información de un lote específico
@router.get("/get-plot/{plot_id}")
def get_plot(plot_id: int, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener los estados "Activo"
    active_plot_status = get_status(db, "Activo", "Plot")
    active_farm_status = get_status(db, "Activo", "Farm")
    active_urf_status = get_status(db, "Activo", "user_role_farm")

    # Obtener el lote
    plot = db.query(Plot).filter(Plot.plot_id == plot_id, Plot.status_id == active_plot_status.status_id).first()
    if not plot:
        logger.warning("El lote con ID %s no existe o no está activo", plot_id)
        return create_response("error", "El lote no existe o no está activo")

    # Obtener la finca asociada al lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id, Farm.status_id == active_farm_status.status_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe o no está activa")
        return create_response("error", "La finca asociada al lote no existe o no está activa")

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm.farm_id)
        return create_response("error", "No tienes permiso para ver este lote")

    # Verificar permiso 'read_plots'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "read_plots"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para ver los lotes en la finca")
        return create_response("error", "No tienes permiso para ver este lote")

    # Obtener la variedad de café
    coffee_variety = db.query(CoffeeVariety).filter(
        CoffeeVariety.coffee_variety_id == plot.coffee_variety_id
    ).first()

    # Devolver la información del lote
    plot_info = {
        "plot_id": plot.plot_id,
        "name": plot.name,
        "coffee_variety_name": coffee_variety.name if coffee_variety else None,
        "latitude": plot.latitude,
        "longitude": plot.longitude,
        "altitude": plot.altitude,
        "farm_id": plot.farm_id
    }

    return create_response("success", "Lote obtenido exitosamente", {"plot": plot_info})

# Endpoint para eliminar un lote (poner en estado 'Inactivo')
@router.post("/delete-plot/{plot_id}")
def delete_plot(plot_id: int, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return create_response("error", "Token de sesión inválido o usuario no encontrado")

    # Obtener los estados "Activo" e "Inactivo" para Plot
    active_plot_status = get_status(db, "Activo", "Plot")
    inactive_plot_status = get_status(db, "Inactivo", "Plot")

    # Obtener el lote
    plot = db.query(Plot).filter(Plot.plot_id == plot_id, Plot.status_id == active_plot_status.status_id).first()
    if not plot:
        logger.warning("El lote con ID %s no existe o no está activo", plot_id)
        return create_response("error", "El lote no existe o no está activo")

    # Obtener la finca asociada al lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe")

    # Obtener el estado "Activo" para UserRoleFarm
    active_urf_status = get_status(db, "Activo", "user_role_farm")

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm.farm_id)
        return create_response("error", "No tienes permiso para eliminar este lote")

    # Verificar permiso 'delete_plot'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "delete_plot"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para eliminar el lote en la finca")
        return create_response("error", "No tienes permiso para eliminar este lote")

    # Cambiar el estado del lote a 'Inactivo'
    try:
        plot.status_id = inactive_plot_status.status_id
        db.commit()
        logger.info("Lote con ID %s puesto en estado 'Inactivo'", plot.plot_id)
        return create_response("success", "Lote eliminado correctamente")
    except Exception as e:
        db.rollback()
        logger.error("Error al eliminar el lote: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al eliminar el lote: {str(e)}")
