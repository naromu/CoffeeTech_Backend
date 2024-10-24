from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from models.models import Farm, UserRoleFarm, User, UnitOfMeasure, Role, Status, StatusType, Permission, RolePermission, Invitation, Plot, CoffeeVariety, Flowering, FloweringType
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import Any, Dict, List, Optional
from utils.response import session_token_invalid_response
from utils.response import create_response
from utils.status import get_status
from datetime import datetime, date, timedelta
import pytz

bogota_tz = pytz.timezone("America/Bogota")


router = APIRouter()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modelos Pydantic para las solicitudes y respuestas
class CreateFloweringRequest(BaseModel):
    """
    Modelo para la solicitud de creación de floración.

    Attributes:
        plot_id (int): ID del lote donde se realiza la floración.
        flowering_type_name (str): Nombre del tipo de floración.
        flowering_date (date): Fecha en que ocurre la floración.
        harvest_date (Optional[date]): Fecha en que se realizará la cosecha (opcional).
    """
    plot_id: int
    flowering_type_name: str
    flowering_date: date
    harvest_date: Optional[date] = None

class UpdateFloweringRequest(BaseModel):
    """
    Modelo para la solicitud de actualización de floración.

    Attributes:
        flowering_id (int): ID de la floración a actualizar.
        harvest_date (date): Nueva fecha de cosecha.
    """
    flowering_id: int
    harvest_date: date

# Helper function to check if flowering is inactive
def check_flowering_inactive(flowering: Flowering, db: Session):
    inactive_flowering_status = get_status(db, "Inactivo", "Flowering")
    if not inactive_flowering_status:
        logger.error("Estado 'Inactivo' para Flowering no encontrado")
        raise HTTPException(status_code=500, detail="Estado 'Inactivo' no encontrado en la base de datos")
    if flowering.status_id == inactive_flowering_status.status_id:
        logger.info("La floración con ID %s está inactivo", flowering.flowering_id)
        raise HTTPException(status_code=400, detail="La floración está inactiva")


