from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import date
from models.models import CulturalWorkTask, User, Plot, CulturalWork
from utils.security import verify_session_token
from dataBase import get_db_session
from utils.response import create_response
from pydantic import BaseModel, EmailStr
import logging
from pydantic import BaseModel, Field
from datetime import date
from typing import List, Optional
from utils.status import get_status

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class CreateCulturalWorkTaskRequest(BaseModel):
    cultural_works_id: int = Field(..., description="ID de la tarea de labor cultural.")
    plot_id: int = Field(..., description="ID del lote donde se asignará la tarea.")
    collaborator_user_id: int = Field(..., description="ID del colaborador asignado.")
    task_date: date = Field(..., description="Fecha de la labor cultural.")  
    reminder_owner: bool = Field(False, description="Indica si el propietario recibirá un recordatorio.")
    reminder_collaborator: bool = Field(False, description="Indica si el colaborador recibirá un recordatorio.")
    
class CulturalWorkTaskResponse(BaseModel):
    task_id: int
    cultural_works_id: int
    plot_id: int
    status: str
    collaborator_user_id: int
    owner_user_id: int
    task_date: str  
    reminder_owner: bool
    reminder_collaborator: bool
    
class GlobalCulturalWorkTaskResponse(BaseModel):
    task_id: int
    cultural_works_id: int
    plot_id: int
    status: str
    collaborator_user_id: int
    owner_user_id: int
    task_date: str  
    reminder_owner: bool
    reminder_collaborator: bool
    
class FilterCulturalWorkTasksRequest(BaseModel):
    labor_type: Optional[str] = Field(None, description="Tipo de labor a filtrar.")
    assignment_type: Optional[str] = Field(None, description="Tipo de asignación a filtrar.")
    status: Optional[str] = Field(None, description="Estado de la tarea a filtrar.")

class FilterCulturalWorkTaskResponse(BaseModel):
    task_id: int
    cultural_works_id: int
    plot_id: int
    status: str
    collaborator_user_id: int
    owner_user_id: int
    task_date: str  # o puedes usar `date` si prefieres
    reminder_owner: bool
    reminder_collaborator: bool
    
class AdvancedFilterCulturalWorkTasksRequest(BaseModel):
    labor_type: Optional[str] = Field(None, description="Tipo de labor a filtrar.")
    farm_id: Optional[int] = Field(None, description="ID de la finca a filtrar.")
    plot_id: Optional[int] = Field(None, description="ID del lote a filtrar.")
    assignment_type: Optional[str] = Field(None, description="Tipo de asignación a filtrar.")

class AdvancedFilterCulturalWorkTaskResponse(BaseModel):
    task_id: int
    cultural_works_id: int
    plot_id: int
    status: str
    collaborator_user_id: int
    owner_user_id: int
    task_date: str  # o puedes usar `date` si prefieres
    reminder_owner: bool
    reminder_collaborator: bool
    
class UpdateCulturalWorkTaskRequest(BaseModel):
    task_id: int = Field(..., description="ID de la tarea de labor cultural a actualizar.")
    labor_type: Optional[str] = Field(None, description="Nuevo tipo de labor.")
    task_date: Optional[str] = Field(None, description="Nueva fecha de la tarea (formato: YYYY-MM-DD).")
    collaborator_user_id: Optional[int] = Field(None, description="Nuevo ID del colaborador asignado.")
    
class CompleteCulturalWorkTaskRequest(BaseModel):
    task_id: int = Field(..., description="ID de la tarea de labor cultural a marcar como terminada.")
    
class DeleteCulturalWorkTaskRequest(BaseModel):
    task_id: int = Field(..., description="ID de la tarea de labor cultural a eliminar.")





