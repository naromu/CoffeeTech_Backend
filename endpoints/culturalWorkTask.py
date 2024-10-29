from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from models.models import (
    Farm, Plot, CulturalWork, CulturalWorkTask, User, Status, RolePermission, Permission, UserRoleFarm,Notification, NotificationType
)
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import Optional
from utils.response import session_token_invalid_response, create_response
from utils.status import get_status
from datetime import datetime, date
from utils.FCM import send_fcm_notification
import pytz
from typing import List


bogota_tz = pytz.timezone("America/Bogota")

router = APIRouter()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modelo Pydantic para la solicitud de creación de CulturalWorkTask
class CreateCulturalWorkTaskRequest(BaseModel):
    cultural_works_name: str = Field(..., description="Nombre de la labor cultural")
    plot_id: int = Field(..., description="ID del lote asignado a la tarea")
    reminder_owner: bool = Field(..., description="Indica si el propietario debe recibir un recordatorio")
    reminder_collaborator: bool = Field(..., description="Indica si el colaborador debe recibir un recordatorio")
    collaborator_user_id: int = Field(..., description="ID del usuario colaborador asignado a la tarea")
    task_date: date = Field(..., description="Fecha asociada a la tarea (diferente de la fecha de creación)")
    


# Modelo Pydantic para la respuesta de CulturalWorkTask
class CulturalWorkTaskResponse(BaseModel):
    cultural_work_task_id: int
    cultural_works_name: str
    owner_name: str
    collaborator_user_id: int  # Nuevo campo añadido
    collaborator_name: str
    status: str
    task_date: date
    
# Modelo Pydantic para la solicitud de actualización de CulturalWorkTask
class UpdateCulturalWorkTaskRequest(BaseModel):
    cultural_work_task_id: int = Field(..., description="ID de la tarea de labor cultural a modificar")
    cultural_works_name: Optional[str] = Field(None, description="Nuevo nombre de la labor cultural")
    collaborator_user_id: Optional[int] = Field(None, description="Nuevo ID del usuario colaborador asignado a la tarea")
    task_date: Optional[date] = Field(None, description="Nueva fecha asociada a la tarea")

# Modelo Pydantic para la solicitud de eliminación de CulturalWorkTask
class DeleteCulturalWorkTaskRequest(BaseModel):
    cultural_work_task_id: int = Field(..., description="ID de la tarea de labor cultural a eliminar")
    
class Collaborator(BaseModel):
    user_id: int
    name: str

