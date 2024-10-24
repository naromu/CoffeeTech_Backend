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
from models.models import Farm, UserRoleFarm, User, UnitOfMeasure, Role, Status, StatusType, Permission, RolePermission, Invitation, Notification
from fastapi import APIRouter, Depends
from utils.response import create_response
from utils.response import session_token_invalid_response
from utils.status import get_status
from models.models import NotificationType

import pytz

bogota_tz = pytz.timezone("America/Bogota")


from datetime import datetime
from models.models import Invitation, Notification, Status




# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class InvitationCreate(BaseModel):
    """
    Modelo para la creación de una invitación.

    Attributes:
        email (EmailStr): Dirección de correo electrónico del usuario a invitar.
        suggested_role (str): Rol sugerido para el usuario invitado.
        farm_id (int): Identificador de la finca a la que se invita.
    """
    email: EmailStr
    suggested_role: str  # El campo de role es una cadena
    farm_id: int

# Función auxiliar para crear una respuesta uniforme

# Función auxiliar para verificar si el usuario tiene un permiso específico
def has_permission(user: User, permission_name: str, db: Session) -> bool:
    """
    Verifica si el usuario tiene un permiso específico.

    Args:
        user (User): Usuario a verificar.
        permission_name (str): Nombre del permiso a verificar.
        db (Session): Sesión de base de datos.

    Returns:
        bool: True si el usuario tiene el permiso, False en caso contrario.
    """
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
    """
    Crea una invitación para un usuario a una finca.

    Args:
        invitation_data (InvitationCreate): Datos de la invitación a crear.
        session_token (str): Token de sesión del usuario autenticado.
        db (Session): Sesión de base de datos.

    Returns:
        JSONResponse: Respuesta con el resultado de la creación de la invitación.
    """
    # Validar el session_token y obtener el usuario autenticado (el invitador)
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()
    
    # Verificar si la finca existe
    farm = db.query(Farm).filter(Farm.farm_id == invitation_data.farm_id).first()
    if not farm:
        return create_response("error", "Finca no encontrada", status_code=404)

    # Verificar si el usuario (invitador) está asociado a la finca y cuál es su rol
    active_status = get_status(db, "Activo", "user_role_farm")
    if not active_status:
        return create_response("error", "El estado 'Activo' no fue encontrado para 'user_role_farm'", status_code=400)

    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == invitation_data.farm_id,
        UserRoleFarm.status_id == active_status.status_id  # Usar el estado "Activo"
    ).first()

    if not user_role_farm:
        return create_response("error", "No tienes acceso a esta finca", status_code=403)

    # Verificar si el rol sugerido para la invitación es válido
    suggested_role = db.query(Role).filter(Role.name == invitation_data.suggested_role).first()
    if not suggested_role:
        return create_response("error", "El rol sugerido no es válido", status_code=400)

    # Verificar si el rol del usuario (invitador) tiene el permiso adecuado para invitar al rol sugerido
    if suggested_role.name == "Administrador de finca":
        has_permission_to_invite = db.query(RolePermission).join(Permission).filter(
            RolePermission.role_id == user_role_farm.role_id,
            Permission.name == "add_administrador_farm"
        ).first()
        if not has_permission_to_invite:
            return create_response("error", "No tienes permiso para invitar a un Administrador de Finca", status_code=403)

    elif suggested_role.name == "Operador de campo":
        has_permission_to_invite = db.query(RolePermission).join(Permission).filter(
            RolePermission.role_id == user_role_farm.role_id,
            Permission.name == "add_operador_farm"
        ).first()
        if not has_permission_to_invite:
            return create_response("error", "No tienes permiso para invitar a un Operador de Campo", status_code=403)

    else:
        return create_response("error", f"No puedes invitar a colaboradores de rol {suggested_role.name} ", status_code=403)

    # Verificar si el usuario ya está registrado
    existing_user = db.query(User).filter(User.email == invitation_data.email).first()
    if not existing_user:
        return create_response("error", "El usuario no está registrado", status_code=404)

    # Verificar si el usuario ya pertenece a la finca
    active_status = get_status(db, "Activo", "user_role_farm")
    if not active_status:
        return create_response("error", "El estado 'Activo' no fue encontrado para 'user_role_farm'", status_code=400)

    existing_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == existing_user.user_id,
        UserRoleFarm.farm_id == invitation_data.farm_id,
        UserRoleFarm.status_id == active_status.status_id  # Verificar que esté en estado 'Activo'
    ).first()

    if existing_role_farm:
        return create_response("error", "El usuario ya está asociado a la finca con un estado activo", status_code=400)

    # Verificar si el usuario ya tiene una invitación pendiente
    pending_status = get_status(db, "Pendiente", "Invitation")
    if not pending_status:
        return create_response("error", "El estado 'Pendiente' no fue encontrado para 'Invitation'", status_code=400)

    existing_invitation = db.query(Invitation).filter(
        Invitation.email == invitation_data.email,
        Invitation.farm_id == invitation_data.farm_id,
        Invitation.status_id == pending_status.status_id  # Usar el estado "Pendiente"
    ).first()

    if existing_invitation:
        return create_response("error", "El usuario ya tiene una invitación pendiente para esta finca", status_code=400)

    # Crear la invitación y la notificación solo después de todas las verificaciones
    try:
        # Crear la nueva invitación
        new_invitation = Invitation(
            email=invitation_data.email,
            suggested_role=invitation_data.suggested_role,
            farm_id=invitation_data.farm_id,
            inviter_user_id=user.user_id,  # Agregar el ID del usuario que está creando la invitación
            date=datetime.now(bogota_tz)  # Agregar la fecha actual
        )
        db.add(new_invitation)
        db.commit()
        db.refresh(new_invitation)

        # Crear la notificación asociada con notification_type_id
        pending_status = get_status(db, "Pendiente", "Notification")
        if not pending_status:
            return create_response("error", "El estado 'Pendiente' no fue encontrado para 'Notification'", status_code=400)

        invitation_notification_type = db.query(NotificationType).filter(NotificationType.name == "Invitation").first()
        if not invitation_notification_type:
            return create_response("error", "No se encontró el tipo de notificación 'Invitation'", status_code=400)

        new_notification = Notification(
            message=f"Has sido invitado como {invitation_data.suggested_role} a la finca {farm.name}",
            date=datetime.now(bogota_tz),
            user_id=existing_user.user_id,
            notification_type_id=invitation_notification_type.notification_type_id,  # Usar notification_type_id
            invitation_id=new_invitation.invitation_id,
            farm_id=invitation_data.farm_id,
            status_id=pending_status.status_id  # Estado "Pendiente" del tipo "Notification"
        )
        db.add(new_notification)
        db.commit()

    
        # Enviar notificación FCM al usuario
        if fcm_token := existing_user.fcm_token:
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


