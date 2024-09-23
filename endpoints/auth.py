from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from models.models import User, Status, StatusType  # Importar todos los modelos desde models.py


from utils.security import hash_password, generate_verification_token , verify_password
from utils.email import send_email
from utils.response import session_token_invalid_response
from utils.response import create_response
from dataBase import get_db_session
import secrets
import datetime
import logging
from typing import Any, Dict

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    passwordConfirmation: str
    
class VerifyTokenRequest(BaseModel):
    token: str

class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordReset(BaseModel):
    token: str
    new_password: str
    confirm_password: str  

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    fcm_token: str  # Campo agregado para recibir el token FCM

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class LogoutRequest(BaseModel):
    session_token: str

class UpdateProfile(BaseModel):
    new_name: str
   

reset_tokens = {}


# Función auxiliar para verificar tokens
def verify_user_token(token: str, db: Session) -> User:
    user = db.query(User).filter(User.verification_token == token).first()
    if not user or (user.token_expiration and user.token_expiration < datetime.datetime.utcnow()):
        return None
    return user


# Función auxiliar para verificar tokens de sesión
def verify_session_token(session_token: str, db: Session) -> User:
    user = db.query(User).filter(User.session_token == session_token).first()
    if not user:
        return None
    return user

import re

# Función auxiliar para validar la contraseña
def validate_password_strength(password: str) -> bool:
    # La contraseña debe tener al menos:
    # - 8 caracteres
    # - 1 letra mayúscula
    # - 1 letra minúscula
    # - 1 número
    # - 1 carácter especial
    if (len(password) >= 8 and
        re.search(r'[A-Z]', password) and
        re.search(r'[a-z]', password) and
        re.search(r'[0-9]', password) and
        re.search(r'[\W_]', password)):
        return True
    return False

# Modificación del endpoint de registro
@router.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db_session)):
    # Validación del nombre (no puede estar vacío)
    if not user.name.strip():
        return create_response("error", "El nombre no puede estar vacío")
    
    # Validación del correo (ya está validado con EmailStr en Pydantic)
    
    # Validación de la contraseña
    if user.password != user.passwordConfirmation:
        return create_response("error", "Las contraseñas no coinciden")
    
    if not validate_password_strength(user.password):
        return create_response("error", "La contraseña debe tener al menos 8 caracteres, incluir una letra mayúscula, una letra minúscula, un número y un carácter especial")
    
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        return create_response("error", "El correo ya está registrado")

    try:
        password_hash = hash_password(user.password)
        verification_token = generate_verification_token(4)

        # Consulta para obtener el status_type_id del tipo "User"
        status_type_record = db.query(StatusType).filter(StatusType.name == "User").first()

        if not status_type_record:
            raise HTTPException(status_code=400, detail="No se encontró el tipo de estado 'User'.")

        # Consulta para obtener el status_id de "No Verificado"
        status_record = db.query(Status).filter(
            Status.name == "No Verificado",
            Status.status_type_id == status_type_record.status_type_id
        ).first()

        if not status_record:
            raise HTTPException(status_code=400, detail="No se encontró el estado 'No Verificado' para tipo 'User'.")

        # Crear el nuevo usuario con estado "No Verificado"
        new_user = User(
            name=user.name,
            email=user.email,
            password_hash=password_hash,
            verification_token=verification_token,
            status_id=status_record.status_id  # Asignamos el status_id dinámicamente
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        send_email(user.email, verification_token, 'verification')

        return create_response("success", "Hemos enviado un correo electrónico para verificar tu cuenta")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar usuario o enviar correo: {str(e)}")



@router.post("/verify")
def verify_email(request: VerifyTokenRequest, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.verification_token == request.token).first()
    
    if not user:
        return create_response("error", "Token inválido")
    
    try:
        # Consulta para obtener el status_type_id del tipo "User"
        status_type_record = db.query(StatusType).filter(StatusType.name == "User").first()
        if not status_type_record:
            raise HTTPException(status_code=400, detail="No se encontró el tipo de estado 'User'.")
        
        # Obtener el estado "Verificado"
        status_verified = db.query(Status).filter(
            Status.name == "Verificado",
            Status.status_type_id == status_type_record.status_type_id
        ).first()
        
        if not status_verified:
            raise HTTPException(status_code=400, detail="No se encontró el estado 'Verificado'.")

        # Actualizar el usuario: marcar como verificado y cambiar el status_id
        user.verification_token = None
        user.status_id = status_verified.status_id
        
        # Guardar los cambios en la base de datos
        db.commit()
        
        return create_response("success", "Correo electrónico verificado exitosamente")
    
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al verificar el correo: {str(e)}")


# Declaración global del diccionario
reset_tokens = {}
@router.post("/forgot-password")
def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db_session)):
    global reset_tokens  # Aseguramos que estamos usando la variable global

    logger.info("Iniciando el proceso de restablecimiento de contraseña para el correo: %s", request.email)
    
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        logger.warning("Correo no encontrado: %s", request.email)
        return create_response("error", "Correo no encontrado")

    try:
        # Genera un token único para restablecer la contraseña
        reset_token = generate_verification_token(4)
        logger.info("Token de restablecimiento generado: %s", reset_token)

        # Configura el tiempo de expiración para 15 minutos en el futuro
        expiration_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
        logger.info("Tiempo de expiración del token establecido para: %s", expiration_time)

        # Almacenar el token en la base de datos
        user.verification_token = reset_token
        logger.info("Token de restablecimiento guardado en la base de datos para el usuario: %s", user.email)

        # Guardar el token y el tiempo de expiración en el diccionario global, sobrescribiendo el token existente si lo hay
        reset_tokens[reset_token] = {
            "expires_at": expiration_time,
            "email": request.email  # Asociamos el token con el correo
        }
        logger.info("Token de restablecimiento almacenado globalmente para el correo: %s", request.email)

        print (reset_token)
        # Guardar cambios en la base de datos
        db.commit()
        logger.info("Cambios guardados en la base de datos para el usuario: %s", user.email)

        # Envía un correo electrónico con el token de restablecimiento
        send_email(request.email, reset_token, 'reset')
        logger.info("Correo electrónico de restablecimiento enviado a: %s", request.email)

        return create_response("success", "Correo electrónico de restablecimiento de contraseña enviado")

    except Exception as e:
        logger.error("Error durante el proceso de restablecimiento de contraseña: %s", str(e))
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error sending password reset email: {str(e)}")