# Endpoint para crear una tarea de labor cultural
@router.post("/create-cultural-work-task")
def create_cultural_work_task(
    request: CreateCulturalWorkTaskRequest,
   session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Crea una nueva tarea de labor cultural asignada a un lote específico.
    
    **Parámetros**:
    - **request**: Un objeto `CreateCulturalWorkTaskRequest` que contiene los detalles de la tarea a crear.
    - **X-Session-Token**: Cabecera que contiene el token de sesión del usuario.
    
    **Respuestas**:
    - **200 OK**: Tarea creada exitosamente.
    - **400 Bad Request**: Si los datos de entrada son inválidos o no se cumplen las validaciones.
    - **401 Unauthorized**: Si el token de sesión es inválido o el usuario no tiene permisos.
    - **404 Not Found**: Si el cultural work o el lote no existen.
    - **500 Internal Server Error**: Si ocurre un error al intentar crear la tarea.
    
    **Ejemplo de solicitud**:
    
    ```json
    {
        "cultural_works_id": 1,
        "plot_id": 10,
        "reminder_owner": true,
        "reminder_collaborator": false,
        "collaborator_user_id": 5,
        "owner_user_id": 2,
        "task_date": "2024-10-18"
    }
    ```
    
    **Ejemplo de cabecera**:
    
    ```
    X-Session-Token: token_valido
    ```
    
    **Ejemplo de respuesta exitosa**:
    
    ```json
    {
        "status": "success",
        "message": "Tarea de labor cultural creada correctamente",
        "data": {
            "cultural_work_tasks_id": 123,
            "cultural_works_id": 1,
            "plot_id": 10,
            "status": "Task terminada",
            "reminder_owner": true,
            "reminder_collaborator": false,
            "collaborator_user_id": 5,
            "owner_user_id": 2,
            "created_at": "2024-10-19T12:34:56",
            "task_date": "2024-10-18"
        }
    }
    ```
    """
    # 1. Verificar que el session_token esté presente
    if not session_token:
        logger.warning("No se proporcionó el token de sesión en la cabecera")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # 2. Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # 3. Obtener los estados necesarios
    active_plot_status = get_status(db, "Activo", "Plot")
    task_terminated_status = get_status(db, "Terminado", "Task")
    pending_task_status = get_status(db, "Por hacer", "Task")  # Estado por defecto para tareas futuras
    active_user_status = get_status(db, "Activo", "User")
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    
    if not all([active_plot_status, task_terminated_status, pending_task_status, active_user_status, active_urf_status]):
        logger.error("No se encontraron los estados necesarios")
        return create_response("error", "Estados necesarios no encontrados", status_code=400)
    
    # 4. Obtener el lote
    plot = db.query(Plot).filter(
        Plot.plot_id == request.plot_id,
        Plot.status_id == active_plot_status.status_id
    ).first()
    if not plot:
        logger.warning("El lote con ID %s no existe o no está activo", request.plot_id)
        return create_response("error", "El lote no existe o no está activo")
    
    # 5. Verificar que el usuario propietario está asociado a la finca del lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe")
    
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm.farm_id)
        return create_response("error", "No tienes permiso para agregar una tarea en esta finca")
    
    # 6. Verificar permiso 'add_cultural_work_task' para el propietario
    role_permission_owner = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "add_cultural_work_task"
    ).first()
    if not role_permission_owner:
        logger.warning("El rol del usuario no tiene permiso para agregar una tarea de labor cultural")
        return create_response("error", "No tienes permiso para agregar una tarea de labor cultural en esta finca")
    
    # 7.1 Buscar el ID de la labor cultural a partir de su nombre
    cultural_work = db.query(CulturalWork).filter(CulturalWork.name == request.cultural_works_name).first()
    if not cultural_work:
        logger.warning("La labor cultural con nombre %s no existe", request.cultural_works_name)
        return create_response("error", "La labor cultural especificada no existe")
    
    
    # 7.2 Verificar que el colaborador está activo

    # Log para verificar el valor de request.collaborator_user_id
    logger.info("Valor de request.collaborator_user_id: %s", request.collaborator_user_id)

    # Log para verificar el valor de active_urf_status.status_id
    logger.info("Valor de active_urf_status.status_id: %s", active_urf_status.status_id)

    # Ejecutar la consulta del colaborador
    collaborator = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == request.collaborator_user_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()

    # Log para verificar si se encontró el colaborador
    if collaborator:
        logger.info("Colaborador encontrado: %s", collaborator)
    else:
        logger.warning("El colaborador con ID %s no existe o no está activo", request.collaborator_user_id)

    # Si no se encuentra el colaborador, retornar la respuesta
    if not collaborator:
        return create_response("error", "El colaborador no existe en la finca")
        
    # 8. Verificar permiso 'completeCulturalWorks' para el colaborador
    # Primero, obtener los roles del colaborador en la finca
    collaborator_roles = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == collaborator.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).all()
    # Obtener permisos asociados a estos roles
    collaborator_permissions = db.query(Permission.name).join(RolePermission).filter(
        RolePermission.role_id.in_([role.role_id for role in collaborator_roles]),
        Permission.name == "complete_cultural_work_task"
    ).all()
    if not collaborator_permissions:
        logger.warning("El colaborador no tiene permiso para completar tareas de labor cultural")
        return create_response("error", "El colaborador no tiene permiso para completar tareas de labor cultural")
    

    # 10. Validar la fecha de la tarea
    current_date = datetime.now(bogota_tz).date()
    task_date = request.task_date
    
    if task_date > current_date:
        # Si la fecha es futura, asignar estado 'Pendiente'
        status_id = pending_task_status.status_id
    else:
        # Si la fecha es anterior o igual a la fecha actual, asignar estado 'Task terminada'
        status_id = task_terminated_status.status_id
    
    # 11. Crear la tarea de labor cultural
    try:
        new_task = CulturalWorkTask(
            cultural_works_id=cultural_work.cultural_works_id,
            plot_id=request.plot_id,
            status_id=status_id,
            reminder_owner=request.reminder_owner,
            reminder_collaborator=request.reminder_collaborator,
            collaborator_user_id=request.collaborator_user_id,
            owner_user_id=user.user_id,  # Asignar el usuario autenticado
            task_date=task_date
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        
    
        # 12. Crear la notificación para el colaborador
        notification_type = db.query(NotificationType).filter(NotificationType.name == "Asignacion_tarea").first()
        pending_status = get_status(db, "AsignacionTarea", "Notification")
        notification_message = f"Se le ha asignado una tarea de {cultural_work.name} en el lote {plot.name} de la finca {farm.name} en la fecha {task_date}"

        new_notification = Notification(
            message=notification_message,
            date=datetime.now(bogota_tz).date(),
            user_id=request.collaborator_user_id,  # Enviar la notificación al colaborador
            notification_type_id=notification_type.notification_type_id,
            farm_id=farm.farm_id,
            status_id=pending_status.status_id  # Estado "Enviada"
        )
        db.add(new_notification)
        db.commit()

        # 13. Enviar notificación FCM al colaborador (si tiene token FCM)
        collaborator_user = db.query(User).filter(User.user_id == request.collaborator_user_id).first()
        if collaborator_user and collaborator_user.fcm_token and (task_date > current_date):
            send_fcm_notification(collaborator_user.fcm_token, "Nueva Tarea de Labor Cultural", notification_message)


    
        logger.info("Tarea de labor cultural creada exitosamente con ID: %s", new_task.cultural_work_tasks_id)
        return create_response("success", "Tarea de labor cultural creada correctamente", {
            "cultural_work_tasks_id": new_task.cultural_work_tasks_id,
            "cultural_works_id": new_task.cultural_works_id,
            "plot_id": new_task.plot_id,
            "status": "Terminado" if task_date <= current_date else "Por hacer",
            "reminder_owner": new_task.reminder_owner,
            "reminder_collaborator": new_task.reminder_collaborator,
            "collaborator_user_id": new_task.collaborator_user_id,
            "owner_user_id": new_task.owner_user_id,
            "created_at": new_task.created_at.isoformat(),
            "task_date": new_task.task_date.isoformat()
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al crear la tarea de labor cultural: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al crear la tarea de labor cultural: {str(e)}")



# Endpoint para listar tareas por lote
@router.get("/list-cultural-work-tasks/{plot_id}")
def list_cultural_work_tasks(
    plot_id: int, 
    session_token: str, 
    db: Session = Depends(get_db_session)
):
    # Verificar que el token de sesión esté presente
    if not session_token:
        logger.warning("No se proporcionó el token de sesión en la cabecera")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # Obtener el estado "Activo" para Plot
    active_plot_status = get_status(db, "Activo", "Plot")
    if not active_plot_status:
        logger.error("Estado 'Activo' para Plot no encontrado")
        return create_response("error", "Estado 'Activo' para Plot no encontrado", status_code=400)
    
    # Obtener el lote
    plot = db.query(Plot).filter(Plot.plot_id == plot_id, Plot.status_id == active_plot_status.status_id).first()
    if not plot:
        logger.warning(f"El lote con ID {plot_id} no existe o no está activo")
        return create_response("error", "El lote no existe o no está activo")
    
    # Obtener la finca asociada al lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe")
    
    # Obtener el estado "Activo" para user_role_farm
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("Estado 'Activo' para user_role_farm no encontrado")
        return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=400)
    
    # Verificar si el usuario tiene un rol activo en la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning(f"El usuario no está asociado con la finca con ID {farm.farm_id}")
        return create_response("error", "No tienes permiso para ver las tareas en esta finca")
    
    # Verificar permiso 'read_cultural_work_task'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "read_cultural_work_task"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para leer tareas de labor cultural")
        return create_response("error", "No tienes permiso para ver las tareas de labor cultural en esta finca")
    
    # Obtener el estado "Inactivo" para Task
    inactive_task_status = get_status(db, "Inactivo", "Task")
    if not inactive_task_status:
        logger.error("Estado 'Inactivo' para Task no encontrado")
        return create_response("error", "Estado 'Inactivo' para Task no encontrado", status_code=500)
    
    # Consultar las tareas de labor cultural del lote que están activas
    tasks = db.query(CulturalWorkTask).filter(
        CulturalWorkTask.plot_id == plot_id,
        CulturalWorkTask.status_id != inactive_task_status.status_id  # Excluir tareas inactivas
    ).all()
    
    # Preparar la lista de tareas con los detalles requeridos
    task_list = []
    for task in tasks:
        # Obtener el nombre de la labor cultural
        cultural_work = db.query(CulturalWork).filter(CulturalWork.cultural_works_id == task.cultural_works_id).first()
        cultural_work_name = cultural_work.name if cultural_work else "Desconocido"
        
        # Obtener el nombre del propietario
        owner = db.query(User).filter(User.user_id == task.owner_user_id).first()
        owner_name = owner.name if owner else "Desconocido"
        
        # Obtener el nombre del colaborador
        collaborator = db.query(User).filter(User.user_id == task.collaborator_user_id).first()
        collaborator_name = collaborator.name if collaborator else "Desconocido"
        
        # Obtener el nombre del status
        status = db.query(Status).filter(Status.status_id == task.status_id).first()
        status_name = status.name if status else "Desconocido"
        
        # Añadir la tarea a la lista incluyendo collaborator_user_id
        task_list.append({
            "cultural_work_task_id": task.cultural_work_tasks_id,
            "cultural_works_name": cultural_work_name,
            "owner_name": owner_name,
            "collaborator_user_id": task.collaborator_user_id,  # Nuevo campo añadido
            "collaborator_name": collaborator_name,
            "status": status_name,
            "task_date": task.task_date.isoformat()  # Convertir date a string
        })
    
    # Verificar si no hay tareas
    if not task_list:
        return create_response("success", "El lote no tiene tareas creadas", {"tasks": []})
    # Retornar la lista de tareas
    return create_response("success", "Tareas obtenidas exitosamente", {"tasks": task_list})



@router.get("/my-cultural-work-tasks")
def my_cultural_work_tasks(
    session_token: str, 
    db: Session = Depends(get_db_session)
):
    # Verificar que el token de sesión esté presente
    if not session_token:
        logger.warning("No se proporcionó el token de sesión en la cabecera")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # Obtener el estado "Por hacer" para Task
    por_hacer_status = get_status(db, "Por hacer", "Task")
    if not por_hacer_status:
        logger.error("Estado 'Por hacer' para Task no encontrado")
        return create_response("error", "Estado 'Por hacer' para Task no encontrado", status_code=400)
    
    # Obtener el estado "Inactivo" para Task
    inactive_task_status = get_status(db, "Inactivo", "Task")
    if not inactive_task_status:
        logger.error("Estado 'Inactivo' para Task no encontrado")
        return create_response("error", "Estado 'Inactivo' para Task no encontrado", status_code=500)
    
    # Consultar las tareas donde el usuario es colaborador, el estado es "Por hacer" y no está inactivo
    tasks = db.query(CulturalWorkTask).filter(
        CulturalWorkTask.collaborator_user_id == user.user_id,
        CulturalWorkTask.status_id == por_hacer_status.status_id,
        CulturalWorkTask.status_id != inactive_task_status.status_id  # Asegurar que no esté inactivo
    ).all()
    
    # Preparar la lista de tareas con los detalles requeridos
    task_list = []
    for task in tasks:
        # Obtener el nombre de la labor cultural
        cultural_work = db.query(CulturalWork).filter(CulturalWork.cultural_works_id == task.cultural_works_id).first()
        cultural_work_name = cultural_work.name if cultural_work else "Desconocido"
        
        # Obtener el nombre del propietario
        owner = db.query(User).filter(User.user_id == task.owner_user_id).first()
        owner_name = owner.name if owner else "Desconocido"
        
        # Obtener el nombre del status
        status = db.query(Status).filter(Status.status_id == task.status_id).first()
        status_name = status.name if status else "Desconocido"
        
        # Obtener la finca y el lote asociados
        plot = db.query(Plot).filter(Plot.plot_id == task.plot_id).first()
        farm_name = plot.farm.name if plot and plot.farm else "Desconocido"
        plot_name = plot.name if plot else "Desconocido"
        
        # Añadir la tarea a la lista con task_date convertido a string
        task_list.append({
            "cultural_work_task_id": task.cultural_work_tasks_id,  # Añadido cultural_work_task_id
            "cultural_works_name": cultural_work_name,            # Añadido cultural_works_name
            "collaborator_id": user.user_id,
            "collaborator_name": user.name,
            "owner_name": owner_name,
            "status": status_name,
            "task_date": task.task_date.isoformat(),              # Convertir date a string
            "farm_name": farm_name,
            "plot_name": plot_name
        })
    
    # Verificar si no hay tareas
    if not task_list:
        return create_response("success", "No tienes tareas asignadas", {"tasks": []})
    
    # Retornar la lista de tareas
    return create_response("success", "Tareas obtenidas exitosamente", {"tasks": task_list})



# Endpoint para actualizar una tarea de labor cultural
@router.post("/update-cultural-work-task")
def update_cultural_work_task(
    request: UpdateCulturalWorkTaskRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Actualiza una tarea de labor cultural existente.

    **Parámetros**:
    - **request**: Un objeto `UpdateCulturalWorkTaskRequest` que contiene los detalles de la tarea a actualizar.
    - **X-Session-Token**: Cabecera que contiene el token de sesión del usuario.

    **Respuestas**:
    - **200 OK**: Tarea actualizada exitosamente.
    - **400 Bad Request**: Si los datos de entrada son inválidos o no se cumplen las validaciones.
    - **401 Unauthorized**: Si el token de sesión es inválido o el usuario no tiene permisos.
    - **403 Forbidden**: Si el usuario no es el creador de la tarea o no tiene el permiso necesario.
    - **404 Not Found**: Si la tarea de labor cultural no existe.
    - **500 Internal Server Error**: Si ocurre un error al intentar actualizar la tarea.
    """
    current_date = datetime.now(bogota_tz).date()

    # 1. Verificar que el session_token esté presente
    if not session_token:
        logger.warning("No se proporcionó el token de sesión en la cabecera")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # 2. Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # 3. Obtener la tarea a actualizar
    task = db.query(CulturalWorkTask).filter(CulturalWorkTask.cultural_work_tasks_id == request.cultural_work_task_id).first()
    if not task:
        logger.warning(f"La tarea de labor cultural con ID {request.cultural_work_task_id} no existe")
        return create_response("error", "La tarea de labor cultural especificada no existe", status_code=404)
    
    # 4.1 Verificar que la tarea no esté inactiva
    inactive_task_status = get_status(db, "Inactivo", "Task")
    if not inactive_task_status:
        logger.error("Estado 'Inactivo' para Task no encontrado")
        return create_response("error", "Estado 'Inactivo' para Task no encontrado", status_code=500)
    
    if task.status_id == inactive_task_status.status_id:
        logger.warning(f"La tarea de labor cultural con ID {request.cultural_work_task_id} está inactiva y no puede ser modificada")
        return create_response("error", "La tarea de labor cultural está inactiva y no puede ser modificada", status_code=403)
 
    # 4.2 Verificar que el usuario que edita es el creador de la tarea
    if task.owner_user_id != user.user_id:
        logger.warning(f"Usuario {user.user_id} no es el creador de la tarea {task.cultural_work_task_id}")
        return create_response("error", "No tienes permiso para editar esta tarea de labor cultural", status_code=403)
    
    # 5. Verificar que el usuario tenga el permiso 'edit_cultural_work_task'
    # Obtener el rol del usuario en la finca asociada a la tarea
    plot = db.query(Plot).filter(Plot.plot_id == task.plot_id).first()
    if not plot:
        logger.error(f"El lote con ID {task.plot_id} asociado a la tarea no existe")
        return create_response("error", "El lote asociado a la tarea no existe", status_code=404)
    
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.error(f"La finca con ID {plot.farm_id} asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe", status_code=404)
    
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("Estado 'Activo' para user_role_farm no encontrado")
        return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=400)
    
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    
    if not user_role_farm:
        logger.warning(f"El usuario {user.user_id} no está asociado con la finca {farm.farm_id}")
        return create_response("error", "No tienes permiso para editar tareas en esta finca", status_code=403)
    
    # Verificar permiso 'edit_cultural_work_task'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "edit_cultural_work_task"
    ).first()
    
    if not role_permission:
        logger.warning(f"El rol {user_role_farm.role_id} del usuario no tiene permiso para editar tareas de labor cultural")
        return create_response("error", "No tienes permiso para editar tareas de labor cultural en esta finca", status_code=403)
    
    # 6. Realizar las actualizaciones permitidas
    try:
        cambios = {}
        old_colaborador_id = None  # Para almacenar el colaborador anterior si se cambia

        # Actualizar el tipo de labor cultural si se proporciona
        if request.cultural_works_name and request.cultural_works_name != task.cultural_work.name:
            cultural_work = db.query(CulturalWork).filter(CulturalWork.name == request.cultural_works_name).first()
            if not cultural_work:
                logger.warning(f"La labor cultural con nombre {request.cultural_works_name} no existe")
                return create_response("error", "La labor cultural especificada no existe", status_code=400)
            task.cultural_works_id = cultural_work.cultural_works_id
            cambios['cultural_works_name'] = cultural_work.name

        # Actualizar el colaborador si se proporciona y es diferente
        if request.collaborator_user_id and request.collaborator_user_id != task.collaborator_user_id:
            # Verificaciones del colaborador
            nuevo_colaborador = db.query(User).filter(User.user_id == request.collaborator_user_id).first()
            if not nuevo_colaborador:
                logger.warning(f"El colaborador con ID {request.collaborator_user_id} no existe")
                return create_response("error", "El colaborador especificado no existe", status_code=400)
            
            # Verificar que el nuevo colaborador esté asociado con la misma finca
            colaborador_farm = db.query(UserRoleFarm).filter(
                UserRoleFarm.user_id == request.collaborator_user_id,
                UserRoleFarm.farm_id == farm.farm_id,
                UserRoleFarm.status_id == active_urf_status.status_id
            ).first()
            if not colaborador_farm:
                logger.warning(f"El colaborador {request.collaborator_user_id} no está asociado con la finca {farm.farm_id}")
                return create_response("error", "El colaborador no está asociado con esta finca", status_code=403)
            
            # Verificar que el nuevo colaborador tenga el permiso adecuado
            role_permission_colab = db.query(RolePermission).join(Permission).filter(
                RolePermission.role_id == colaborador_farm.role_id,
                Permission.name == "complete_cultural_work_task"  # Asegúrate de que este permiso exista
            ).first()
            if not role_permission_colab:
                logger.warning(f"El rol {colaborador_farm.role_id} del colaborador no tiene permiso para ser asignado a tareas de labor cultural")
                return create_response("error", "El colaborador no tiene permiso para ser asignado a tareas de labor cultural", status_code=403)
            
            # Almacenar el colaborador antiguo antes de actualizar
            old_colaborador_id = task.collaborator_user_id
            task.collaborator_user_id = request.collaborator_user_id
            cambios['collaborator_user_id'] = request.collaborator_user_id

        # Actualizar la fecha de la tarea si se proporciona y es diferente
        if request.task_date and request.task_date != task.task_date:
            old_task_date = task.task_date
            task.task_date = request.task_date
            cambios['task_date'] = task.task_date.isoformat()
            
            # Determinar el nuevo estado basado en la nueva fecha
            pending_task_status = get_status(db, "Por hacer", "Task")
            task_terminated_status = get_status(db, "Terminado", "Task")
            if request.task_date > datetime.now(bogota_tz).date():
                task.status_id = pending_task_status.status_id
                cambios['status'] = "Por hacer"
            else:
                task.status_id = task_terminated_status.status_id
                cambios['status'] = "Terminado"

        # Confirmar los cambios en la base de datos antes de enviar notificaciones
        db.commit()

        # Generar notificaciones basadas en los cambios realizados
        if cambios:
            # Obtener los datos actualizados de la tarea
            task = db.query(CulturalWorkTask).filter(CulturalWorkTask.cultural_work_tasks_id == request.cultural_work_task_id).first()
            
            # Verificar si hubo cambio de colaborador
            if 'collaborator_user_id' in cambios:
                # Notificación al colaborador antiguo
                if old_colaborador_id:
                    message_unassign = f"Se te ha desasignado la tarea de labor cultural '{task.cultural_work.name}' en el lote {plot.name} de la finca {farm.name}."
                    
                    # Obtener el tipo de notificación y estado correspondiente
                    notification_type_unassign = db.query(NotificationType).filter(NotificationType.name == "Asignacion_tarea").first()
                    if not notification_type_unassign:
                        logger.error("Tipo de notificación 'Asignacion_tarea' no encontrado")
                        return create_response("error", "Tipo de notificación 'Asignacion_tarea' no encontrado", status_code=500)
                    pending_status_unassign = get_status(db, "AsignacionTarea", "Notification")
                    if not pending_status_unassign:
                        logger.error("Estado 'Asignacion_tarea' para Notification no encontrado")
                        return create_response("error", "Estado 'Asignacion_tarea' para Notification no encontrado", status_code=500)
                    
                    nueva_notificacion_unassign = Notification(
                        message=message_unassign,
                        date=datetime.now(bogota_tz).date(),
                        user_id=old_colaborador_id,  # Asignar al colaborador antiguo
                        notification_type_id=notification_type_unassign.notification_type_id,
                        farm_id=farm.farm_id,
                        status_id=pending_status_unassign.status_id
                    )
                    db.add(nueva_notificacion_unassign)
                
                # Notificación al nuevo colaborador
                message_assign = f"Se te ha asignado una nueva tarea de labor cultural '{task.cultural_work.name}' en el lote {plot.name} de la finca {farm.name} para la fecha {task.task_date}."
                
                # Obtener el tipo de notificación y estado correspondiente
                notification_type_assign = db.query(NotificationType).filter(NotificationType.name == "Asignacion_tarea").first()
                if not notification_type_assign:
                    logger.error("Tipo de notificación 'Asignacion_tarea' no encontrado")
                    return create_response("error", "Tipo de notificación 'Asignacion_tarea' no encontrado", status_code=500)
                pending_status_assign = get_status(db, "AsignacionTarea", "Notification")
                if not pending_status_assign:
                    logger.error("Estado 'AsignacionTarea' para Notification no encontrado")
                    return create_response("error", "Estado 'AsignacionTarea' para Notification no encontrado", status_code=500)
                
                nueva_notificacion_assign = Notification(
                    message=message_assign,
                    date=datetime.now(bogota_tz).date(),
                    user_id=task.collaborator_user_id,  # Asignar al nuevo colaborador
                    notification_type_id=notification_type_assign.notification_type_id,
                    farm_id=farm.farm_id,
                    status_id=pending_status_assign.status_id
                )
                db.add(nueva_notificacion_assign)
                
                # Confirmar las notificaciones de cambio de colaborador
                db.commit()
                
                # Enviar notificación FCM al colaborador antiguo si tiene token
                if old_colaborador_id:
                    colaborador_antiguo = db.query(User).filter(User.user_id == old_colaborador_id).first()
                    if colaborador_antiguo and colaborador_antiguo.fcm_token:
                        send_fcm_notification(
                            colaborador_antiguo.fcm_token,
                            "Desasignación de Tarea de Labor Cultural",
                            message_unassign
                        )
                
                # Enviar notificación FCM al nuevo colaborador si tiene token y la tarea está pendiente
                colaborador_nuevo = db.query(User).filter(User.user_id == task.collaborator_user_id).first()
                if colaborador_nuevo and colaborador_nuevo.fcm_token and (task.task_date > current_date):
                    send_fcm_notification(
                        colaborador_nuevo.fcm_token,
                        "Asignación de Tarea de Labor Cultural",
                        message_assign
                    )
            
            else:
                # Si no hubo cambio de colaborador, verificar si hubo cambio de fecha/hora
                if 'task_date' in cambios:
                    message_update = f"Se ha actualizado una tarea del lote {plot.name} de la finca {farm.name}."
                    
                    # Obtener el tipo de notificación y estado correspondiente
                    notification_type_update = db.query(NotificationType).filter(NotificationType.name == "Actualizacion_tarea").first()
                    if not notification_type_update:
                        logger.error("Tipo de notificación 'Actualizacion_tarea' no encontrado")
                        return create_response("error", "Tipo de notificación 'Actualizacion_tarea' no encontrado", status_code=500)
                    pending_status_update = get_status(db, "ActualizacionTarea", "Notification")
                    if not pending_status_update:
                        logger.error("Estado 'ActualizacionTarea' para Notification no encontrado")
                        return create_response("error", "Estado 'ActualizacionTarea' para Notification no encontrado", status_code=500)
                    
                    # Crear la notificación
                    nueva_notificacion_update = Notification(
                        message=message_update,
                        date=datetime.now(bogota_tz).date(),
                        user_id=task.collaborator_user_id,  # Asignar al colaborador actual
                        notification_type_id=notification_type_update.notification_type_id,
                        farm_id=farm.farm_id,
                        status_id=pending_status_update.status_id
                    )
                    db.add(nueva_notificacion_update)
                    db.commit()
                    
                    # Enviar notificación FCM al colaborador si tiene token y la tarea está pendiente
                    colaborador_actual = db.query(User).filter(User.user_id == task.collaborator_user_id).first()
                    if colaborador_actual and colaborador_actual.fcm_token and (task.task_date > current_date):
                        send_fcm_notification(
                            colaborador_actual.fcm_token,
                            "Actualización de Tarea de Labor Cultural",
                            message_update
                        )

        logger.info(f"Tarea de labor cultural con ID {task.cultural_work_tasks_id} actualizada exitosamente")
        
        # Preparar la respuesta con los cambios realizados
        response_data = {
            "cultural_work_task_id": task.cultural_work_tasks_id,
            "cultural_works_name": task.cultural_work.name,
            "collaborator_user_id": task.collaborator_user_id,
            "task_date": task.task_date.isoformat(),
            "status": "Terminado" if task.task_date <= datetime.now(bogota_tz).date() else "Por hacer"
        }
        
        return create_response("success", "Tarea de labor cultural actualizada correctamente", data=response_data)

    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar la tarea de labor cultural: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al actualizar la tarea de labor cultural: {str(e)}")

    
    
