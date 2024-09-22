from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from models.models import Farm, UserRoleFarm, User, UnitOfMeasure, Role, Status, StatusType, Permission, RolePermission, Invitation
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import Any, Dict, List
from utils.email import send_email


# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class InvitationCreate(BaseModel):
    email: EmailStr
    suggested_role: str  # El campo de role es una cadena
    farm_id: int
    
# Función auxiliar para crear una respuesta uniforme
def create_response(status: str, message: str, data: Dict[str, Any] = None):
    return {
        "status": status,
        "message": message,
        "data": data or {}
    }
    
@router.post("/create-invitation")
def create_invitation(invitation_data: InvitationCreate, session_token: str, db: Session = Depends(get_db_session)):
    # Validar el session_token y obtener el usuario
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

    # Verificar si la finca existe
    farm = db.query(Farm).filter(Farm.farm_id == invitation_data.farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Finca no encontrada")

    # Verificar si el usuario es el dueño o administrador de la finca
    user_role_farm = db.query(UserRoleFarm).filter_by(farm_id=invitation_data.farm_id, user_id=user.user_id).first()
    if not user_role_farm or user_role_farm.role_id not in [1, 2]:  # 1 = Dueño, 2 = Administrador
        raise HTTPException(status_code=403, detail="No tienes permisos para invitar a colaboradores a esta finca")

    # Encuentra el propietario de la finca
    owner_user = db.query(User).join(UserRoleFarm, User.user_id == UserRoleFarm.user_id).filter(
        UserRoleFarm.farm_id == invitation_data.farm_id,
        UserRoleFarm.role_id == 1  # 1 = Propietario
    ).first()

    if not owner_user or owner_user.name is None:
        raise HTTPException(status_code=404, detail="Propietario no encontrado o sin nombre asignado.")

    # Crear una nueva invitación
    try:
        new_invitation = Invitation(
            email=invitation_data.email,
            suggested_role=invitation_data.suggested_role,
            farm_id=invitation_data.farm_id,
            status="Pendiente"  # Aquí puedes poner None o un ID inicial si deseas
            
        )
        db.add(new_invitation)
        db.commit()
        db.refresh(new_invitation)

        # Enviar correo de invitación
        send_email(invitation_data.email, invitation_data.farm_id, 'invitation', farm.name, owner_user.name, invitation_data.suggested_role )
    except Exception as e:
        db.rollback()  # Hacer rollback en caso de un error
        raise HTTPException(status_code=500, detail=f"Error creando la invitación: {str(e)}")

    return {"message": "Invitación creada exitosamente", "invitation_id": new_invitation.invitation_id}

@router.post("/accept-invitation")
def accept_invitation(invitation_id: int, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

    invitation = db.query(Invitation).filter(Invitation.invitation_id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitación no encontrada")

    # Obtener el ID del rol basado en el nombre sugerido
    role = db.query(Role).filter(Role.name == invitation.suggested_role).first()
    if not role:
        raise HTTPException(status_code=400, detail="Rol no encontrado")

    try:
        # Marcar la invitación como aceptada
        invitation.status_id = 16  # ID para "Aceptada"
        invitation.is_active = False  # Marcar como no activa
        db.commit()
        print(f"Invitación actualizada: {invitation.status_id}, {invitation.is_active}")

        # Asignar el usuario a la finca con el role_id correspondiente
        user_role_farm = UserRoleFarm(
            user_id=user.user_id,
            farm_id=invitation.farm_id,
            role_id=role.role_id  # Usa el ID del rol aquí
        )
        db.add(user_role_farm)
        db.commit()
        print("Usuario asignado a la finca")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error aceptando la invitación: {str(e)}")

    return create_response("success", "Invitación aceptada exitosamente", {"invitation_id": invitation.invitation_id})


@router.post("/reject-invitation")
def reject_invitation(invitation_id: int, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        raise HTTPException(status_code=400, detail="Token inválido o expirado")

    invitation = db.query(Invitation).filter(Invitation.invitation_id == invitation_id).first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitación no encontrada")

    if not invitation.is_active:
        raise HTTPException(status_code=400, detail="La invitación ya fue gestionada")

    try:
        invitation.status_id = 17  # ID para "Rechazada"
        invitation.is_active = False  # Marcar como no activa
        db.commit()
        db.refresh(invitation)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error rechazando la invitación: {str(e)}")

    return create_response("success", "Invitación rechazada exitosamente", {"invitation_id": invitation.invitation_id})
