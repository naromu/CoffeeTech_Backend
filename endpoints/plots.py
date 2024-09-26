from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from models.models import Plot, UserRoleFarm, Permission, RolePermission, Farm, Status, StatusType, CoffeeVariety
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
    coffee_variety_id: int

    class Config:
        orm_mode = True

class PlotUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    seed_time: Optional[date]  # Mantener el tipo `date`
    longitude: Optional[str] = None
    latitude: Optional[str] = None
    altitude: Optional[str] = None
    coffee_variety_id: Optional[int] = None

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
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    logger.info(f"Usuario autenticado: {user.name} (ID: {user.user_id})")

    # Aquí ahora usamos plot_data.farm_id
    farm_id = plot_data.farm_id  # Extraemos farm_id del cuerpo de la solicitud

    farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
    if not farm:
        logger.error(f"Finca con ID {farm_id} no encontrada")
        return create_response("error", "Finca no encontrada", status_code=404)

    logger.info(f"Finca encontrada: {farm.name} (ID: {farm.farm_id})")

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
        raise HTTPException(status_code=403, detail="No tienes permiso para crear lotes en esta finca")

    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "agregar_lotes"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para crear lotes")
        raise HTTPException(status_code=403, detail="No tienes permiso para crear lotes en esta finca")

    try:
        # Validar variedad de café
        coffee_variety = db.query(CoffeeVariety).filter(CoffeeVariety.coffee_variety_id == plot_data.coffee_variety_id).first()

        if not coffee_variety:
            logger.error(f"Variedad de café con ID {plot_data.coffee_variety_id} no encontrada")
            raise HTTPException(status_code=404, detail="Variedad de café no encontrada")
        
        # Verificar si ya existe un lote con el mismo nombre en la finca
        existing_plot = db.query(Plot).filter(Plot.name == plot_data.name, Plot.farm_id == plot_data.farm_id).first()
        if existing_plot:
            logger.error(f"Ya existe un lote con el nombre '{plot_data.name}' en la finca ID {plot_data.farm_id}")
            raise HTTPException(status_code=400, detail="Ya existe un lote con ese nombre en la finca.")

        new_plot = Plot(**plot_data.dict())
        db.add(new_plot)
        db.commit()
        logger.info("Lote creado con éxito")
        return create_response("success", "Lote creado correctamente", plot_id=new_plot.plot_id, status_code=201)


    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Error al crear lote: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al crear lote: {str(e)}")



@router.get("/list-plots/{farm_id}", response_model=List[PlotResponse])
def list_plots(farm_id: int, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return create_response("error", "Token de sesión inválido o usuario no encontrado")

    logger.info(f"Usuario autenticado: {user.name} (ID: {user.user_id})")

    # Verificar si la finca existe
    farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
    if not farm:
        logger.error(f"Finca con ID {farm_id} no encontrada")
        return create_response("error", "Finca no encontrada", status_code=404)

    logger.info(f"Finca encontrada: {farm.name} (ID: {farm.farm_id})")

    # Verificar si el usuario tiene acceso a la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.user_id == user.user_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca")
        raise HTTPException(status_code=403, detail="No tienes permiso para listar lotes en esta finca")

    # Verificar si la finca está activa
    active_status = db.query(Status).join(StatusType).filter(
        Status.name == "Activo",
        StatusType.name == "user_role_farm"
    ).first()

    if not active_status:
        logger.error("Estado 'Activo' no encontrado para 'user_role_farm'")
        return create_response("error", "Estado 'Activo' no encontrado para 'user_role_farm'", status_code=400)

    # Verificar si el usuario tiene permisos para listar lotes
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "view_plots"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para listar lotes")
        raise HTTPException(status_code=403, detail="No tienes permiso para listar lotes en esta finca")

    # Listar los lotes asociados a la finca
    plots = db.query(Plot).filter(Plot.farm_id == farm_id).all()
    if not plots:
        logger.warning(f"No se encontraron lotes en la finca {farm.name}")
        return create_response("success", "No se encontraron lotes en la finca")

    logger.info(f"{len(plots)} lotes encontrados en la finca {farm.name}")
    return plots


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

        if plot_data.coffee_variety_id is not None:
            coffee_variety = db.query(CoffeeVariety).filter(CoffeeVariety.coffee_variety_id == plot_data.coffee_variety_id).first()
            if not coffee_variety:
                logger.error(f"Variedad de café con ID {plot_data.coffee_variety_id} no encontrada")
                raise HTTPException(status_code=404, detail="Variedad de café no encontrada")
            plot.coffee_variety_id = plot_data.coffee_variety_id

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