@router.post("/create-cultural-work-task")
def create_cultural_work_task(request: CreateCulturalWorkTaskRequest, session_token: str, db: Session = Depends(get_db_session)):
    """
    Crear una nueva tarea de labor cultural.
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o usuario no autenticado")

    # Verificar que el usuario tenga el rol adecuado (Propietario o Administrador)
    if user.role not in ['Propietario', 'Administrador de finca']:
        raise HTTPException(status_code=403, detail="No tienes permiso para crear esta tarea")

    # Verificar que el colaborador esté activo y tenga un rol menor al usuario actual
    collaborator = db.query(User).filter(User.user_id == request.collaborator_user_id, User.is_active == True).first()
    if not collaborator:
        raise HTTPException(status_code=400, detail="El colaborador no está activo o no existe")

    if collaborator.role not in ['Trabajador'] or collaborator.role == user.role:
        raise HTTPException(status_code=403, detail="El colaborador debe tener un rol menor al tuyo")

    # Verificar si la fecha es anterior, igual o futura
    today = date.today()
    pending_status = get_status(db, "Pendiente", "Task")
    completed_status = get_status(db, "Completado", "Task")
    # Determinar el estado de la tarea según la fecha
    task_status = completed_status if request.date < today else pending_status


    # Verificar que el lote y la labor cultural existan
    plot = db.query(Plot).filter(Plot.plot_id == request.plot_id).first()
    if not plot:
        raise HTTPException(status_code=404, detail="El lote no existe")

    cultural_work = db.query(CulturalWork).filter(CulturalWork.cultural_works_id == request.cultural_works_id).first()
    if not cultural_work:
        raise HTTPException(status_code=404, detail="La tarea de labor cultural no existe")

    # Crear la tarea de labor cultural
    new_task = CulturalWorkTask(
        cultural_works_id=request.cultural_works_id,
        plot_id=request.plot_id,
        status=task_status,
        reminder_owner=request.reminder_owner,
        reminder_collaborator=request.reminder_collaborator,
        collaborator_user_id=request.collaborator_user_id,
        owner_user_id=user.user_id
    )

    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    # Mostrar mensaje de confirmación y configurar recordatorios si es necesario
    if request.date >= today:
        return create_response("success", "Labor cultural creada. Puedes configurar recordatorios.", {"task_id": new_task.cultural_work_tasks_id})
    else:
        return create_response("success", "Labor cultural creada como 'terminada'", {"task_id": new_task.cultural_work_tasks_id})
    
    

@router.get("/list-cultural-work-tasks/{plot_id}", response_model=List[CulturalWorkTaskResponse])
def list_cultural_work_tasks(plot_id: int, session_token: str, db: Session = Depends(get_db_session)):
    """
    Listar las tareas de labores culturales para un lote específico.
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o usuario no autenticado")

    # Verificar que el lote existe
    plot = db.query(Plot).filter(Plot.plot_id == plot_id).first()
    if not plot:
        raise HTTPException(status_code=404, detail="El lote no existe")

    # Listar tareas de labores culturales
    tasks_query = db.query(CulturalWorkTask).filter(CulturalWorkTask.plot_id == plot_id)

    # Filtrar las tareas según el rol del usuario
    if user.role == 'Operador de campo':
        tasks_query = tasks_query.filter(CulturalWorkTask.collaborator_user_id == user.user_id)
    elif user.role in ['Propietario', 'Administrador de finca']:
        # Los propietarios y administradores pueden ver todas las tareas
        pass
    else:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver las tareas")

    tasks = tasks_query.all()

    if not tasks:
        return []  # Retornar lista vacía si no hay tareas

    # Preparar la respuesta
    response_tasks = [
        CulturalWorkTaskResponse(
            task_id=task.cultural_work_tasks_id,
            cultural_works_id=task.cultural_works_id,
            plot_id=task.plot_id,
            status=task.status,
            collaborator_user_id=task.collaborator_user_id,
            owner_user_id=task.owner_user_id,
            task_date=task.task_date.isoformat(),  # Convertir a formato de cadena
            reminder_owner=task.reminder_owner,
            reminder_collaborator=task.reminder_collaborator
        )
        for task in tasks
    ]

    return response_tasks


@router.get("/list-global-cultural-work-tasks", response_model=List[GlobalCulturalWorkTaskResponse])
def list_global_cultural_work_tasks(session_token: str, db: Session = Depends(get_db_session)):
    """
    Listar globalmente todas las tareas de labores culturales.
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o usuario no autenticado")

    # Consultar todas las tareas de labores culturales
    tasks_query = db.query(CulturalWorkTask)

    # Filtrar las tareas según el rol del usuario
    if user.role == 'Operador de campo':
        # Solo se listan las tareas asignadas al operador
        tasks_query = tasks_query.filter(CulturalWorkTask.collaborator_user_id == user.user_id)
    elif user.role not in ['Propietario', 'Administrador de finca']:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver las tareas")

    tasks = tasks_query.all()

    if not tasks:
        return []  # Retornar lista vacía si no hay tareas

    # Preparar la respuesta
    response_tasks = [
        GlobalCulturalWorkTaskResponse(
            task_id=task.cultural_work_tasks_id,
            cultural_works_id=task.cultural_works_id,
            plot_id=task.plot_id,
            status=task.status,
            collaborator_user_id=task.collaborator_user_id,
            owner_user_id=task.owner_user_id,
            task_date=task.task_date.isoformat(),  # Convertir a formato de cadena
            reminder_owner=task.reminder_owner,
            reminder_collaborator=task.reminder_collaborator
        )
        for task in tasks
    ]

    return response_tasks


@router.post("/filter-cultural-work-tasks", response_model=List[FilterCulturalWorkTaskResponse])
def filter_cultural_work_tasks(
    request: FilterCulturalWorkTasksRequest, 
    session_token: str, 
    db: Session = Depends(get_db_session)
):
    """
    Filtrar tareas de labores culturales por tipo de labor, tipo de asignación y estado.
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o usuario no autenticado")

    # Iniciar la consulta base
    tasks_query = db.query(CulturalWorkTask)

    # Aplicar filtros si se proporcionan
    if request.labor_type:
        tasks_query = tasks_query.filter(CulturalWorkTask.labor_type == request.labor_type)
    
    if request.assignment_type:
        tasks_query = tasks_query.filter(CulturalWorkTask.assignment_type == request.assignment_type)
    
    if request.status:
        tasks_query = tasks_query.filter(CulturalWorkTask.status == request.status)

    # Ejecutar la consulta
    tasks = tasks_query.all()

    if not tasks:
        return []  # Retornar lista vacía si no hay tareas que coincidan

    # Preparar la respuesta
    response_tasks = [
        FilterCulturalWorkTaskResponse(
            task_id=task.cultural_work_tasks_id,
            cultural_works_id=task.cultural_works_id,
            plot_id=task.plot_id,
            status=task.status,
            collaborator_user_id=task.collaborator_user_id,
            owner_user_id=task.owner_user_id,
            task_date=task.task_date.isoformat(),  # Convertir a formato de cadena
            reminder_owner=task.reminder_owner,
            reminder_collaborator=task.reminder_collaborator
        )
        for task in tasks
    ]

    return response_tasks


