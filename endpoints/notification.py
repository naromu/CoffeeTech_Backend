from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Any, Optional
from datetime import datetime
from models.models import Notification, User
from utils.security import verify_session_token
from dataBase import get_db_session
from pydantic import BaseModel
import logging
from fastapi.responses import ORJSONResponse
from decimal import Decimal

# Configurar el logger
logging.basicConfig(level=logging.INFO)  # Cambia a DEBUG si necesitas más detalles
logger = logging.getLogger(__name__)

router = APIRouter()

# Pydantic model para la respuesta de notificación
class NotificationResponse(BaseModel):
    notifications_id: int  # ID de la notificación
    message: Optional[str]  # Mensaje de la notificación
    date: datetime  # Fecha de la notificación
    notification_type: Optional[str]  # Tipo de notificación
    invitation_id: Optional[int]  # ID de la invitación asociada (si aplica)
    farm_id: Optional[int]  # ID de la finca asociada (si aplica)
    status: Optional[str]  # Estado de la notificación

    class Config:
        from_attributes = True  # Permitir que los atributos se usen como parámetros de entrada
        json_encoders = {
            datetime: lambda v: v.isoformat()  # Serializar fechas en formato ISO
        }

@router.get("/get-notification")
def get_notifications(session_token: str, db: Session = Depends(get_db_session)):
    """
    Endpoint para obtener las notificaciones de un usuario autenticado.

    Parámetros:
    - session_token: Token de sesión del usuario.
    - db: Sesión de la base de datos (inyectada automáticamente).

    Retorna:
    - Respuesta con las notificaciones del usuario.
    """
    # Verificar el session_token y obtener el usuario autenticado
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning(f"Sesión inválida para el token: {session_token}")
        return session_token_invalid_response()

    logger.info(f"Usuario autenticado: {user.user_id} - {user.name}")

    # Consultar las notificaciones del usuario en la base de datos
    notifications = db.query(Notification).filter(Notification.user_id == user.user_id).all()

    logger.info(f"Notificaciones obtenidas: {len(notifications)}")

    if not notifications:
        logger.info("No hay notificaciones para este usuario.")
        return create_response("success", "No hay notificaciones para este usuario.", data=[])

    # Mostrar las notificaciones obtenidas antes de serializarlas
    for notification in notifications:
        logger.debug(f"Notificación obtenida: {notification}")
        logger.debug(f"Notificación ID: {notification.notifications_id}, Status ID: {notification.status_id}")

        # Verificar si la relación 'status' está cargada y no es None
        if notification.status is None:
            logger.warning(f"La notificación con ID {notification.notifications_id} no tiene 'status'.")
        else:
            logger.debug(f"Status: {notification.status.name}")

    # Convertir las notificaciones a un formato que Pydantic pueda manejar
    try:
        notification_responses = [
            NotificationResponse(
                notifications_id=notification.notifications_id,
                message=notification.message,
                date=notification.date,
                notification_type=notification.notification_type.name if notification.notification_type else None,
                invitation_id=notification.invitation_id,
                farm_id=notification.farm_id,
                status=notification.status.name if notification.status else None
            )
            for notification in notifications
        ]
        logger.info(f"Notificaciones serializadas correctamente: {len(notification_responses)}")
        
        # Convertir a dict usando Pydantic
        notification_responses_dict = [n.dict() for n in notification_responses]
    except Exception as e:
        # Loguear el error exacto de serialización
        logger.error(f"Error de serialización: {e}")
        return create_response("error", f"Error de serialización: {str(e)}", data=[])

    # Devolver la respuesta exitosa con las notificaciones encontradas
    return create_response("success", "Notificaciones obtenidas exitosamente.", data=notification_responses_dict)

def create_response(
    status: str,
    message: str,
    data: Optional[Any] = None,
    status_code: int = 200
) -> ORJSONResponse:
    """
    Crea una respuesta estructurada para el API.

    Parámetros:
    - status: Estado de la respuesta (ej. "success", "error").
    - message: Mensaje adicional sobre la respuesta.
    - data: Datos opcionales a incluir en la respuesta.
    - status_code: Código de estado HTTP (default es 200).

    Retorna:
    - Respuesta en formato ORJSONResponse.
    """
    return ORJSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "message": message,
            "data": data or {}
        }
    )

def session_token_invalid_response() -> ORJSONResponse:
    """
    Crea una respuesta para el caso en que el token de sesión es inválido.

    Retorna:
    - Respuesta indicando que las credenciales han expirado.
    """
    return create_response(
        status="error",
        message="Credenciales expiradas, cerrando sesión.",
        data={},
        status_code=401
    )