# Nuevo Endpoint para eliminar una tarea de labor cultural
@router.post("/delete-cultural-work-task")
def delete_cultural_work_task(
    request: DeleteCulturalWorkTaskRequest,
    session_token: str = Header(..., alias="X-Session-Token"),
    db: Session = Depends(get_db_session)
):
    """
    Elimina una tarea de labor cultural existente cambiando su estado a "Inactivo".

    **Parámetros**:
    - **request**: Un objeto `DeleteCulturalWorkTaskRequest` que contiene el ID de la tarea a eliminar.
    - **X-Session-Token**: Cabecera que contiene el token de sesión del usuario.

    **Respuestas**:
    - **200 OK**: Tarea eliminada exitosamente.
    - **400 Bad Request**: Si los datos de entrada son inválidos o no se cumplen las validaciones.
    - **401 Unauthorized**: Si el token de sesión es inválido o el usuario no tiene permisos.
    - **403 Forbidden**: Si el usuario no tiene el permiso necesario para eliminar la tarea.
    - **404 Not Found**: Si la tarea de labor cultural no existe.
    - **500 Internal Server Error**: Si ocurre un error al intentar eliminar la tarea.
    """
    # 1. Verificar que el session_token esté presente
    if not session_token:
        logger.warning("No se proporcionó el token de sesión en la cabecera")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # 2. Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # 3. Obtener la tarea a eliminar
    task = db.query(CulturalWorkTask).filter(CulturalWorkTask.cultural_work_tasks_id == request.cultural_work_task_id).first()
    if not task:
        logger.warning(f"La tarea de labor cultural con ID {request.cultural_work_task_id} no existe")
        return create_response("error", "La tarea de labor cultural especificada no existe", status_code=404)
    
    # 4. Verificar que la tarea no esté ya inactiva
    inactive_task_status = get_status(db, "Inactivo", "Task")
    if not inactive_task_status:
        logger.error("Estado 'Inactivo' para Task no encontrado")
        return create_response("error", "Estado 'Inactivo' para Task no encontrado", status_code=500)
    
    if task.status_id == inactive_task_status.status_id:
        logger.warning(f"La tarea de labor cultural con ID {request.cultural_work_task_id} ya está inactiva")
        return create_response("error", "La tarea de labor cultural ya está inactiva", status_code=400)
    
    # 5. Verificar que el usuario tenga el permiso 'delete_cultural_work_task'
    # Obtener el rol del usuario en la finca asociada a la tarea
    plot = db.query(Plot).filter(Plot.plot_id == task.plot_id).first()
    if not plot:
        logger.error(f"El lote con ID {task.plot_id} asociado a la tarea no existe")
        return create_response("error", "El lote asociado a la tarea no existe", status_code=404)
    
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.error(f"La finca con ID {plot.farm_id} asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe", status_code=404)
    
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("Estado 'Activo' para user_role_farm no encontrado")
        return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=400)
    
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    
    if not user_role_farm:
        logger.warning(f"El usuario {user.user_id} no está asociado con la finca {farm.farm_id}")
        return create_response("error", "No tienes permiso para eliminar tareas en esta finca", status_code=403)
    
    # Verificar permiso 'delete_cultural_work_task'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "delete_cultural_work_task"
    ).first()
    
    if not role_permission:
        logger.warning(f"El rol {user_role_farm.role_id} del usuario no tiene permiso para eliminar tareas de labor cultural")
        return create_response("error", "No tienes permiso para eliminar tareas de labor cultural en esta finca", status_code=403)
    
    # 6. Cambiar el estado de la tarea a "Inactivo"
    try:
        task.status_id = inactive_task_status.status_id
        cambios = {'status': 'Inactivo'}
        
        # Opcional: Crear una notificación para el colaborador indicando que la tarea ha sido eliminada
        notification_type = db.query(NotificationType).filter(NotificationType.name == "EliminacionTarea").first()
        if notification_type:
            # Obtener Status para 'Inactivo' de tipo 'Notification'
            eliminacion_status = get_status(db, "Inactivo", "Notification")
            if eliminacion_status:
                notification_message = f"La tarea de {task.cultural_work.name} en el lote {plot.name} de la finca {farm.name} ha sido eliminada."
                nueva_notificacion = Notification(
                    message=notification_message,
                    date=datetime.now(bogota_tz).date(),
                    user_id=task.collaborator_user_id,
                    notification_type_id=notification_type.notification_type_id,
                    farm_id=farm.farm_id,
                    status_id=eliminacion_status.status_id
                )
                db.add(nueva_notificacion)
        
                # Enviar notificación FCM al colaborador si tiene token
                colaborador_user = db.query(User).filter(User.user_id == task.collaborator_user_id).first()
                if colaborador_user and colaborador_user.fcm_token:
                    send_fcm_notification(colaborador_user.fcm_token, "Eliminación de Tarea de Labor Cultural", notification_message)
        
        db.commit()
        
        logger.info(f"Tarea de labor cultural con ID {task.cultural_work_tasks_id} eliminada exitosamente")
        
        return create_response("success", "Tarea de labor cultural eliminada correctamente", data={"cultural_work_task_id": task.cultural_work_tasks_id})
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error al eliminar la tarea de labor cultural: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al eliminar la tarea de labor cultural: {str(e)}")
    
    
@router.get("/collaborators-with-complete-permission")
def get_collaborators_with_complete_permission(
    plot_id: int,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Obtiene una lista de colaboradores (id y nombre) que tienen el permiso 'complete_cultural_work_task' 
    y pertenecen a la finca asociada al lote especificado.

    **Parámetros**:
    - **plot_id**: ID del lote.
    - **X-Session-Token**: Cabecera que contiene el token de sesión del usuario.

    **Respuestas**:
    - **200 OK**: Lista de colaboradores obtenida exitosamente.
    - **400 Bad Request**: Si los parámetros son inválidos o no se encuentran los estados necesarios.
    - **401 Unauthorized**: Si el token de sesión es inválido o está ausente.
    - **403 Forbidden**: Si el usuario no está asociado con la finca o no tiene permisos.
    - **404 Not Found**: Si el lote o la finca no existen.
    - **500 Internal Server Error**: Si ocurre un error en el servidor.
    """
    try:
        # 1. Verificar que el session_token esté presente
        if not session_token:
            logger.warning("No se proporcionó el token de sesión en la solicitud")
            return create_response("error", "Token de sesión faltante", status_code=401)

        # 2. Verificar el token de sesión
        user = verify_session_token(session_token, db)
        if not user:
            logger.warning("Token de sesión inválido o usuario no encontrado")
            return session_token_invalid_response()

        # 3. Obtener el lote y la finca asociada
        active_plot_status = get_status(db, "Activo", "Plot")
        if not active_plot_status:
            logger.error("Estado 'Activo' para Plot no encontrado")
            return create_response("error", "Estado 'Activo' para Plot no encontrado", status_code=400)

        plot = db.query(Plot).filter(
            Plot.plot_id == plot_id,
            Plot.status_id == active_plot_status.status_id
        ).first()
        if not plot:
            logger.warning(f"El lote con ID {plot_id} no existe o no está activo")
            return create_response("error", "El lote no existe o no está activo", status_code=404)

        farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
        if not farm:
            logger.warning(f"La finca asociada al lote con ID {plot_id} no existe")
            return create_response("error", "La finca asociada al lote no existe", status_code=404)

        # 4. Verificar que el usuario esté asociado con la finca y tenga estado activo
        active_urf_status = get_status(db, "Activo", "user_role_farm")
        if not active_urf_status:
            logger.error("Estado 'Activo' para user_role_farm no encontrado")
            return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=400)

        user_role_farm = db.query(UserRoleFarm).filter(
            UserRoleFarm.user_id == user.user_id,
            UserRoleFarm.farm_id == farm.farm_id,
            UserRoleFarm.status_id == active_urf_status.status_id
        ).first()

        if not user_role_farm:
            logger.warning(f"El usuario {user.user_id} no está asociado con la finca {farm.farm_id}")
            return create_response("error", "No tienes permiso para acceder a esta finca", status_code=403)

        # 5. Obtener el permiso 'complete_cultural_work_task'
        complete_permission = db.query(Permission).filter(Permission.name == "complete_cultural_work_task").first()
        if not complete_permission:
            logger.error("Permiso 'complete_cultural_work_task' no encontrado")
            return create_response("error", "Permiso 'complete_cultural_work_task' no encontrado", status_code=500)

        # 6. Obtener los roles que tienen el permiso 'complete_cultural_work_task'
        roles_with_permission = db.query(RolePermission.role_id).filter(
            RolePermission.permission_id == complete_permission.permission_id
        ).subquery()

        # 7. Consultar los colaboradores que pertenecen a la finca, están activos y tienen el permiso
        collaborators = db.query(User.user_id, User.name).join(UserRoleFarm, User.user_id == UserRoleFarm.user_id).filter(
            UserRoleFarm.farm_id == farm.farm_id,
            UserRoleFarm.status_id == active_urf_status.status_id,
            UserRoleFarm.role_id.in_(roles_with_permission)
        ).distinct().all()

        # 8. Preparar la lista de colaboradores
        collaborators_list = [{"user_id": c.user_id, "name": c.name} for c in collaborators]

        logger.info(f"Se encontraron {len(collaborators_list)} colaboradores con permiso 'complete_cultural_work_task' en la finca {farm.farm_id}")

        # 9. Retornar la respuesta
        return create_response("success", "Colaboradores obtenidos exitosamente", {"collaborators": collaborators_list})

    except Exception as e:
        logger.error(f"Error al obtener colaboradores: {str(e)}")
        return create_response("error", f"Error interno del servidor: {str(e)}", status_code=500)