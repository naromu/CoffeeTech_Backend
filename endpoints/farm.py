from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from models.models import Farm, UserRoleFarm, User, UnitOfMeasure, Role, Status, StatusType, Permission, RolePermission, Invitation, Plot
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import Any, Dict, List
from utils.email import send_email
from utils.response import session_token_invalid_response
from utils.response import create_response
from utils.status import get_status


# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class CreateFarmRequest(BaseModel):
    name: str
    area: float
    unitMeasure: str
    
class ListFarmResponse(BaseModel):
    farm_id: int
    name: str
    area: float
    unit_of_measure: str
    status: str
    role: str
    
class UpdateFarmRequest(BaseModel):
    farm_id: int
    name: str
    area: float
    unitMeasure: str

# Función auxiliar para crear una respuesta uniforme


@router.post("/create-farm")
def create_farm(request: CreateFarmRequest, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # Validación 1: El nombre de la finca no puede estar vacío ni contener solo espacios
    if not request.name or not request.name.strip():
        logger.warning("El nombre de la finca no puede estar vacío o solo contener espacios")
        return create_response("error", "El nombre de la finca no puede estar vacío")

    # Validación 2: El nombre no puede exceder los 100 caracteres
    if len(request.name) > 50:
        logger.warning("El nombre de la finca es demasiado largo")
        return create_response("error", "El nombre de la finca no puede tener más de 50 caracteres")

    # Validación 3: El área no puede ser negativa ni cero
    if request.area <= 0:
        logger.warning("El área de la finca debe ser mayor que cero")
        return create_response("error", "El área de la finca debe ser un número positivo mayor que cero")

    # Validación 4: Área no puede ser extremadamente grande (por ejemplo, no más de 10,000 hectáreas)
    if request.area > 10000:
        logger.warning("El área de la finca no puede exceder las 10,000 unidades de medida")
        return create_response("error", "El área de la finca no puede exceder las 10,000 unidades de medida")

    # Obtener el status "Activo" para el tipo "Farm"
    active_farm_status = get_status(db, "Activo", "Farm")
    if not active_farm_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Farm'")
        return create_response("error", "No se encontró el estado 'Activo' para el tipo 'Farm'", status_code=400)

    # Comprobar si el usuario ya tiene una finca activa con el mismo nombre
    existing_farm = db.query(Farm).join(UserRoleFarm).filter(
        Farm.name == request.name,
        UserRoleFarm.user_id == user.user_id,
        Farm.status_id == active_farm_status.status_id  # Filtrar solo por fincas activas
    ).first()

    if existing_farm:
        logger.warning("El usuario ya tiene una finca activa con el nombre '%s'", request.name)
        return create_response("error", f"Ya existe una finca activa con el nombre '{request.name}' para el propietario")

    # Buscar la unidad de medida (unitMeasure)
    unit_of_measure = db.query(UnitOfMeasure).filter(UnitOfMeasure.name == request.unitMeasure).first()
    if not unit_of_measure:
        logger.warning("Unidad de medida no válida: %s", request.unitMeasure)
        return create_response("error", "Unidad de medida no válida")
    
    # Obtener el StatusType con nombre "Farm"
    # Obtener el status "Activo" para el tipo "Farm" utilizando get_status
    status_record = get_status(db, "Activo", "Farm")
    if not status_record:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Farm'")
        return create_response("error", "No se encontró el estado 'Activo' para el tipo 'Farm'", status_code=400)

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


@router.post("/list-farm")
def list_farm(session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener el status "Activo" para el tipo "Farm"
    active_farm_status = get_status(db, "Activo", "Farm")
    if not active_farm_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Farm'")
        return create_response("error", "Estado 'Activo' no encontrado para Farm", status_code=400)

    # Obtener el status "Activo" para el tipo "user_role_farm"
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'user_role_farm'")
        return create_response("error", "Estado 'Activo' no encontrado para user_role_farm", status_code=400)

    try:
        # Realizar la consulta con los filtros adicionales de estado activo
        farms = db.query(Farm, UnitOfMeasure, Status, Role).select_from(UserRoleFarm).join(
            Farm, UserRoleFarm.farm_id == Farm.farm_id
        ).join(
            UnitOfMeasure, Farm.area_unit_id == UnitOfMeasure.unit_of_measure_id
        ).join(
            Status, Farm.status_id == Status.status_id
        ).join(
            Role, UserRoleFarm.role_id == Role.role_id
        ).filter(
            UserRoleFarm.user_id == user.user_id,
            UserRoleFarm.status_id == active_urf_status.status_id,  # Filtrar por estado activo en user_role_farm
            Farm.status_id == active_farm_status.status_id         # Filtrar por estado activo en Farm
        ).all()

        farm_list = []
        for farm, unit_of_measure, status, role in farms:
            farm_list.append(ListFarmResponse(
                farm_id=farm.farm_id,
                name=farm.name,
                area=farm.area,
                unit_of_measure=unit_of_measure.name,
                status=status.name,
                role=role.name
            ))

        return create_response("success", "Lista de fincas obtenida exitosamente", {"farms": farm_list})

    except Exception as e:
        logger.error("Error al obtener la lista de fincas: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al obtener la lista de fincas: {str(e)}")

    
    
@router.post("/update-farm")
def update_farm(request: UpdateFarmRequest, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener el status "Activo" para la finca y la relación user_role_farm
    active_farm_status = get_status(db, "Activo", "Farm")
    active_urf_status = get_status(db, "Activo", "user_role_farm")

    # Verificar si el usuario está asociado con la finca y si tanto la finca como la relación están activas
    user_role_farm = db.query(UserRoleFarm).join(Farm).filter(
        UserRoleFarm.farm_id == request.farm_id,
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.status_id == active_urf_status.status_id,
        Farm.status_id == active_farm_status.status_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca activa que intenta editar")
        return create_response("error", "No tienes permiso para editar esta finca porque no estás asociado con una finca activa")

    # Verificar permisos para el rol del usuario
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "edit_farm"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para editar la finca")
        return create_response("error", "No tienes permiso para editar esta finca")

    # Validaciones del nombre y área
    if not request.name or not request.name.strip():
        logger.warning("El nombre de la finca no puede estar vacío o solo contener espacios")
        return create_response("error", "El nombre de la finca no puede estar vacío")
    
    if len(request.name) > 50:
        logger.warning("El nombre de la finca es demasiado largo")
        return create_response("error", "El nombre de la finca no puede tener más de 50 caracteres")
    
    if request.area <= 0:
        logger.warning("El área de la finca debe ser mayor que cero")
        return create_response("error", "El área de la finca debe ser un número positivo mayor que cero")

    # Buscar la unidad de medida (unitMeasure)
    unit_of_measure = db.query(UnitOfMeasure).filter(UnitOfMeasure.name == request.unitMeasure).first()
    if not unit_of_measure:
        logger.warning("Unidad de medida no válida: %s", request.unitMeasure)
        return create_response("error", "Unidad de medida no válida")

    try:
        # Buscar la finca que se está intentando actualizar
        farm = db.query(Farm).filter(Farm.farm_id == request.farm_id).first()
        if not farm:
            logger.warning("Finca no encontrada")
            return create_response("error", "Finca no encontrada")

        # Verificar si el nuevo nombre ya está en uso por otra finca en la que el usuario es propietario
        if farm.name != request.name:  # Solo validar el nombre si se está intentando cambiar
            existing_farm = db.query(Farm).join(UserRoleFarm).join(Role).filter(
                Farm.name == request.name,
                Farm.farm_id != request.farm_id,
                UserRoleFarm.user_id == user.user_id,
                Role.name == "Propietario",  # Verificar que el usuario sea propietario
                Farm.status_id == active_farm_status.status_id,
                UserRoleFarm.status_id == active_urf_status.status_id
            ).first()

            if existing_farm:
                logger.warning("El nombre de la finca ya está en uso por otra finca del usuario")
                return create_response("error", "El nombre de la finca ya está en uso por otra finca del propietario")

        # Actualizar la finca
        farm.name = request.name
        farm.area = request.area
        farm.area_unit_id = unit_of_measure.unit_of_measure_id

        db.commit()
        db.refresh(farm)
        logger.info("Finca actualizada exitosamente con ID: %s", farm.farm_id)

        return create_response("success", "Finca actualizada correctamente", {
            "farm_id": farm.farm_id,
            "name": farm.name,
            "area": farm.area,
            "unit_of_measure": request.unitMeasure
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al actualizar la finca: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al actualizar la finca: {str(e)}")



@router.get("/get-farm/{farm_id}")
def get_farm(farm_id: int, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener el status "Activo" para la finca y user_role_farm
    active_farm_status = get_status(db, "Activo", "Farm")
    if not active_farm_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Farm'")
        return create_response("error", "Estado 'Activo' no encontrado para Farm", status_code=400)

    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'user_role_farm'")
        return create_response("error", "Estado 'Activo' no encontrado para user_role_farm", status_code=400)

    try:
        # Verificar que la finca y la relación user_role_farm estén activas
        farm_data = db.query(Farm, UnitOfMeasure, Status, Role).select_from(UserRoleFarm).join(
            Farm, UserRoleFarm.farm_id == Farm.farm_id
        ).join(
            UnitOfMeasure, Farm.area_unit_id == UnitOfMeasure.unit_of_measure_id
        ).join(
            Status, Farm.status_id == Status.status_id
        ).join(
            Role, UserRoleFarm.role_id == Role.role_id
        ).filter(
            UserRoleFarm.user_id == user.user_id,
            UserRoleFarm.status_id == active_urf_status.status_id,
            Farm.status_id == active_farm_status.status_id,
            Farm.farm_id == farm_id
        ).first()

        # Validar si se encontró la finca
        if not farm_data:
            logger.warning("Finca no encontrada o no pertenece al usuario")
            return create_response("error", "Finca no encontrada o no pertenece al usuario")

        farm, unit_of_measure, status, role = farm_data

        # Crear la respuesta en el formato esperado
        farm_response = ListFarmResponse(
            farm_id=farm.farm_id,
            name=farm.name,
            area=farm.area,
            unit_of_measure=unit_of_measure.name,
            status=status.name,
            role=role.name
        )

        return create_response("success", "Finca obtenida exitosamente", {"farm": farm_response})

    except Exception as e:
        # Log detallado para administradores, pero respuesta genérica para el usuario
        logger.error("Error al obtener la finca: %s", str(e))
        return create_response("error", "Ocurrió un error al intentar obtener la finca. Por favor, inténtalo de nuevo más tarde.")


@router.post("/delete-farm/{farm_id}")
def delete_farm(farm_id: int, session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return create_response("error", "Token de sesión inválido o usuario no encontrado")

    # Obtener el status "Activo" para la finca y user_role_farm
    active_farm_status = get_status(db, "Activo", "Farm")
    if not active_farm_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'Farm'")
        return create_response("error", "Estado 'Activo' no encontrado para Farm", status_code=400)

    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("No se encontró el estado 'Activo' para el tipo 'user_role_farm'")
        return create_response("error", "Estado 'Activo' no encontrado para user_role_farm", status_code=400)

    # Verificar si el usuario está asociado con la finca activa
    user_role_farm = db.query(UserRoleFarm).join(Farm).filter(
        UserRoleFarm.farm_id == farm_id,
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.status_id == active_urf_status.status_id,
        Farm.status_id == active_farm_status.status_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca que intenta eliminar")
        return create_response("error", "No tienes permiso para eliminar esta finca")

    # Verificar permisos para eliminar la finca
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "delete_farm"
    ).first()

    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para eliminar la finca")
        return create_response("error", "No tienes permiso para eliminar esta finca")

    try:
        farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()

        if not farm:
            logger.warning("Finca no encontrada")
            return create_response("error", "Finca no encontrada")

        # Cambiar el estado de la finca a "Inactiva"
        inactive_farm_status = db.query(Status).join(StatusType).filter(
            Status.name == "Inactiva",
            StatusType.name == "Farm"
        ).first()

        if not inactive_farm_status:
            logger.error("No se encontró el estado 'Inactiva' para el tipo 'Farm'")
            raise HTTPException(status_code=400, detail="No se encontró el estado 'Inactiva' para el tipo 'Farm'.")

        farm.status_id = inactive_farm_status.status_id

        # Cambiar el estado de todas las relaciones en user_role_farm a "Inactiva"
        inactive_urf_status = db.query(Status).join(StatusType).filter(
            Status.name == "Inactiva",
            StatusType.name == "user_role_farm"
        ).first()

        if not inactive_urf_status:
            logger.error("No se encontró el estado 'Inactiva' para el tipo 'user_role_farm'")
            raise HTTPException(status_code=400, detail="No se encontró el estado 'Inactiva' para el tipo 'user_role_farm'.")

        user_role_farms = db.query(UserRoleFarm).filter(UserRoleFarm.farm_id == farm_id).all()
        for urf in user_role_farms:
            urf.status_id = inactive_urf_status.status_id

        db.commit()
        logger.info("Finca y relaciones en user_role_farm puestas en estado 'Inactiva' para la finca con ID %s", farm_id)
        return create_response("success", "Finca puesta en estado 'Inactiva' correctamente")

    except Exception as e:
        db.rollback()
        logger.error("Error al desactivar la finca: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al desactivar la finca: {str(e)}")
