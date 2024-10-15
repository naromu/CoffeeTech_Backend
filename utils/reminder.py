from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models.models import CulturalWorkTask, User
from firebase_admin import messaging
import logging
from FCM import send_fcm_notification
from apscheduler.schedulers.background import BackgroundScheduler

# Configurar el logger
logger = logging.getLogger(__name__)

def send_reminders(db: Session):
    """
    Función que se ejecuta todos los días a las 5:00 AM para enviar recordatorios de tareas pendientes.
    """
    today = datetime.today().date()

    # Obtener todas las tareas pendientes para hoy o anteriores
    pending_tasks = db.query(CulturalWorkTask).filter(
        CulturalWorkTask.task_date <= today,
        CulturalWorkTask.status == 'Pendiente'  # Asume que el estado de pendiente es "Pendiente"
    ).all()

    for task in pending_tasks:
        # Obtener el colaborador y el propietario relacionados con la tarea
        collaborator = db.query(User).filter(User.user_id == task.collaborator_user_id).first()
        owner = db.query(User).filter(User.user_id == task.owner_user_id).first()

        # Enviar notificación al colaborador si tiene recordatorio activado
        if task.reminder_collaborator and collaborator and collaborator.fcm_token:
            send_fcm_notification(
                fcm_token=collaborator.fcm_token,
                title="Recordatorio de Tarea Pendiente",
                body=f"Tienes una tarea pendiente asignada para hoy en la finca {task.plot_id}."
            )
            logger.info(f"Notificación enviada al colaborador {collaborator.name}")

        # Enviar notificación al propietario si tiene recordatorio activado
        if task.reminder_owner and owner and owner.fcm_token:
            send_fcm_notification(
                fcm_token=owner.fcm_token,
                title="Recordatorio de Tarea Pendiente",
                body=f"Tienes una tarea pendiente asignada para hoy en la finca {task.plot_id}."
            )
            logger.info(f"Notificación enviada al propietario {owner.name}")
            
            
scheduler = BackgroundScheduler()

def start_scheduler():
    scheduler.add_job(send_reminders, 'cron', hour=5, minute=0)  # Ejecutar a las 5:00 AM cada día
    scheduler.start()

@app.on_event("startup")
def startup_event():
    start_scheduler()