@router.post("/advanced-filter-cultural-work-tasks", response_model=List[AdvancedFilterCulturalWorkTaskResponse])
def advanced_filter_cultural_work_tasks(
    request: AdvancedFilterCulturalWorkTasksRequest, 
    session_token: str, 
    db: Session = Depends(get_db_session)
):
    """
    Filtrar tareas de labores culturales por tipo de labor, finca, lote y tipo de asignación.
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o usuario no autenticado")

    # Iniciar la consulta base
    tasks_query = db.query(CulturalWorkTask)

    # Aplicar filtros si se proporcionan
    if request.labor_type:
        tasks_query = tasks_query.filter(CulturalWorkTask.labor_type == request.labor_type)
    
    if request.farm_id:
        tasks_query = tasks_query.filter(CulturalWorkTask.farm_id == request.farm_id)

    if request.plot_id:
        tasks_query = tasks_query.filter(CulturalWorkTask.plot_id == request.plot_id)
    
    if request.assignment_type:
        tasks_query = tasks_query.filter(CulturalWorkTask.assignment_type == request.assignment_type)

    # Ejecutar la consulta
    tasks = tasks_query.all()

    if not tasks:
        return []  # Retornar lista vacía si no hay tareas que coincidan

    # Preparar la respuesta
    response_tasks = [
        AdvancedFilterCulturalWorkTaskResponse(
            task_id=task.cultural_work_tasks_id,
            cultural_works_id=task.cultural_works_id,
            plot_id=task.plot_id,
            status=task.status,
            collaborator_user_id=task.collaborator_user_id,
            owner_user_id=task.owner_user_id,
            task_date=task.task_date.isoformat(),  # Convertir a formato de cadena
            reminder_owner=task.reminder_owner,
            reminder_collaborator=task.reminder_collaborator
        )
        for task in tasks
    ]

    return response_tasks

@router.post("/update-cultural-work-task", summary="Actualizar tarea de labor cultural", description="Actualiza el tipo, fecha y colaborador asignado de una tarea de labor cultural.")
def update_cultural_work_task(request: UpdateCulturalWorkTaskRequest, session_token: str, db: Session = Depends(get_db_session)):
    """
    Actualiza el tipo, fecha y colaborador asignado de una tarea de labor cultural.

    Args:
        request (UpdateCulturalWorkTaskRequest): Contiene la nueva información de la tarea.
        session_token (str): Token de sesión del usuario para autenticar la solicitud.
        db (Session): Sesión de base de datos proporcionada por la dependencia.

    Returns:
        dict: Respuesta indicando el estado del proceso de actualización de la tarea.
    """
    # Verificar el token de sesión

    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o usuario no autenticado")

    # Obtener la tarea de labor cultural
    task = db.query(CulturalWorkTask).filter(CulturalWorkTask.cultural_work_tasks_id == request.task_id).first()
    if not task:
        logger.warning("La tarea con ID %s no existe", request.task_id)
        return create_response("error", "La tarea no existe")

    # Verificar si el usuario es el creador de la tarea
    if task.owner_user_id != user.user_id:
        logger.warning("El usuario no tiene permiso para editar esta tarea")
        return create_response("error", "No tienes permiso para editar esta tarea")

    # Actualizar tipo de labor si se proporciona
    if request.labor_type:
        task.labor_type = request.labor_type

    # Actualizar fecha de la tarea si se proporciona
    if request.task_date:
        task.task_date = request.task_date

    # Actualizar colaborador asignado si se proporciona
    if request.collaborator_user_id:
        # Aquí puedes incluir lógica adicional para verificar si el colaborador es válido
        task.collaborator_user_id = request.collaborator_user_id

    # Guardar los cambios en la base de datos
    try:
        db.commit()
        db.refresh(task)  # Actualiza el objeto con los nuevos valores de la base de datos
        logger.info("Tarea actualizada exitosamente con ID: %s", task.cultural_work_tasks_id)
        return create_response("success", "Tarea de labor cultural actualizada correctamente", {
            "task_id": task.cultural_work_tasks_id,
            "labor_type": task.labor_type,
            "task_date": task.task_date.isoformat(),  # Formato de fecha como cadena
            "collaborator_user_id": task.collaborator_user_id
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al actualizar la tarea: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al actualizar la tarea: {str(e)}")


@router.post("/complete-cultural-work-task", summary="Marcar tarea de labor cultural como terminada", description="Marca una tarea de labor cultural como terminada.")
def complete_cultural_work_task(request: CompleteCulturalWorkTaskRequest, session_token: str, db: Session = Depends(get_db_session)):
    """
    Marca una tarea de labor cultural como terminada.

    Args:
        request (CompleteCulturalWorkTaskRequest): Contiene el ID de la tarea a completar.
        session_token (str): Token de sesión del usuario para autenticar la solicitud.
        db (Session): Sesión de base de datos proporcionada por la dependencia.

    Returns:
        dict: Respuesta indicando el estado del proceso de marcar la tarea como terminada.
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o usuario no autenticado")

    # Obtener la tarea de labor cultural
    task = db.query(CulturalWorkTask).filter(CulturalWorkTask.cultural_work_tasks_id == request.task_id).first()
    if not task:
        logger.warning("La tarea con ID %s no existe", request.task_id)
        return create_response("error", "La tarea no existe")

    # Verificar si el usuario es el creador de la tarea
    if task.owner_user_id != user.user_id:
        logger.warning("El usuario no tiene permiso para marcar esta tarea como terminada")
        return create_response("error", "No tienes permiso para marcar esta tarea como terminada")

    # Marcar la tarea como terminada
    try:
        task.status = "Terminada"  # Cambia el estado de la tarea a "Terminada"
        db.commit()
        db.refresh(task)  # Actualiza el objeto con los nuevos valores de la base de datos
        logger.info("Tarea marcada como terminada con ID: %s", task.cultural_work_tasks_id)
        return create_response("success", "Tarea de labor cultural marcada como terminada correctamente", {
            "task_id": task.cultural_work_tasks_id,
            "status": task.status
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al marcar la tarea como terminada: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al marcar la tarea como terminada: {str(e)}")

@router.post("/delete-cultural-work-task", summary="Eliminar tarea de labor cultural", description="Elimina una tarea de labor cultural.")
def delete_cultural_work_task(request: DeleteCulturalWorkTaskRequest, session_token: str, db: Session = Depends(get_db_session)):
    """
    Elimina una tarea de labor cultural.

    Args:
        request (DeleteCulturalWorkTaskRequest): Contiene el ID de la tarea a eliminar.
        session_token (str): Token de sesión del usuario para autenticar la solicitud.
        db (Session): Sesión de base de datos proporcionada por la dependencia.

    Returns:
        dict: Respuesta indicando el estado del proceso de eliminación de la tarea.
    """
    # Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido o usuario no autenticado")

    # Obtener la tarea de labor cultural
    task = db.query(CulturalWorkTask).filter(CulturalWorkTask.cultural_work_tasks_id == request.task_id).first()
    if not task:
        logger.warning("La tarea con ID %s no existe", request.task_id)
        return create_response("error", "La tarea no existe")

    # Verificar si el usuario es el creador de la tarea
    if task.owner_user_id != user.user_id:
        logger.warning("El usuario no tiene permiso para eliminar esta tarea")
        return create_response("error", "No tienes permiso para eliminar esta tarea")

    # Eliminar la tarea
    try:
        db.delete(task)  # Elimina la tarea de la base de datos
        db.commit()
        logger.info("Tarea eliminada con ID: %s", task.cultural_work_tasks_id)
        return create_response("success", "Tarea de labor cultural eliminada correctamente", {
            "task_id": task.cultural_work_tasks_id
        })
    except Exception as e:
        db.rollback()
        logger.error("Error al eliminar la tarea: %s", str(e))
        raise HTTPException(status_code=500, detail=f"Error al eliminar la tarea: {str(e)}")





