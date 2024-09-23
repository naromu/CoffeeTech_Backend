from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from models.models import  UserRoleFarm,  Invitation
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from utils.email import send_email

router = APIRouter()

from utils.response import session_token_invalid_response
from utils.response import create_response

@router.post("/notification/accept-invitation")
def accept_invitation(
    session_token: str, 
    invitation_id: int, 
    response: str,  # 'aceptar' o 'rechazar'
    db: Session = Depends(get_db_session)
):
    # Validar el session_token y obtener el usuario
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        session_token_invalid_response()

    # Verificar si la invitación existe
    invitation = db.query(Invitation).filter(Invitation.invitation_id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitación no encontrada")
    
    # Verificar si el usuario es el destinatario de la invitación
    if invitation.email != user.email:
        raise HTTPException(status_code=403, detail="No tienes permisos para aceptar o rechazar esta invitación")

    # Actualizar el estado de la invitación dependiendo de la respuesta
    if response.lower() == 'aceptar':
        invitation.status = 'Aceptada'
        
        # Asignar al usuario en la tabla user_role_farm con el rol sugerido
        new_user_role_farm = UserRoleFarm(
            user_id=user.user_id,
            farm_id=invitation.farm_id,
            role_id=invitation.suggested_role
        )
        db.add(new_user_role_farm)
    
    elif response.lower() == 'rechazar':
        invitation.status = 'Rechazada'
    else:
        raise HTTPException(status_code=400, detail="Respuesta inválida. Debe ser 'aceptar' o 'rechazar'.")

    # Guardar cambios en la base de datos
    try:
        db.commit()
    except Exception as e:
        db.rollback()  # Revertir cambios si ocurre un error
        raise HTTPException(status_code=500, detail=f"Error al actualizar la invitación: {str(e)}")

    return {
        "message": f"Invitación {response.lower()} exitosamente",
        "invitation_id": invitation.invitation_id,
        "status": invitation.status
    }