@router.post("/verify-token")
def verify_token(request: VerifyTokenRequest, db: Session = Depends(get_db_session)):
    global reset_tokens

    logger.info("Iniciando la verificación del token: %s", request.token)
    logger.debug("Estado actual de reset_tokens: %s", reset_tokens)

    token_info = reset_tokens.get(request.token)

    if token_info:
        logger.info("Token encontrado: %s", request.token)

        current_time = datetime.datetime.utcnow()
        expires_at = token_info['expires_at']
        logger.debug("Hora actual: %s, Expira a: %s", current_time, expires_at)

        if current_time > expires_at:
            logger.info("El token ha expirado: %s", request.token)
            return create_response("error", "Token ha expirado")

        logger.info("Token válido, puede proceder a restablecer la contraseña.")
        return create_response("success", "Token válido. Puede proceder a restablecer la contraseña.")

    logger.warning("Token inválido o expirado: %s", request.token)
    return create_response("error", "Token inválido o expirado")

@router.post("/reset-password")
def reset_password(reset: PasswordReset, db: Session = Depends(get_db_session)):
    global reset_tokens  # Aseguramos que estamos usando la variable global

    logger.info("Iniciando el proceso de restablecimiento de contraseña para el token: %s", reset.token)

    # Verificar que las contraseñas coincidan
    if reset.new_password != reset.confirm_password:
        logger.warning("Las contraseñas no coinciden para el token: %s", reset.token)
        return create_response("error", "Las contraseñas no coinciden")

    # Validar que la nueva contraseña cumpla con los requisitos de seguridad
    if not validate_password_strength(reset.new_password):
        return create_response("error", "La nueva contraseña debe tener al menos 8 caracteres, incluir una letra mayúscula, una letra minúscula, un número y un carácter especial")

    # Verificar el token en el diccionario en memoria
    token_info = reset_tokens.get(reset.token)

    if token_info:
        logger.info("Token encontrado en memoria: %s", reset.token)

        # Verificar si el token ha expirado
        current_time = datetime.datetime.utcnow()
        expires_at = token_info['expires_at']
        logger.debug("Hora actual: %s, Expira a: %s", current_time, expires_at)

        if current_time > expires_at:
            logger.info("El token ha expirado: %s", reset.token)
            del reset_tokens[reset.token]  # Eliminar token expirado
            return create_response("error", "El token ha expirado")

        # Obtener el usuario de la base de datos usando el token
        user = db.query(User).filter(User.verification_token == reset.token).first()
        if not user:
            logger.warning("Usuario no encontrado para el token: %s", reset.token)
            return create_response("error", "Usuario no encontrado")

        try:
            # Actualizar la contraseña del usuario
            new_password_hash = hash_password(reset.new_password)
            logger.debug("Hash de la nueva contraseña generado: %s", new_password_hash)

            user.password_hash = new_password_hash
            logger.info("Contraseña actualizada para el usuario: %s", user.email)

            # Limpiar el token después de usarlo
            user.verification_token = None

            # Confirmar los cambios en la base de datos
            db.commit()
            logger.info("Cambios confirmados en la base de datos para el usuario: %s", user.email)

            # Eliminar el token del diccionario después de usarlo
            del reset_tokens[reset.token]
            logger.info("Token eliminado del diccionario global: %s", reset.token)

            return create_response("success", "Contraseña restablecida exitosamente")
        except Exception as e:
            logger.error("Error al restablecer la contraseña: %s", str(e))
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error al restablecer la contraseña: {str(e)}")
    else:
        logger.warning("Token inválido o expirado: %s", reset.token)
        return create_response("error", "Token inválido o expirado")


