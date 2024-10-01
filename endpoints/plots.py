from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models.models import Plot, UserRoleFarm, Permission, RolePermission, Farm, Status, StatusType, CoffeeVariety, UnitOfMeasure, Role
from utils.security import verify_session_token
from utils.status import get_status
from dataBase import get_db_session
from utils.response import create_response, session_token_invalid_response
import logging
from typing import Optional
from datetime import date

from typing import List, Dict, Any

from sqlalchemy import func



# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear el enrutador
router = APIRouter()

# Schemas
class PlotCreate(BaseModel):
    farm_id: int
    name: str = Field(..., max_length=100)
    seed_time: Optional[date]
    longitude: Optional[str] = Field(None, max_length=45)
    latitude: Optional[str] = Field(None, max_length=45)
    altitude: Optional[str] = Field(None, max_length=45)
    coffee_variety_name: str = Field(..., max_length=100)  # Cambiado de coffee_variety_id a coffee_variety_name

    class Config:
        orm_mode = True

class PlotUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    seed_time: Optional[date]
    longitude: Optional[str] = Field(None, max_length=45)
    latitude: Optional[str] = Field(None, max_length=45)
    altitude: Optional[str] = Field(None, max_length=45)
    coffee_variety_name: Optional[str] = Field(None, max_length=100)  # Cambiado de coffee_variety_id a coffee_variety_name

    class Config:
        orm_mode = True


class PlotResponse(BaseModel):
    plot_id: int
    farm_id: int
    name: str
    seed_time: Optional[date]
    longitude: Optional[str]
    latitude: Optional[str]
    altitude: Optional[str]
    coffee_variety_id: int

    class Config:
        orm_mode = True

class PlotDelete(BaseModel):
    plot_id: int

    class Config:
        orm_mode = True