# Endpoint para crear una floración
@router.post("/create-flowering")
def create_flowering(request: CreateFloweringRequest, session_token: str, db: Session = Depends(get_db_session)):
    """
    Endpoint para crear una nueva floración.

    Este endpoint permite agregar una nueva floración a un lote específico. 
    Requiere un token de sesión para verificar la identidad del usuario y 
    asegura que el usuario tenga permisos adecuados para realizar esta acción.

    Parameters:
        request (CreateFloweringRequest): Modelo de solicitud que contiene 
            los detalles de la floración a crear.
        session_token (str): Token de sesión del usuario.
        db (Session, optional): Sesión de la base de datos, inyectada por 
            FastAPI.

    Returns:
        dict: Un diccionario que indica el resultado de la operación. Puede 
            incluir el ID de la floración creada, el estado y otros 
            detalles.

    Raises:
        HTTPException: Si ocurre un error en el proceso de creación.
    
    **Ejemplo de solicitud:**

    ```json
    {
        "plot_id": 1,
        "flowering_type_name": "Floración A",
        "flowering_date": "2024-10-01",
        "harvest_date": "2024-12-15"
    }
    ```

    **Ejemplo de respuesta exitosa:**

    ```json
    {
        "status": "success",
        "message": "Floración creada correctamente",
        "data": {
            "flowering_id": 123,
            "plot_id": 1,
            "flowering_date": "2024-10-01",
            "harvest_date": "2024-12-15",
            "status": "Activa",
            "flowering_type_name": "Floración A"
        }
    }
    ```

    **Ejemplo de respuesta de error:**

    ```json
    {
        "status": "error",
        "message": "La fecha de floración no puede ser en el futuro"
    }
    ```
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener estados necesarios
    active_plot_status = get_status(db, "Activo", "Plot")
    active_flowering_status = get_status(db, "Activa", "Flowering")
    cosechada_flowering_status = get_status(db, "Cosechada", "Flowering")  # Nuevo estado

    active_urf_status = get_status(db, "Activo", "user_role_farm")

    if not all([active_plot_status, active_flowering_status,cosechada_flowering_status, active_urf_status]):
        logger.error("No se encontraron los estados necesarios")
        return create_response("error", "Estados necesarios no encontrados", status_code=400)

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

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm.farm_id)
        return create_response("error", "No tienes permiso para agregar una floración en esta finca")

    # Verificar permiso 'add_flowering'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "add_flowering"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para agregar una floración en la finca")
        return create_response("error", "No tienes permiso para agregar una floración en esta finca")

    # Validaciones de fechas
    flowering_date = request.flowering_date
    harvest_date = request.harvest_date

    if flowering_date > datetime.now(bogota_tz).date():
        logger.warning("La fecha de floración no puede ser en el futuro")
        return create_response("error", "La fecha de floración no puede ser en el futuro")


    if harvest_date:
        if harvest_date < flowering_date:
            logger.warning("La fecha de cosecha no puede ser anterior a la fecha de floración")
            return create_response("error", "La fecha de cosecha no puede ser anterior a la fecha de floración")
        weeks_between_dates = (harvest_date - flowering_date).days / 7
        if weeks_between_dates > 33:
            logger.warning("Se pasa de 32 semanas desde la floración hasta la fecha de cosecha")
            return create_response("error", "Su lote debió ser cosechado mucho antes, se pasa de 32 semanas desde la floración")
        elif weeks_between_dates < 24:
            logger.warning("No han pasado más de 24 semanas desde la floración hasta la fecha de cosecha")
            return create_response("error", "Su lote no puede ser cosechado, tiene menos de 24 semanas desde la floración")

    else:
        weeks_since_flowering = (datetime.now(bogota_tz).date() - flowering_date).days / 7
        if weeks_since_flowering > 33:
            logger.warning("Se pasa de 32 semanas desde la floración hasta la fecha actual")
            return create_response("error", "Su lote debió ser cosechado mucho antes, se pasa de 32 semanas desde la floración")


    # Verificar que el tipo de floración exista
    flowering_type = db.query(FloweringType).filter(FloweringType.name == request.flowering_type_name).first()
    if not flowering_type:
        logger.warning("El tipo de floración '%s' no existe", request.flowering_type_name)
        return create_response("error", f"El tipo de floración '{request.flowering_type_name}' no existe")

 # **Nuevo: Verificar si hay una floración activa del mismo tipo en el lote solo si harvest_date no está presente**
    if not harvest_date:
        existing_flowering = db.query(Flowering).filter(
            Flowering.plot_id == request.plot_id,
            Flowering.flowering_type_id == flowering_type.flowering_type_id,
            Flowering.status_id == active_flowering_status.status_id
        ).first()
        if existing_flowering:
            logger.warning("Ya existe una floración activa de tipo '%s' en el lote con ID %s", request.flowering_type_name, request.plot_id)
            return create_response("error", f"Ya existe una floración activa de tipo '{request.flowering_type_name}' en este lote")

    # Determinar el estado de la floración basado en la presencia de harvest_date
    if harvest_date:
        flowering_status = cosechada_flowering_status
        status_name = "Cosechada"
    else:
        flowering_status = active_flowering_status
        status_name = "Activa"

    # Crear la floración
    try:
        new_flowering = Flowering(
            plot_id=request.plot_id,
            flowering_date=request.flowering_date,
            harvest_date=harvest_date,
            status_id=flowering_status.status_id,
            flowering_type_id=flowering_type.flowering_type_id
        )
        db.add(new_flowering)
        db.commit()
        db.refresh(new_flowering)

        logger.info("Floración creada exitosamente con ID: %s", new_flowering.flowering_id)
        return create_response("success", "Floración creada correctamente", {
            "flowering_id": new_flowering.flowering_id,
            "plot_id": new_flowering.plot_id,
            "flowering_date": new_flowering.flowering_date.isoformat(),
            "harvest_date": new_flowering.harvest_date.isoformat() if new_flowering.harvest_date else None,
            "status": status_name,
            "flowering_type_name": flowering_type.name
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al crear la floración: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al crear la floración: {str(e)}")

# Endpoint para actualizar una floración
@router.post("/update-flowering")
def update_flowering(request: UpdateFloweringRequest, session_token: str, db: Session = Depends(get_db_session)):
    """
    Actualiza una floración existente.

    **Parámetros**:
    - **request**: Un objeto `UpdateFloweringRequest` que contiene la información de la floración a actualizar.
        - **flowering_id**: ID de la floración a actualizar.
        - **harvest_date**: Nueva fecha de cosecha.

    - **session_token**: Token de sesión del usuario.

    - **db**: Sesión de base de datos, se obtiene automáticamente.

    **Respuestas**:
    - **200 OK**: Floración actualizada correctamente.
    - **400 Bad Request**: Si no se encuentran los estados necesarios o si las fechas son inválidas.
    - **401 Unauthorized**: Si el token de sesión es inválido o el usuario no tiene permisos.
    - **404 Not Found**: Si la floración no existe o no está activa.
    - **500 Internal Server Error**: Si ocurre un error al intentar actualizar la floración.

    **Ejemplo de respuesta exitosa**:
    {
        "status": "success",
        "message": "Floración actualizada correctamente",
        "data": {
            "flowering_id": 1,
            "plot_id": 10,
            "flowering_date": "2024-01-01",
            "harvest_date": "2024-04-01",
            "status": "Cosechada",
            "flowering_type_name": "Tipo de floración"
        }
    }
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener estados necesarios
    active_flowering_status = get_status(db, "Activa", "Flowering")
    harvested_flowering_status = get_status(db, "Cosechada", "Flowering")
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    inactive_flowering_status = get_status(db, "Inactivo", "Flowering")


    if not all([active_flowering_status,inactive_flowering_status, harvested_flowering_status, active_urf_status]):
        logger.error("No se encontraron los estados necesarios")
        return create_response("error", "Estados necesarios no encontrados", status_code=400)

    # Obtener la floración
    flowering = db.query(Flowering).filter(
        Flowering.flowering_id == request.flowering_id,
        Flowering.status_id == active_flowering_status.status_id
    ).first()
    if not flowering:
        logger.warning("La floración con ID %s no existe o no está activa", request.flowering_id)
        return create_response("error", "La floración no existe o no está activa")
    
    # Verificar si la floración está inactiva
    try:
        check_flowering_inactive(flowering, db)
    except HTTPException as e:
        return create_response("error", e.detail, status_code=e.status_code)



    # Obtener el lote y la finca asociada
    plot = db.query(Plot).filter(Plot.plot_id == flowering.plot_id).first()
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca")
        return create_response("error", "No tienes permiso para editar una floración en esta finca")

    # Verificar permiso 'edit_flowering'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "edit_flowering"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para editar una floración")
        return create_response("error", "No tienes permiso para editar una floración en esta finca")

    # Validar la fecha de cosecha
    if request.harvest_date < flowering.flowering_date:
        logger.warning("La fecha de cosecha no puede ser anterior a la fecha de floración")
        return create_response("error", "La fecha de cosecha no puede ser anterior a la fecha de floración")

    weeks_between_dates = (request.harvest_date - flowering.flowering_date).days / 7

    if weeks_between_dates > 33:
        logger.warning("Se pasa de 32 semanas desde la floración hasta la fecha de cosecha")
        return create_response("error", "Su lote ya debió haber sido cosechado, se pasa de 32 semanas desde la floración")

    if weeks_between_dates < 24:
        logger.warning("No han pasado más de 24 semanas desde la floración hasta la fecha de cosecha")
        return create_response("error", "Su lote no puede ser cosechado, tiene menos de 24 semanas desde la floración")

    # Actualizar la floración
    try:
        flowering.harvest_date = request.harvest_date
        flowering.status_id = harvested_flowering_status.status_id
        db.commit()
        db.refresh(flowering)

        logger.info("Floración actualizada exitosamente con ID: %s", flowering.flowering_id)
        return create_response("success", "Floración actualizada correctamente", {
            "flowering_id": flowering.flowering_id,
            "plot_id": flowering.plot_id,
            "flowering_date": flowering.flowering_date.isoformat(),
            "harvest_date": flowering.harvest_date.isoformat(),
            "status": "Cosechada",
            "flowering_type_name": flowering.flowering_type.name
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al actualizar la floración: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al actualizar la floración: {str(e)}")

# Endpoint para obtener recomendaciones (por flowering_id)
@router.get("/get-recommendations/{flowering_id}")
def get_recommendations(flowering_id: int, session_token: str, db: Session = Depends(get_db_session)):
    """
    Obtiene recomendaciones basadas en la floración dada.

    **Parámetros**:
    - **flowering_id**: ID de la floración para la cual se obtendrán recomendaciones.
    - **session_token**: Token de sesión del usuario.

    - **db**: Sesión de base de datos, se obtiene automáticamente.

    **Respuestas**:
    - **200 OK**: Recomendaciones obtenidas exitosamente.
    - **400 Bad Request**: Si no se encuentran los estados necesarios.
    - **401 Unauthorized**: Si el token de sesión es inválido o el usuario no tiene permisos.
    - **404 Not Found**: Si la floración no existe o no está activa.

    **Ejemplo de respuesta exitosa**:
    {
        "status": "success",
        "message": "Recomendaciones obtenidas exitosamente",
        "data": {
            "recommendations": {
                "flowering_id": 1,
                "flowering_type_name": "Tipo de floración",
                "flowering_date": "2024-01-01",
                "tasks": [
                    {
                        "task": "Detección de enfermedades",
                        "start_date": "2024-03-01",
                        "end_date": "2024-03-08",
                        "programar": "Sí"
                    },
                    ...
                ]
            }
        }
    }
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()

    # Obtener estados necesarios
    active_flowering_status = get_status(db, "Activa", "Flowering")
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    inactive_flowering_status = get_status(db, "Inactivo", "Flowering")

    if not all([active_flowering_status,inactive_flowering_status, active_urf_status]):
        logger.error("No se encontraron los estados necesarios")
        return create_response("error", "Estados necesarios no encontrados", status_code=400)

    # Obtener la floración
    flowering = db.query(Flowering).filter(
        Flowering.flowering_id == flowering_id,
        Flowering.status_id == active_flowering_status.status_id
    ).first()
    if not flowering:
        logger.warning("La floración con ID %s no existe o no está activa", flowering_id)
        return create_response("error", "La floración no existe o no está activa")

   # Verificar si la floración está inactiva
    try:
        check_flowering_inactive(flowering, db)
    except HTTPException as e:
        return create_response("error", e.detail, status_code=e.status_code)
    
    # Obtener el lote y la finca asociada
    plot = db.query(Plot).filter(Plot.plot_id == flowering.plot_id).first()
    if not plot:
        logger.warning("El lote asociado a la floración no existe")
        return create_response("error", "El lote asociado a la floración no existe")

    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()

    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca")
        return create_response("error", "No tienes permiso para ver las recomendaciones de esta floración")

    # Verificar permiso 'read_flowering'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "read_flowering"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para ver las recomendaciones")
        return create_response("error", "No tienes permiso para ver las recomendaciones de esta floración")

    # Calcular recomendaciones para la floración
    current_date = datetime.now(bogota_tz).date()
    flowering_date = flowering.flowering_date

    # Lista de tareas
    tasks = []

    # Detección de enfermedades
    disease_detection_start = flowering_date + timedelta(weeks=9)
    disease_detection_end = flowering_date + timedelta(weeks=17)
    programar = "Sí" if disease_detection_start <= current_date <= disease_detection_end else "No"
    tasks.append({
        "task": "Chequeo de Salud",
        "start_date": disease_detection_start.isoformat(),
        "end_date": disease_detection_end.isoformat(),
        "programar": programar
    })

    # Detección de plagas
    pest_detection_start = flowering_date + timedelta(weeks=18)
    pest_detection_end = flowering_date + timedelta(weeks=22)
    programar = "Sí" if pest_detection_start <= current_date <= pest_detection_end else "No"
    tasks.append({
        "task": "Chequeo de Salud",
        "start_date": pest_detection_start.isoformat(),
        "end_date": pest_detection_end.isoformat(),
        "programar": programar
    })

    # Detección de deficiencias nutricionales
    nutritional_deficiency_start = flowering_date + timedelta(weeks=24)
    nutritional_deficiency_end = nutritional_deficiency_start + timedelta(days=6)
    programar = "Sí" if nutritional_deficiency_start <= current_date <= nutritional_deficiency_end else "No"
    tasks.append({
        "task": "Chequeo de Salud",
        "start_date": nutritional_deficiency_start.isoformat(),
        "end_date": nutritional_deficiency_end.isoformat(),
        "programar": programar
    })

    '''# Fertilización
    fertilization_start = nutritional_deficiency_start
    fertilization_end = nutritional_deficiency_end
    programar = "Sí" if fertilization_start <= current_date <= fertilization_end else "No"
    tasks.append({
        "task": "Fertilización",
        "start_date": fertilization_start.isoformat(),
        "end_date": fertilization_end.isoformat(),
        "programar": programar
    })'''

    # Detección de estado de maduración
    for week in [26, 28, 30, 32]:
        maturation_start = flowering_date + timedelta(weeks=week)
        maturation_end = maturation_start + timedelta(days=6)
        programar = "Sí" if maturation_start <= current_date <= maturation_end else "No"
        tasks.append({
            "task": f"Chequeo de estado de maduración (semana {week})",
            "start_date": maturation_start.isoformat(),
            "end_date": maturation_end.isoformat(),
            "programar": programar
        })

    recommendations = {
        "flowering_id": flowering.flowering_id,
        "flowering_type_name": flowering.flowering_type.name,
        "flowering_date": flowering.flowering_date.isoformat(),
        "current_date": current_date.isoformat(),
        "tasks": tasks
    }

    return create_response("success", "Recomendaciones obtenidas exitosamente", {"recommendations": recommendations})

# Endpoint para obtener floraciones activas
@router.get("/get-active-flowerings/{plot_id}")
def get_active_flowerings(plot_id: int, session_token: str, db: Session = Depends(get_db_session)):
    """
    Obtiene las floraciones activas para un lote específico.

    **Parámetros**:
    - **plot_id**: ID del lote para el cual se obtendrán las floraciones activas.
    - **session_token**: Token de sesión del usuario.
    - **db**: Sesión de base de datos, se obtiene automáticamente.

    **Respuestas**:
    - **200 OK**: Floraciones activas obtenidas correctamente.
    - **400 Bad Request**: Si los estados necesarios no se encuentran o son inválidos.
    - **401 Unauthorized**: Si el token de sesión es inválido o el usuario no tiene permisos.
    - **404 Not Found**: Si el lote no existe o no está activo.
    - **500 Internal Server Error**: Si ocurre un error al intentar obtener las floraciones.

    **Ejemplo de respuesta exitosa**:
    {
        "status": "success",
        "message": "Floraciones activas obtenidas exitosamente",
        "data": {
            "flowerings": [
                {
                    "flowering_id": 1,
                    "flowering_type_name": "Floración Temprana",
                    "flowering_date": "2024-01-01",
                    "status": "Activa"
                },
                ...
            ]
        }
    }
    """
    # Verificar el token de sesión y permisos
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    active_plot_status = get_status(db, "Activo", "Plot")
    active_flowering_status = get_status(db, "Activa", "Flowering")
    active_urf_status = get_status(db, "Activo", "user_role_farm")

    plot = db.query(Plot).filter(Plot.plot_id == plot_id, Plot.status_id == active_plot_status.status_id).first()
    if not plot:
        return create_response("error", "El lote no existe o no está activo")

    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()

    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()

    if not user_role_farm:
        return create_response("error", "No tienes permiso para ver las floraciones de este lote")

    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "read_flowering"
    ).first()

    if not role_permission:
        return create_response("error", "No tienes permiso para ver las floraciones de este lote")

    # Obtener floraciones activas
    flowerings = db.query(Flowering).filter(
        Flowering.plot_id == plot_id,
        Flowering.status_id == active_flowering_status.status_id
    ).all()

    if not flowerings:
        return create_response("success", "No tiene floraciones activas", {"flowerings": []})

    flowering_list = []
    for flowering in flowerings:
        flowering_list.append({
            "flowering_id": flowering.flowering_id,
            "flowering_type_name": flowering.flowering_type.name,
            "flowering_date": flowering.flowering_date.isoformat(),
            "status": "Activa"
        })

    return create_response("success", "Floraciones activas obtenidas exitosamente", {"flowerings": flowering_list})

# Endpoint para obtener el historial de floraciones
@router.get("/get-flowering-history/{plot_id}")
def get_flowering_history(plot_id: int, session_token: str, db: Session = Depends(get_db_session)):
    """
    Obtiene el historial de floraciones cosechadas para un lote específico.

    **Parámetros**:
    - **plot_id**: ID del lote para el cual se obtendrá el historial de floraciones.
    - **session_token**: Token de sesión del usuario.
    - **db**: Sesión de base de datos, se obtiene automáticamente.

    **Respuestas**:
    - **200 OK**: Historial de floraciones obtenido correctamente.
    - **400 Bad Request**: Si los estados necesarios no se encuentran o son inválidos.
    - **401 Unauthorized**: Si el token de sesión es inválido o el usuario no tiene permisos.
    - **404 Not Found**: Si el lote no existe o no está activo.
    - **500 Internal Server Error**: Si ocurre un error al intentar obtener el historial.

    **Ejemplo de respuesta exitosa**:
    {
        "status": "success",
        "message": "Historial de floraciones obtenido exitosamente",
        "data": {
            "flowerings": [
                {
                    "flowering_id": 1,
                    "flowering_type_name": "Floración Temprana",
                    "flowering_date": "2023-05-01",
                    "harvest_date": "2023-08-01",
                    "status": "Cosechada"
                },
                ...
            ]
        }
    }
    """
    # Verificar el token de sesión y permisos
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    active_plot_status = get_status(db, "Activo", "Plot")
    harvested_flowering_status = get_status(db, "Cosechada", "Flowering")
    active_urf_status = get_status(db, "Activo", "user_role_farm")

    plot = db.query(Plot).filter(Plot.plot_id == plot_id, Plot.status_id == active_plot_status.status_id).first()
    if not plot:
        return create_response("error", "El lote no existe o no está activo")

    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()

    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()

    if not user_role_farm:
        return create_response("error", "No tienes permiso para ver las floraciones de este lote")

    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "read_flowering"
    ).first()

    if not role_permission:
        return create_response("error", "No tienes permiso para ver las floraciones de este lote")

    # Obtener floraciones cosechadas
    flowerings = db.query(Flowering).filter(
        Flowering.plot_id == plot_id,
        Flowering.status_id == harvested_flowering_status.status_id
    ).all()

    if not flowerings:
        return create_response("success", "No tiene historial de floraciones", {"flowerings": []})

    flowering_list = []
    for flowering in flowerings:
        flowering_list.append({
            "flowering_id": flowering.flowering_id,
            "flowering_type_name": flowering.flowering_type.name,
            "flowering_date": flowering.flowering_date.isoformat(),
            "harvest_date": flowering.harvest_date.isoformat() if flowering.harvest_date else None,
            "status": "Cosechada"
        })

    return create_response("success", "Historial de floraciones obtenido exitosamente", {"flowerings": flowering_list})

# Endpoint para eliminar una floración
@router.post("/delete-flowering/{flowering_id}")
def delete_flowering(flowering_id: int, session_token: str, db: Session = Depends(get_db_session)):
    """
    Elimina (desactiva) una floración activa.

    **Parámetros**:
    - **flowering_id**: ID de la floración a eliminar.
    - **session_token**: Token de sesión del usuario.
    - **db**: Sesión de base de datos, se obtiene automáticamente.

    **Respuestas**:
    - **200 OK**: Floración eliminada correctamente.
    - **400 Bad Request**: Si los estados necesarios no se encuentran o son inválidos.
    - **401 Unauthorized**: Si el token de sesión es inválido o el usuario no tiene permisos.
    - **404 Not Found**: Si la floración no existe o no está activa.
    - **500 Internal Server Error**: Si ocurre un error al intentar eliminar la floración.

    **Ejemplo de respuesta exitosa**:
    {
        "status": "success",
        "message": "Floración eliminada correctamente"
    }

    **Ejemplo de respuesta de error**:
    {
        "status": "error",
        "message": "No tienes permiso para eliminar esta floración"
    }
    """
    # Verificar el token de sesión y permisos
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    active_flowering_status = get_status(db, "Activa", "Flowering")
    inactive_flowering_status = get_status(db, "Inactivo", "Flowering")
    active_urf_status = get_status(db, "Activo", "user_role_farm")

    if not all([active_flowering_status, inactive_flowering_status, active_urf_status]):
        logger.error("No se encontraron los estados necesarios")
        return create_response("error", "Estados necesarios no encontrados", status_code=400)

    # Obtener la floración
    flowering = db.query(Flowering).filter(
        Flowering.flowering_id == flowering_id,
        Flowering.status_id == active_flowering_status.status_id
    ).first()
    if not flowering:
        return create_response("error", "La floración no existe o no está activa")

    # Verificar si la floración está inactiva
    try:
        check_flowering_inactive(flowering, db)
    except HTTPException as e:
        return create_response("error", e.detail, status_code=e.status_code)


    # Obtener el lote y la finca asociada
    plot = db.query(Plot).filter(Plot.plot_id == flowering.plot_id).first()
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()

    # Verificar si el usuario tiene un rol en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()

    if not user_role_farm:
        return create_response("error", "No tienes permiso para eliminar esta floración")

    # Verificar permiso 'delete_flowering'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "delete_flowering"
    ).first()

    if not role_permission:
        return create_response("error", "No tienes permiso para eliminar esta floración")

    try:
        flowering.status_id = inactive_flowering_status.status_id
        db.commit()
        logger.info("Floración con ID %s puesta en estado 'Inactiva'", flowering.flowering_id)
        return create_response("success", "Floración eliminada correctamente")
    except Exception as e:
        db.rollback()
        logger.error("Error al eliminar la floración: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al eliminar la floración: {str(e)}")
