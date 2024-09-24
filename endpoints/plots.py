from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from models.models import Plot, UserRoleFarm, Permission, RolePermission, Plot
from utils.security import verify_session_token
from dataBase import get_db_session
from utils.response import create_response
import logging
from typing import Optional

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear el enrutador
router = APIRouter()

# Schemas
class PlotCreate(BaseModel):
    farm_id: int
    name: str = Field(..., max_length=100)
    size: float
    crop_type: str = Field(..., max_length=50)
    status: Optional[str] = Field(None, max_length=50)

    class Config:
        orm_mode = True

class PlotUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    size: Optional[float]
    crop_type: Optional[str] = Field(None, max_length=50)
    status: Optional[str] = Field(None, max_length=50)

    class Config:
        orm_mode = True

class PlotResponse(BaseModel):
    plot_id: int
    farm_id: int
    name: str
    size: float
    crop_type: str
    status: Optional[str]

    class Config:
        orm_mode = True

class PlotDelete(BaseModel):
    plot_id: int

    class Config:
        orm_mode = True

# Endpoints
@router.post("/create-plot")
def create_plot(plot_data: PlotCreate, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return create_response("error", "Token de sesión inválido o usuario no encontrado")

    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.farm_id == plot_data.farm_id,
        UserRoleFarm.user_id == user.user_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca")
        return create_response("error", "No tienes permiso para crear lotes en esta finca")

    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "agregar_lotes"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para crear lotes")
        return create_response("error", "No tienes permiso para crear lotes en esta finca")

    try:
        new_plot = Plot(**plot_data.dict())
        db.add(new_plot)
        db.commit()
        logger.info("Lote creado con éxito")
        return create_response("success", "Lote creado correctamente")
    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear lote: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al crear lote: {str(e)}")

@router.get("/get-plot/{plot_id}")
def get_plot(plot_id: int, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return create_response("error", "Token de sesión inválido o usuario no encontrado")

    user_role_farm = db.query(UserRoleFarm).join(Plot).filter(
        Plot.plot_id == plot_id,
        UserRoleFarm.user_id == user.user_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no tiene acceso a esta finca o lote")
        return create_response("error", "No tienes permiso para acceder a este lote")

    plot = db.query(Plot).filter(Plot.plot_id == plot_id).first()
    if not plot:
        logger.warning("Lote no encontrado")
        return create_response("error", "Lote no encontrado")

    return create_response("success", plot)

@router.put("/edit-plot/{plot_id}")
def edit_plot(plot_id: int, plot_data: PlotUpdate, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return create_response("error", "Token de sesión inválido o usuario no encontrado")

    user_role_farm = db.query(UserRoleFarm).join(Plot).filter(
        Plot.plot_id == plot_id,
        UserRoleFarm.user_id == user.user_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no tiene acceso a esta finca o lote")
        return create_response("error", "No tienes permiso para editar este lote")

    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "edit_plot"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para editar lotes")
        return create_response("error", "No tienes permiso para editar lotes en esta finca")

    try:
        plot = db.query(Plot).filter(Plot.plot_id == plot_id).first()
        if not plot:
            logger.warning("Lote no encontrado")
            return create_response("error", "Lote no encontrado")

        for key, value in plot_data.dict().items():
            if value is not None:
                setattr(plot, key, value)

        db.commit()
        logger.info("Lote editado con éxito")
        return create_response("success", "Lote editado correctamente")
    except Exception as e:
        db.rollback()
        logger.error(f"Error al editar lote: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al editar lote: {str(e)}")

@router.delete("/delete-plot/{plot_id}")
def delete_plot(plot_id: int, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return create_response("error", "Token de sesión inválido o usuario no encontrado")

    user_role_farm = db.query(UserRoleFarm).join(Plot).filter(
        Plot.plot_id == plot_id,
        UserRoleFarm.user_id == user.user_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no tiene acceso a esta finca o lote")
        return create_response("error", "No tienes permiso para eliminar este lote")

    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "delete_plot"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para eliminar lotes")
        return create_response("error", "No tienes permiso para eliminar lotes en esta finca")

    try:
        plot = db.query(Plot).filter(Plot.plot_id == plot_id).first()
        if not plot:
            logger.warning("Lote no encontrado")
            return create_response("error", "Lote no encontrado")

        db.delete(plot)
        db.commit()
        logger.info("Lote eliminado con éxito")
        return create_response("success", "Lote eliminado correctamente")
    except Exception as e:
        db.rollback()
        logger.error(f"Error al eliminar lote: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar lote: {str(e)}")