# Endpoints
@router.post("/create-plot", response_model=PlotResponse)
def create_plot(plot_data: PlotCreate, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    logger.info(f"Usuario autenticado: {user.name} (ID: {user.user_id})")

    # Verificar si la finca existe
    farm = db.query(Farm).filter(Farm.farm_id == plot_data.farm_id).first()
    if not farm:
        logger.error(f"Finca con ID {plot_data.farm_id} no encontrada")
        return create_response("error", "Finca no encontrada", status_code=404)

    logger.info(f"Finca encontrada: {farm.name} (ID: {farm.farm_id})")

    # Verificar estado activo del usuario en la finca
    active_status = db.query(Status).join(StatusType).filter(
        Status.name == "Activo",
        StatusType.name == "user_role_farm"
    ).first()

    if not active_status:
        logger.error("Estado 'Activo' no encontrado para 'user_role_farm'")
        return create_response("error", "Estado 'Activo' no encontrado para 'user_role_farm'", status_code=400)

    # Verificar que el usuario esté asociado a la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.user_id == user.user_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca")
        raise HTTPException(status_code=403, detail="No tienes permiso para crear lotes en esta finca")

    # Verificar permiso para agregar lotes
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "agregar_lotes"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para crear lotes")
        raise HTTPException(status_code=403, detail="No tienes permiso para crear lotes en esta finca")

    try:
        # Validar que la variedad de café exista usando el nombre
        coffee_variety = db.query(CoffeeVariety).filter(CoffeeVariety.name == plot_data.coffee_variety_name).first()

        if not coffee_variety:
            logger.error(f"Variedad de café con nombre '{plot_data.coffee_variety_name}' no encontrada")
            raise HTTPException(status_code=404, detail="Variedad de café no encontrada")

        # Verificar si ya existe un lote con el mismo nombre en la finca
        existing_plot = db.query(Plot).filter(Plot.name == plot_data.name, Plot.farm_id == plot_data.farm_id).first()
        if existing_plot:
            logger.error(f"Ya existe un lote con el nombre '{plot_data.name}' en la finca ID {plot_data.farm_id}")
            raise HTTPException(status_code=400, detail="Ya existe un lote con ese nombre en la finca.")

        # Crear el nuevo lote
        new_plot = Plot(
            farm_id=plot_data.farm_id,
            name=plot_data.name,
            seed_time=plot_data.seed_time,
            longitude=plot_data.longitude,
            latitude=plot_data.latitude,
            altitude=plot_data.altitude,
            coffee_variety_id=coffee_variety.coffee_variety_id  # Asociar con el ID de la variedad de café
        )

        db.add(new_plot)
        db.commit()
        db.refresh(new_plot)

        logger.info(f"Lote creado con éxito: {new_plot.name} (ID: {new_plot.plot_id})")

        # Retornar respuesta de éxito
        return create_response(
            status="success",
            message="Lote creado correctamente",
            data={"plot_id": new_plot.plot_id},
            status_code=201
        )

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error al crear lote: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al crear lote: {str(e)}")



@router.post("/list-plots/{farm_id}")
def list_plots(farm_id: int, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    logger.info(f"Usuario autenticado: {user.name} (ID: {user.user_id})")

    # Obtener el estado "Activo" para user_role_farm
    active_status = get_status(db, "Activo", "user_role_farm")
    if not active_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'user_role_farm'")
        return create_response("error", "Estado 'Activo' no encontrado para user_role_farm", status_code=400)

    # Verificar si la finca existe
    farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
    if not farm:
        logger.error(f"Finca con ID {farm_id} no encontrada")
        return create_response("error", "Finca no encontrada", status_code=404)

    logger.info(f"Finca encontrada: {farm.name} (ID: {farm.farm_id})")

    # Verificar si el usuario tiene acceso a la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.status_id == active_status.status_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no está asociado o activo en la finca")
        return create_response("error", "No tienes permiso para listar los lotes de esta finca", status_code=403)

    try:
        # Listar los lotes asociados a la finca
        plots = db.query(Plot, CoffeeVariety).join(
            CoffeeVariety, Plot.coffee_variety_id == CoffeeVariety.coffee_variety_id
        ).filter(Plot.farm_id == farm_id).all()

        plot_list = []
        for plot, coffee_variety in plots:
            plot_list.append({
                "plot_id": plot.plot_id,
                "name": plot.name,
                "latitude": plot.latitude,
                "longitude": plot.longitude,
                "altitude": plot.altitude,
                "coffee_variety": coffee_variety.name,
                "seed_time": plot.seed_time
            })

        if not plot_list:
            logger.warning(f"No se encontraron lotes en la finca {farm.name}")
            return create_response("success", "No se encontraron lotes en la finca", {"plots": []})

        
        logger.info(f"Contenido de plot_list antes de retornar: {plot_list}")

        return create_response("success", "Lista de lotes obtenida exitosamente", {"plots": plot_list})

    except Exception as e:
        logger.error(f"Error al obtener la lista de lotes: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener la lista de lotes: {str(e)}")




@router.put("/edit-plot/{plot_id}", response_model=PlotResponse)
def edit_plot(
    plot_id: int,
    plot_data: PlotUpdate,  # Usamos PlotUpdate para recibir los datos de actualización
    session_token: str, 
    db: Session = Depends(get_db_session)
):
    # Verificación de sesión y usuario
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    logger.info(f"Usuario autenticado: {user.name} (ID: {user.user_id})")

    # Buscar el lote a editar
    plot = db.query(Plot).filter(Plot.plot_id == plot_id).first()
    if not plot:
        logger.error(f"Lote con ID {plot_id} no encontrado")
        return create_response("error", "Lote no encontrado", status_code=404)

    logger.info(f"Lote encontrado: {plot.name} (ID: {plot.plot_id})")

    # Verificar permisos del usuario sobre la finca asociada al lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()

    active_status = db.query(Status).join(StatusType).filter(
        Status.name == "Activo",
        StatusType.name == "user_role_farm"
    ).first()

    if not active_status:
        logger.error("Estado 'Activo' no encontrado para 'user_role_farm'")
        return create_response("error", "Estado 'Activo' no encontrado para 'user_role_farm'", status_code=400)

    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.user_id == user.user_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca")
        raise HTTPException(status_code=403, detail="No tienes permiso para editar lotes en esta finca")

    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "edit-plot"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para editar lotes")
        raise HTTPException(status_code=403, detail="No tienes permiso para editar lotes en esta finca")

    # Actualización de campos, solo si se envían en plot_data
    try:
        if plot_data.name is not None:
            existing_plot = db.query(Plot).filter(Plot.name == plot_data.name, Plot.farm_id == plot.farm_id).first()
            if existing_plot and existing_plot.plot_id != plot_id:
                logger.error(f"Ya existe un lote con el nombre '{plot_data.name}' en la finca ID {plot.farm_id}")
                raise HTTPException(status_code=400, detail="Ya existe un lote con ese nombre en la finca.")
            plot.name = plot_data.name

        if plot_data.seed_time is not None:
            plot.seed_time = plot_data.seed_time

        if plot_data.longitude is not None:
            plot.longitude = plot_data.longitude

        if plot_data.latitude is not None:
            plot.latitude = plot_data.latitude

        if plot_data.altitude is not None:
            plot.altitude = plot_data.altitude

        if plot_data.coffee_variety_name is not None:
            # Buscar la variedad de café por nombre
            coffee_variety = db.query(CoffeeVariety).filter(CoffeeVariety.name == plot_data.coffee_variety_name).first()
            if not coffee_variety:
                logger.error(f"Variedad de café con nombre '{plot_data.coffee_variety_name}' no encontrada")
                raise HTTPException(status_code=404, detail="Variedad de café no encontrada")
            plot.coffee_variety_id = coffee_variety.coffee_variety_id

        # Guardar cambios en la base de datos
        db.commit()
        db.refresh(plot)
        logger.info(f"Lote {plot.plot_id} editado con éxito")
        return create_response("success", "Lote editado correctamente", plot_id=plot.plot_id, status_code=200)

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error al editar lote: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al editar lote: {str(e)}")


@router.delete("/delete-plot/{plot_id}", response_model=dict)  # Cambia a dict o define un modelo específico
def delete_plot(
    plot_id: int,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    # Verificación de sesión y usuario
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    logger.info(f"Usuario autenticado: {user.name} (ID: {user.user_id})")

    # Buscar el lote a eliminar
    plot = db.query(Plot).filter(Plot.plot_id == plot_id).first()
    if not plot:
        logger.error(f"Lote con ID {plot_id} no encontrado")
        return create_response("error", "Lote no encontrado", status_code=404)

    logger.info(f"Lote encontrado: {plot.name} (ID: {plot.plot_id})")

    # Verificar permisos del usuario sobre la finca asociada al lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()

    active_status = db.query(Status).join(StatusType).filter(
        Status.name == "Activo",
        StatusType.name == "user_role_farm"
    ).first()

    if not active_status:
        logger.error("Estado 'Activo' no encontrado para 'user_role_farm'")
        return create_response("error", "Estado 'Activo' no encontrado para 'user_role_farm'", status_code=400)

    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.user_id == user.user_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca")
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar lotes en esta finca")

    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "delete-plot"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para eliminar lotes")
        raise HTTPException(status_code=403, detail="No tienes permiso para eliminar lotes en esta finca")

    # Eliminar el lote
    try:
        db.delete(plot)
        db.commit()
        logger.info(f"Lote {plot.plot_id} eliminado con éxito")
        return create_response("success", "Lote eliminado correctamente", plot_id=plot.plot_id, status_code=200)

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error al eliminar lote: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar lote: {str(e)}")

@router.get("/get-plot/{plot_id}")
def get_plot(plot_id: int, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    try:
        # Consultar el lote específico por su ID 
        plot_data = db.query(Plot, CoffeeVariety, Farm, UnitOfMeasure, Role).select_from(UserRoleFarm).join(
            Farm, UserRoleFarm.farm_id == Farm.farm_id
        ).join(
            Plot, Plot.farm_id == Farm.farm_id
        ).join(
            CoffeeVariety, Plot.coffee_variety_id == CoffeeVariety.coffee_variety_id
        ).join(
            UnitOfMeasure, Farm.area_unit_id == UnitOfMeasure.unit_of_measure_id
        ).join(
            Role, UserRoleFarm.role_id == Role.role_id
        ).filter(
            UserRoleFarm.user_id == user.user_id,
            Plot.plot_id == plot_id
        ).first()

        # Validar si se encontró el lote
        if not plot_data:
            logger.warning("Lote no encontrado o no pertenece al usuario")
            return create_response("error", "Lote no encontrado o no pertenece al usuario")

        plot, coffee_variety, farm, unit_of_measure, role = plot_data

        # Crear la respuesta en el formato esperado
        plot_response = {
            "plot_id": plot.plot_id,
            "name": plot.name,
            "latitude": plot.latitude,
            "longitude": plot.longitude,
            "altitude": plot.altitude,
            "coffee_variety": coffee_variety.name,
            "seed_time": plot.seed_time,
            "unit_of_measure": unit_of_measure.name,
            "farm": {
                "farm_id": farm.farm_id,
                "name": farm.name,
            },
            "role": role.name  # Rol del usuario en la finca a la que pertenece el lote
        }

        return create_response("success", "Lote obtenido exitosamente", {"plot": plot_response})

    except Exception as e:
        # Log detallado para administradores, pero respuesta genérica para el usuario
        logger.error("Error al obtener el lote: %s", str(e))
        return create_response("error", "Ocurrió un error al intentar obtener el lote. Por favor, inténtalo de nuevo más tarde.")