@router.post("/respond-invitation/{invitation_id}")
def respond_invitation(invitation_id: int, action: str, session_token: str, db: Session = Depends(get_db_session)):
    """
    Responde a una invitación con las acciones 'accept' o 'reject'.
    
    Parámetros:
    - invitation_id: ID de la invitación a procesar.
    - action: La acción a realizar ('accept' o 'reject').
    - session_token: Token de sesión del usuario autenticado.
    - db: Sesión de la base de datos (inyectada mediante Depends).
    
    Retorna:
    - Un mensaje de éxito o error en función de la acción realizada.
    """
    # Validar el session_token y obtener el usuario autenticado
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    # Buscar la invitación
    invitation = db.query(Invitation).filter(Invitation.invitation_id == invitation_id).first()
    if not invitation:
        return create_response("error", "Invitación no encontrada", status_code=404)
    
    # Verificar si el usuario es el invitado
    if user.email != invitation.email:
        return create_response("error", "No tienes permiso para responder esta invitación", status_code=403)

    # Usar get_status para obtener los estados "Aceptada" y "Rechazada" del tipo "Invitation"
    accepted_status = get_status(db, "Aceptada", "Invitation")
    rejected_status = get_status(db, "Rechazada", "Invitation")
    responded_status = get_status(db, "Respondida", "Notification")  # Obtener el estado "Respondida"

    if not accepted_status or not rejected_status or not responded_status:
        return create_response("error", "Estados necesarios no encontrados en la base de datos", status_code=500)

    # Verificar si la invitación ya fue aceptada o rechazada
    if invitation.status_id in [accepted_status.status_id, rejected_status.status_id]:
        return create_response("error", "La invitación ya ha sido procesada (aceptada o rechazada)", status_code=400)

    # Actualizar las notificaciones relacionadas con la invitación
    notification = db.query(Notification).filter(Notification.invitation_id == invitation_id).first()
    if notification:
        notification.status_id = responded_status.status_id  # Actualizar el estado a "Respondida"
        db.commit()

    # Verificar si la acción es "accept" o "reject"
    if action.lower() == "accept":
        # Cambiar el estado de la invitación a "Aceptada"
        invitation.status_id = accepted_status.status_id
        db.commit()

        # Usar la función get_status para obtener el estado "Activo" del tipo "user_role_farm"
        active_status = get_status(db, "Activo", "user_role_farm")
        if not active_status:
            return create_response("error", "El estado 'Activo' no fue encontrado para 'user_role_farm'", status_code=400)

        # Obtener el rol sugerido
        suggested_role = db.query(Role).filter(Role.name == invitation.suggested_role).first()
        if not suggested_role:
            return create_response("error", "El rol sugerido no es válido", status_code=400)

        # Agregar al usuario a la finca en la tabla UserRoleFarm con el rol de la invitación
        new_user_role_farm = UserRoleFarm(
            user_id=user.user_id,
            farm_id=invitation.farm_id,
            role_id=suggested_role.role_id,  # Asignar el rol sugerido
            status_id=active_status.status_id  # Estado "Activo" del tipo "user_role_farm"
        )
        db.add(new_user_role_farm)
        db.commit()

        # Crear la notificación para el usuario que hizo la invitación (inviter_user_id)
        inviter = db.query(User).filter(User.user_id == invitation.inviter_user_id).first()
        if inviter:
            accepted_notification_type = db.query(NotificationType).filter(NotificationType.name == "Invitation_accepted").first()
            if not accepted_notification_type:
                return create_response("error", "No se encontró el tipo de notificación 'Invitation_accepted'", status_code=400)

            notification_message = f"El usuario {user.name} ha aceptado tu invitación a la finca {invitation.farm.name}."
            new_notification = Notification(
                message=notification_message,
                date=datetime.now(bogota_tz),
                user_id=invitation.inviter_user_id,
                notification_type_id=accepted_notification_type.notification_type_id,  # Usar notification_type_id
                invitation_id=invitation.invitation_id,
                farm_id=invitation.farm_id,
                status_id=responded_status.status_id  # Estado "Respondida" del tipo "Notification"
            )
            db.add(new_notification)
            db.commit()

            # Enviar notificación FCM al invitador (si tiene token)
            if inviter.fcm_token:
                send_fcm_notification(inviter.fcm_token, "Invitación aceptada", notification_message)

        return create_response("success", "Has aceptado la invitación exitosamente", status_code=200)

    elif action.lower() == "reject":
        # Cambiar el estado de la invitación a "Rechazada"
        invitation.status_id = rejected_status.status_id
        db.commit()

        # Crear la notificación para el usuario que hizo la invitación (inviter_user_id)
        inviter = db.query(User).filter(User.user_id == invitation.inviter_user_id).first()
        if inviter:
            rejected_notification_type = db.query(NotificationType).filter(NotificationType.name == "invitation_rejected").first()
            if not rejected_notification_type:
                return create_response("error", "No se encontró el tipo de notificación 'invitation_rejected'", status_code=400)

            notification_message = f"El usuario {user.name} ha rechazado tu invitación a la finca {invitation.farm.name}."
            new_notification = Notification(
                message=notification_message,
                date=datetime.now(bogota_tz),
                user_id=invitation.inviter_user_id,
                notification_type_id=rejected_notification_type.notification_type_id,  # Usar notification_type_id
                invitation_id=invitation.invitation_id,
                farm_id=invitation.farm_id,
                status_id=responded_status.status_id  # Estado "Respondida" del tipo "Notification"
            )
            db.add(new_notification)
            db.commit()

            # Enviar notificación FCM al invitador (si tiene token)
            if inviter.fcm_token:
                send_fcm_notification(inviter.fcm_token, "Invitación rechazada", notification_message)

        return create_response("success", "Has rechazado la invitación exitosamente", status_code=200)

    else:
        return create_response("error", "Acción inválida. Debes usar 'accept' o 'reject'", status_code=400)