from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from models.models import Farm, UserRoleFarm, User, UnitOfMeasure, Role, Status, StatusType, Permission, RolePermission, Invitation
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import Any, Dict, List
from utils.email import send_email
from utils.FCM import send_fcm_notification

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class InvitationCreate(BaseModel):
    email: EmailStr
    suggested_role: str  # El campo de role es una cadena
    farm_id: int

# Función auxiliar para crear una respuesta uniforme
def create_response(status: str, message: str, data: Dict[str, Any] = None, status_code: int = 200):
    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "message": message,
            "data": data or {}
        }
    )

# Función auxiliar para verificar si el usuario tiene un permiso específico
def has_permission(user: User, permission_name: str, db: Session) -> bool:
    # Obtener los roles asociados al usuario en la finca
    user_roles = db.query(UserRoleFarm).filter(UserRoleFarm.user_id == user.user_id).all()

    for user_role in user_roles:
        # Obtener los permisos asociados al rol del usuario
        role_permissions = db.query(RolePermission).filter(RolePermission.role_id == user_role.role_id).all()

        # Verificar si el permiso está en los permisos asociados al rol
        for role_permission in role_permissions:
            permission = db.query(Permission).filter(Permission.permission_id == role_permission.permission_id).first()
            if permission and permission.name == permission_name:
                return True
    return False

@router.post("/create-invitation")
def create_invitation(invitation_data: InvitationCreate, session_token: str, db: Session = Depends(get_db_session)):
    # Validar el session_token y obtener el usuario autenticado
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()
    # Verificar si la finca existe
    farm = db.query(Farm).filter(Farm.farm_id == invitation_data.farm_id).first()
    if not farm:
        return create_response("error", "Finca no encontrada", status_code=404)

    # Verificar si el usuario está asociado a la finca y cuál es su rol
    user_role_farm = db.query(UserRoleFarm).join(Status, UserRoleFarm.status_id == Status.status_id).join(
        StatusType, Status.status_type_id == StatusType.status_type_id).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == invitation_data.farm_id,
        Status.name == "Activo",  # Verifica que el estatus sea "Activo"
        StatusType.name == "user_role_farm"  # Verifica que el estatus pertenezca al tipo correcto
    ).first()

    if not user_role_farm:
        return create_response("error", "No tienes acceso a esta finca", status_code=403)

    # Obtener el rol del usuario
    role_id = user_role_farm.role_id

    # Verificar el rol sugerido para la invitación
    suggested_role = db.query(Role).filter(Role.name == invitation_data.suggested_role).first()
    if not suggested_role:
        return create_response("error", "El rol sugerido no es válido", status_code=400)

    # Verificar si el rol del usuario tiene el permiso adecuado para invitar al rol sugerido
    if suggested_role.name == "Administrador de finca":
        has_permission_to_invite = db.query(RolePermission).join(Permission).filter(
            RolePermission.role_id == role_id,
            Permission.name == "add_administrador_farm"
        ).first()
        if not has_permission_to_invite:
            return create_response("error", "No tienes permiso para invitar a un Administrador de Finca", status_code=403)

    elif suggested_role.name == "Operador de campo":
        has_permission_to_invite = db.query(RolePermission).join(Permission).filter(
            RolePermission.role_id == role_id,
            Permission.name == "add_operador_farm"
        ).first()
        if not has_permission_to_invite:
            return create_response("error", "No tienes permiso para invitar a un Operador de Campo", status_code=403)

    else:
        return create_response("error", "No puedes invitar", status_code=403)

    # Verificar si el usuario ya pertenece a la finca
    existing_user = db.query(User).filter(User.email == invitation_data.email).first()
    if not existing_user:
        return create_response("error", "El usuario no está registrado", status_code=404)

    # Obtener el FCM token del usuario
    fcm_token = existing_user.fcm_token  # Asegúrate de que este campo esté presente en la tabla `users`

    existing_role_farm = db.query(UserRoleFarm).join(Status, UserRoleFarm.status_id == Status.status_id).join(
        StatusType, Status.status_type_id == StatusType.status_type_id).filter(
        UserRoleFarm.user_id == existing_user.user_id,
        UserRoleFarm.farm_id == invitation_data.farm_id,
        Status.name == "Activo"
    ).first()

    if existing_role_farm:
        return create_response("error", "El usuario ya pertenece a esta finca", status_code=400)

    # Crear una nueva invitación
    try:
        new_invitation = Invitation(
            email=invitation_data.email,
            suggested_role=invitation_data.suggested_role,
            farm_id=invitation_data.farm_id
        )
        db.add(new_invitation)
        db.commit()
        db.refresh(new_invitation)

        # Enviar correo de invitación
        send_email(invitation_data.email, invitation_data.farm_id, 'invitation', farm.name, user.name, invitation_data.suggested_role)

        # Enviar notificación FCM al usuario
        if fcm_token:
            title = "Nueva Invitación"
            body = f"Has sido invitado como {invitation_data.suggested_role} a la finca {farm.name}"
            send_fcm_notification(fcm_token, title, body)
        else:
            logger.warning("No se pudo enviar la notificación push. No se encontró el token FCM del usuario.")
    except Exception as e:
        db.rollback()  # Hacer rollback en caso de un error
        logger.error(f"Error creando la invitación: {str(e)}")
        return create_response("error", f"Error creando la invitación: {str(e)}", status_code=500)

    return create_response("success", "Invitación creada exitosamente", {"invitation_id": new_invitation.invitation_id}, status_code=201)

