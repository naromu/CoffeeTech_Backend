from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from models.models import Notification, User
from utils.security import verify_session_token
from dataBase import get_db_session
from pydantic import BaseModel

from utils.response import create_response, session_token_invalid_response

router = APIRouter()

# Pydantic model para la respuesta de notificación
class NotificationResponse(BaseModel):
    notifications_id: int
    message: Optional[str]
    date: datetime
    type: str
    invitation_id: Optional[int]
    farm_id: Optional[int]
    reminder_time: Optional[datetime]
    is_responded: Optional[bool]

    class Config:
        from_attributes = True

@router.get("/get-notification")
def get_notifications(session_token: str, db: Session = Depends(get_db_session)):
    # Verificar el session_token y obtener el usuario autenticado
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    # Consultar las notificaciones del usuario en la base de datos
    notifications = db.query(Notification).filter(Notification.user_id == user.user_id).all()

    if not notifications:
        return create_response("error", "No se encontraron notificaciones para este usuario.", data=[])

    # Devolver la respuesta exitosa con las notificaciones encontradas
    return create_response("success", "Notificaciones obtenidas exitosamente.", data=notifications)
