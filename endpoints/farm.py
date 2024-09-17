from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from models.models import Farm, UserRoleFarm, User, UnitOfMeasure, Role, Status, StatusType
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import Any, Dict

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class CreateFarmRequest(BaseModel):
    name: str
    area: float
    unitMeasure: str

# Función auxiliar para crear una respuesta uniforme
def create_response(status: str, message: str, data: Dict[str, Any] = None):
    return {
        "status": status,
        "message": message,
        "data": data or {}
    }

@router.post("/create-farm")
def create_farm(request: CreateFarmRequest, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return create_response("error", "Token de sesión inválido o usuario no encontrado")
    
    # Validación 1: El nombre de la finca no puede estar vacío ni contener solo espacios
    if not request.name or not request.name.strip():
        logger.warning("El nombre de la finca no puede estar vacío o solo contener espacios")
        return create_response("error", "El nombre de la finca no puede estar vacío")

    # Validación 2: El nombre no puede exceder los 100 caracteres
    if len(request.name) > 100:
        logger.warning("El nombre de la finca es demasiado largo")
        return create_response("error", "El nombre de la finca no puede tener más de 100 caracteres")

    # Validación 3: El área no puede ser negativa ni cero
    if request.area <= 0:
        logger.warning("El área de la finca debe ser mayor que cero")
        return create_response("error", "El área de la finca debe ser un número positivo mayor que cero")

    # Validación 4: Área no puede ser extremadamente grande (por ejemplo, no más de 10,000 hectáreas)
    if request.area > 10000:
        logger.warning("El área de la finca no puede exceder las 10,000 unidades de medida")
        return create_response("error", "El área de la finca no puede exceder las 10,000 unidades de medida")

    # Comprobar si el usuario ya tiene una finca con el mismo nombre
    existing_farm = db.query(Farm).join(UserRoleFarm).filter(
        Farm.name == request.name,
        UserRoleFarm.user_id == user.user_id
    ).first()

    if existing_farm:
        logger.warning("El usuario ya tiene una finca con el nombre '%s'", request.name)
        return create_response("error", f"Ya existe una finca con el nombre '{request.name}' para este usuario")

    # Buscar la unidad de medida (unitMeasure)
    unit_of_measure = db.query(UnitOfMeasure).filter(UnitOfMeasure.name == request.unitMeasure).first()
    if not unit_of_measure:
        logger.warning("Unidad de medida no válida: %s", request.unitMeasure)
        return create_response("error", "Unidad de medida no válida")
    
    # Obtener el StatusType con nombre "Farm"
    status_type_record = db.query(StatusType).filter(StatusType.name == "Farm").first()
    if not status_type_record:
        logger.error("No se encontró el tipo de estado 'Farm'")
        raise HTTPException(status_code=400, detail="No se encontró el tipo de estado 'Farm'.")

    # Obtener el status_id para el estado "Activo" del tipo "Farm"
    status_record = db.query(Status).filter(
        Status.name == "Activo",
        Status.status_type_id == status_type_record.status_type_id
    ).first()

    if not status_record:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Farm'")
        raise HTTPException(status_code=400, detail="No se encontró el estado 'Activo' para el tipo 'Farm'.")

    try:
        # Crear la nueva finca
        new_farm = Farm(
            name=request.name,
            area=request.area,
            area_unit_id=unit_of_measure.unit_of_measure_id,
            status_id=status_record.status_id
        )
        db.add(new_farm)
        db.commit()
        db.refresh(new_farm)
        logger.info("Finca creada exitosamente con ID: %s", new_farm.farm_id)

        # Buscar el rol "Propietario"
        role = db.query(Role).filter(Role.name == "Propietario").first()
        if not role:
            logger.error("Rol 'Propietario' no encontrado")
            raise HTTPException(status_code=400, detail="Rol 'Propietario' no encontrado")

        # Crear la relación UserRoleFarm
        user_role_farm = UserRoleFarm(
            user_id=user.user_id,
            farm_id=new_farm.farm_id,
            role_id=role.role_id
        )
        db.add(user_role_farm)
        db.commit()
        logger.info("Usuario asignado como 'Propietario' de la finca con ID: %s", new_farm.farm_id)

        return create_response("success", "Finca creada y usuario asignado correctamente", {
            "farm_id": new_farm.farm_id,
            "name": new_farm.name,
            "area": new_farm.area,
            "unit_of_measure": request.unitMeasure
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al crear la finca o asignar el usuario: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al crear la finca o asignar el usuario: {str(e)}")