@router.post("/accept-invitation")
def accept_invitation(invitation_id: int, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    invitation = db.query(Invitation).filter(Invitation.invitation_id == invitation_id).first()
    if not invitation:
        return create_response("error", "Invitación no encontrada", status_code=404)

    # Obtener el ID del rol basado en el nombre sugerido
    role = db.query(Role).filter(Role.name == invitation.suggested_role).first()
    if not role:
        return create_response("error", "Rol no encontrado", status_code=400)

    try:
        # Marcar la invitación como aceptada
        invitation.status_id = 16  # ID para "Aceptada"
        invitation.is_active = False  # Marcar como no activa
        db.commit()
        logger.info(f"Invitación actualizada: {invitation.status_id}, {invitation.is_active}")

        # Asignar el usuario a la finca con el role_id correspondiente
        user_role_farm = UserRoleFarm(
            user_id=user.user_id,
            farm_id=invitation.farm_id,
            role_id=role.role_id  # Usa el ID del rol aquí
        )
        db.add(user_role_farm)
        db.commit()
        logger.info("Usuario asignado a la finca")
    except Exception as e:
        db.rollback()
        logger.error(f"Error aceptando la invitación: {str(e)}")
        return create_response("error", f"Error aceptando la invitación: {str(e)}", status_code=500)

    return create_response("success", "Invitación aceptada exitosamente", {"invitation_id": invitation.invitation_id}, status_code=200)

@router.post("/reject-invitation")
def reject_invitation(invitation_id: int, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    invitation = db.query(Invitation).filter(Invitation.invitation_id == invitation_id).first()
    if not invitation:
        return create_response("error", "Invitación no encontrada", status_code=404)

    if not invitation.is_active:
        return create_response("error", "La invitación ya fue gestionada", status_code=400)

    try:
        invitation.status_id = 17  # ID para "Rechazada"
        invitation.is_active = False  # Marcar como no activa
        db.commit()
        db.refresh(invitation)
    except Exception as e:
        db.rollback()
        logger.error(f"Error rechazando la invitación: {str(e)}")
        return create_response("error", f"Error rechazando la invitación: {str(e)}", status_code=500)

    return create_response("success", "Invitación rechazada exitosamente", {"invitation_id": invitation.invitation_id}, status_code=200)
