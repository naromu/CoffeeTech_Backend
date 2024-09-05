from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from models.user import User
from utils.security import hash_password, generate_verification_token, generate_reset_token, verify_password
from utils.email import send_email
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

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class LogoutRequest(BaseModel):
    session_token: str

class UpdateProfile(BaseModel):
    new_name: str
    new_email: EmailStr

reset_tokens = {}

# Función auxiliar para crear una respuesta uniforme
def create_response(status: str, message: str, data: Dict[str, Any] = None):
    return {
        "status": status,
        "message": message,
        "data": data or {}
    }

# Función auxiliar para verificar tokens
def verify_user_token(token: str, db: Session) -> User:
    user = db.query(User).filter(User.verification_token == token).first()
    if not user or (user.token_expiration and user.token_expiration < datetime.datetime.utcnow()):
        return None
    return user


# Función auxiliar para verificar tokens de sesión
def verify_session_token(session_token: str, db: Session) -> User:
    user = db.query(User).filter(User.verification_token == session_token, User.is_verified == True).first()
    if not user:
        return None
    return user

# Endpoint de registro de usuario
@router.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db_session)):
    if user.password != user.passwordConfirmation:
        return create_response("error", "Las contraseñas no coinciden")

    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        return create_response("error", "El correo ya está registrado")

    try:
        password_hash = hash_password(user.password)
        verification_token = generate_verification_token()

        new_user = User(
            name=user.name,
            email=user.email,
            password_hash=password_hash,
            verification_token=verification_token
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        send_email(user.email, verification_token, 'verification')

        return create_response("success", "Hemos enviado un correo electrónico para verificar tu cuenta")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al registrar usuario o enviar correo: {str(e)}")

# Verificar email
@router.post("/verify")
def verify_email(request: VerifyTokenRequest, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.verification_token == request.token, User.is_verified == False).first()
    if not user:
        return create_response("error", "Token invalido o expirado")

    try:
        user.is_verified = True
        user.verification_token = None
        db.commit()
        return create_response("success", "Correo electrónico verificado exitosamente")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error verifying email: {str(e)}")

@router.post("/forgot-password")
def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db_session)):
    logger.info("Iniciando el proceso de restablecimiento de contraseña para el correo: %s", request.email)
    
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        logger.warning("Correo no encontrado: %s", request.email)
        return create_response("error", "Correo no encontrado")

    try:
        # Genera un token único para restablecer la contraseña
        reset_token = secrets.token_urlsafe(32)
        logger.info("Token de restablecimiento generado: %s", reset_token)

        # Configura el tiempo de expiración para 15 minutos en el futuro
        expiration_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
        logger.info("Tiempo de expiración del token establecido para: %s", expiration_time)

        # Almacena el token y el tiempo de expiración en el diccionario en memoria
        reset_tokens[request.email] = {
            "token": reset_token,
            "expires_at": expiration_time
        }
        logger.info("Token de restablecimiento almacenado en el diccionario para el correo: %s", request.email)

        # Envía un correo electrónico con el token de restablecimiento
        send_email(request.email, reset_token, 'reset')
        logger.info("Correo electrónico de restablecimiento enviado a: %s", request.email)

        return create_response("success", "Correo electrónico de restablecimiento de contraseña enviado")
    except Exception as e:
        logger.error("Error durante el envío del correo de restablecimiento: %s", str(e))
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error sending password reset email: {str(e)}")


@router.post("/verify-token")
def verify_token(request: VerifyTokenRequest, db: Session = Depends(get_db_session)):
    # Buscar el token en el diccionario en memoria
    for email, token_info in reset_tokens.items():
        if token_info['token'] == request.token:
            # Verificar si el token ha expirado
            if datetime.utcnow() > token_info['expires_at']:
                return create_response("error", "Token ha expirado")

            # Token válido, no eliminamos el token, solo confirmamos la validez
            return create_response("success", "Token válido. Puede proceder a restablecer la contraseña.")

    return create_response("error", "Token inválido o expirado")

from fastapi import HTTPException

class PasswordReset(BaseModel):
    token: str
    new_password: str
    confirm_password: str  # Agregamos la confirmación de contraseña

@router.post("/reset-password")
def reset_password(reset: PasswordReset, db: Session = Depends(get_db_session)):
    # Verificar que las contraseñas coincidan
    if reset.new_password != reset.confirm_password:
        return create_response("error", "Las contraseñas no coinciden")

    # Verificar el token en el diccionario en memoria
    email_to_reset = None
    for email, token_info in reset_tokens.items():
        if token_info['token'] == reset.token:
            # Verificar si el token ha expirado
            if datetime.utcnow() > token_info['expires_at']:
                return create_response("error", "Token ha expirado")
            email_to_reset = email
            break

    if not email_to_reset:
        return create_response("error", "Token inválido o expirado")

    # Obtener el usuario de la base de datos
    user = db.query(User).filter(User.email == email_to_reset).first()
    if not user:
        return create_response("error", "Usuario no encontrado")

    try:
        # Actualizar la contraseña del usuario
        new_password_hash = hash_password(reset.new_password)
        user.password_hash = new_password_hash

        # Limpiar el token después de usarlo
        user.verification_token = None
        db.commit()

        # Eliminar el token del diccionario después de usarlo
        del reset_tokens[email_to_reset]

        return create_response("success", "Contraseña restablecida exitosamente")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error resetting password: {str(e)}")


# Inicio de sesión
@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.password_hash):
        return create_response("error", "Credenciales incorrectas")

    try:
        session_token = secrets.token_urlsafe(32)
        user.verification_token = session_token
        db.commit()
        return create_response("success", "Inicio de sesión exitoso", {"verification_token": session_token})
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error during login: {str(e)}")

# Cambiar contraseña
@router.put("/change-password")
def change_password(change: PasswordChange, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user or not verify_password(change.current_password, user.password_hash):
        return create_response("error", "Credenciales incorrectas")

    try:
        new_password_hash = hash_password(change.new_password)
        user.password_hash = new_password_hash
        db.commit()
        return create_response("success", "Cambio de contraseña exitoso")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error changing password: {str(e)}")

# Cerrar sesión
@router.post("/logout")
def logout(request: LogoutRequest, db: Session = Depends(get_db_session)):
    user = verify_session_token(request.session_token, db)
    if not user:
        return create_response("error", "Token de sesion invalido")

    try:
        user.verification_token = None
        db.commit()
        return create_response("success", "Cierre de sesión exitoso")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error during logout: {str(e)}")

# Eliminar cuenta
@router.delete("/delete-account")
def delete_account(session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        return create_response("error", "Token de sesion invalido")

    try:
        db.delete(user)
        db.commit()
        return create_response("success", "Cuenta eliminada exitosa")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting account: {str(e)}")

# Actualizar perfil
@router.post("/update-profile")
def update_profile(profile: UpdateProfile, session_token: str, db: Session = Depends(get_db_session)):
    user = verify_session_token(session_token, db)
    if not user:
        return create_response("error", "Token de sesion invalido")

    try:
        user.name = profile.new_name
        user.email = profile.new_email
        db.commit()
        return create_response("success", "Perfil actualizado exitosamente")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating profile: {str(e)}")