@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.email == request.email).first()

    if not user or not verify_password(request.password, user.password_hash):
        return create_response("error", "Credenciales incorrectas")

    # Verificar si el usuario está en estado "Verificado"
    status_verified = db.query(Status).filter(Status.name == "Verificado").first()
    if user.status_id != status_verified.status_id:
        # Usuario no verificado, generar un nuevo token de verificación
        new_verification_token = generate_verification_token(4)
        user.verification_token = new_verification_token

        try:
            # Guardar el nuevo token en la base de datos
            db.commit()
            # Enviar correo con el nuevo token de verificación
            send_email(user.email, new_verification_token, 'verification')

            return create_response("error", "Debes verificar tu correo antes de iniciar sesión")
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"Error al enviar el nuevo correo de verificación: {str(e)}")

    try:
        session_token = generate_verification_token(32)
        user.session_token = session_token
        user.fcm_token = request.fcm_token  # Guardar el token FCM del usuario
        db.commit()
        return create_response("success", "Inicio de sesión exitoso", {"session_token": session_token, "name": user.name})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error durante el inicio de sesión: {str(e)}")


# Cambiar contraseña
@router.put("/change-password")
def change_password(change: PasswordChange, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user or not verify_password(change.current_password, user.password_hash):
        return create_response("error", "Credenciales incorrectas")

    # Validar que la nueva contraseña cumpla con los requisitos de seguridad
    if not validate_password_strength(change.new_password):
        return create_response("error", "La nueva contraseña debe tener al menos 8 caracteres, incluir una letra mayúscula, una letra minúscula, un número y un carácter especial")

    try:
        new_password_hash = hash_password(change.new_password)
        user.password_hash = new_password_hash
        db.commit()
        return create_response("success", "Cambio de contraseña exitoso")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al cambiar la contraseña: {str(e)}")


# Cerrar sesión
# Cerrar sesión
@router.post("/logout")
def logout(request: LogoutRequest, db: Session = Depends(get_db_session)):
    user = verify_session_token(request.session_token, db)
    if not user:
        return session_token_invalid_response()
    try:
        user.session_token = None  # Borrar el session_token
        user.fcm_token = None  # Borrar el fcm_token también
        db.commit()
        return create_response("success", "Cierre de sesión exitoso")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error durante el cierre de sesión: {str(e)}")


# Eliminar cuenta
@router.delete("/delete-account")
def delete_account(session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    try:
        db.delete(user)
        db.commit()
        return create_response("success", "Cuenta eliminada exitosa")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting account: {str(e)}")

@router.post("/update-profile")
def update_profile(profile: UpdateProfile, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()
    
    # Validación de que el nuevo nombre no sea vacío
    if not profile.new_name.strip():
        return create_response("error", "El nombre no puede estar vacío")

    try:
        # Solo actualizamos el nombre del usuario
        user.name = profile.new_name
        db.commit()
        return create_response("success", "Perfil actualizado exitosamente")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar el perfil: {str(e)}")
