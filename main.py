from fastapi import FastAPI
from endpoints import auth, utils, farm ,invitation,notification,collaborators,plots,flowering,transaction,reports,detection
from dataBase import engine
from models.models import Base
from endpoints import culturalWorkTask
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session
from dataBase import get_db_session
from models.models import CulturalWorkTask, User, Plot, Farm, Notification, NotificationType, Status, CulturalWork
from utils.FCM import send_fcm_notification
from datetime import datetime, timedelta
import pytz
import logging

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"


# Crear todas las tablas
Base.metadata.create_all(bind=engine)

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


saved_model_path_vgg = "modelsIA/Modelo-Enfermedades"
saved_model_path_def = "modelsIA/Modelo-Deficiencias"
onnx_model_path = 'modelsIA/Modelo-EstadosMaduracion/best.onnx'

if not os.path.exists(saved_model_path_vgg):
    logger.warning(f"El modelo VGG no se encuentra en la ruta: {saved_model_path_vgg}")
else:
    logger.warning(f"El modelo VGG existe en la ruta: {saved_model_path_vgg}")


# Verificar modelo de deficiencias
if not os.path.exists(saved_model_path_def):
    logger.warning(f"El modelo de deficiencias no se encuentra en la ruta: {saved_model_path_def}")
else:
    logger.warning(f"El modelo de deficiencias existe en la ruta: {saved_model_path_def}")

# Verificar modelo ONNX
if not os.path.exists(onnx_model_path):
    logger.warning(f"El modelo ONNX no se encuentra en la ruta: {onnx_model_path}")
else:
    logger.warning(f"El modelo ONNX existe en la ruta: {onnx_model_path}")


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

# Incluir las rutas de labores culturales
app.include_router(culturalWorkTask.router, prefix="/culturalWorkTask", tags=["culturalWorkTask"])

# Incluir las rutas de transacciones
app.include_router(transaction.router, prefix="/transaction", tags=["transaction"])

app.include_router(reports.router, prefix="/reports", tags=["Reports"])

app.include_router(detection.router, prefix="/detection", tags=["Detection"])

# Incluir las rutas de farm con prefijo y etiqueta

@app.get("/")
def read_root():
    """
    Ruta raíz que retorna un mensaje de bienvenida.

    Returns:
        dict: Un diccionario con un mensaje de bienvenida.
    """
    return {"message": "Welcome to the FastAPI application CoffeeTech!"}


# Función para obtener la hora actual en Colombia
def get_colombia_now():
    colombia_tz = pytz.timezone("America/Bogota")
    return datetime.now(colombia_tz)

# Función que se ejecutará diariamente a las 5 AM
def send_daily_reminders():
    logger.info("Ejecutando tarea programada: Enviar recordatorios diarios")

    # Crear una sesión de base de datos
    db_session = get_db_session()
    db = next(db_session)

    try:
        # Obtener la fecha actual en Colombia
        today = get_colombia_now().date()

        # Obtener el estado "Enviada" para notificaciones
        sent_status = db.query(Status).filter(Status.name == "AsignacionTarea").first()
        if not sent_status:
            logger.error("Estado 'AsignacionTarea' no encontrado en la base de datos.")
            return

        # Obtener el tipo de notificación "Asignacion_tarea"
        notification_type = db.query(NotificationType).filter(NotificationType.name == "Asignacion_tarea").first()
        if not notification_type:
            logger.error("Tipo de notificación 'Asignacion_tarea' no encontrado.")
            return

        # Buscar todas las tareas cuya fecha es hoy y tienen recordatorios activados
        tasks = db.query(CulturalWorkTask).filter(
            CulturalWorkTask.task_date == today
        ).all()

        for task in tasks:
            # Obtener información relacionada de la tarea
            plot = db.query(Plot).filter(Plot.plot_id == task.plot_id).first()
            farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
            cultural_work = db.query(CulturalWork).filter(CulturalWork.cultural_works_id == task.cultural_works_id).first()
            collaborator = db.query(User).filter(User.user_id == task.collaborator_user_id).first()
            owner = db.query(User).filter(User.user_id == task.owner_user_id).first()

            if not plot or not farm or not cultural_work or not collaborator or not owner:
                logger.warning(f"Tarea con ID {task.cultural_work_tasks_id} tiene referencias inválidas.")
                continue

            # Enviar notificación al propietario si está habilitado
            if task.reminder_owner:
                # Mensaje personalizado para el propietario
                message_owner = f"El colaborador {collaborator.name} tiene una tarea de {cultural_work.name} para hoy en el lote {plot.name} de la finca {farm.name}."

                # Crear la notificación en la base de datos
                notification_owner = Notification(
                    message=message_owner,
                    date=get_colombia_now(),
                    user_id=owner.user_id,
                    notification_type_id=notification_type.notification_type_id,
                    farm_id=farm.farm_id,
                    status_id=sent_status.status_id
                )
                db.add(notification_owner)
                db.commit()

                # Enviar notificación FCM si el usuario tiene un token
                if owner.fcm_token:
                    send_fcm_notification(owner.fcm_token, "Recordatorio de Tarea de colaborador", message_owner)
                    logger.info(f"Notificación enviada al propietario: {owner.name}")

            # Enviar notificación al colaborador si está habilitado
            if task.reminder_collaborator:
                # Mensaje para el colaborador
                message_collaborator = f"Tienes una tarea de {cultural_work.name} para hoy en el lote {plot.name} de la finca {farm.name}."

                # Crear la notificación en la base de datos
                notification_collaborator = Notification(
                    message=message_collaborator,
                    date=get_colombia_now(),
                    user_id=collaborator.user_id,
                    notification_type_id=notification_type.notification_type_id,
                    farm_id=farm.farm_id,
                    status_id=sent_status.status_id
                )
                db.add(notification_collaborator)
                db.commit()

                # Enviar notificación FCM si el usuario tiene un token
                if collaborator.fcm_token:
                    send_fcm_notification(collaborator.fcm_token, "Recordatorio de Tarea", message_collaborator)
                    logger.info(f"Notificación enviada al colaborador: {collaborator.name}")
                    
    except Exception as e:
        logger.error(f"Error al enviar recordatorios diarios: {e}")
    finally:
        db.close()

# Inicializar el programador
scheduler = BackgroundScheduler(timezone="America/Bogota")

# Programar la tarea para que se ejecute diariamente a las 5 AM
scheduler.add_job(send_daily_reminders, CronTrigger(hour=5, minute=0))

# Iniciar el programador al iniciar la aplicación
@app.on_event("startup")
def startup_event():
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler iniciado y programado para enviar recordatorios diarios a las 5 AM.")

@app.on_event("shutdown")
def shutdown_event():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler detenido.")