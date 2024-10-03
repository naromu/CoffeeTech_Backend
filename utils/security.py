from passlib.context import CryptContext
import secrets
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from models.models import User
from dataBase import get_db_session
from fastapi.security import OAuth2PasswordBearer




# Cambia el esquema a "argon2"
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    """
    Hashea una contraseña utilizando el esquema configurado en CryptContext.

    Args:
        password (str): La contraseña en texto plano a hashear.

    Returns:
        str: La contraseña hasheada.
    """
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica una contraseña en texto plano contra una contraseña hasheada.

    Args:
        plain_password (str): La contraseña en texto plano.
        hashed_password (str): La contraseña hasheada a comparar.

    Returns:
        bool: Verdadero si las contraseñas coinciden, falso en caso contrario.
    """
    return pwd_context.verify(plain_password, hashed_password)

import random
import string

def generate_verification_token(length: int=3) -> str:
    """
    Genera un token de verificación aleatorio.

    Args:
        length (int): La longitud del token. Por defecto es 3.

    Returns:
        str: Un token de verificación aleatorio compuesto por letras y dígitos.
    """
    characters = string.ascii_letters + string.digits  # Letras mayúsculas, minúsculas y dígitos
    return ''.join(random.choices(characters, k=length))



oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(db: Session = Depends(get_db_session), token: str = Depends(oauth2_scheme)):
    """
    Obtiene el usuario actual basado en el token de verificación.

    Args:
        db (Session, optional): Sesión de base de datos. Se obtiene automáticamente.
        token (str): El token de verificación recibido.

    Returns:
        User: El objeto usuario correspondiente al token.

    Raises:
        HTTPException: Si el token es inválido o el usuario no está verificado.
    """
    user = db.query(User).filter(User.verification_token == token).first()
    if not user or not user.is_verified:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user

# Función auxiliar para verificar tokens de sesión
def verify_session_token(session_token: str, db: Session) -> User:
    """
    Verifica si un token de sesión es válido y devuelve el usuario correspondiente.

    Args:
        session_token (str): El token de sesión a verificar.
        db (Session): La sesión de base de datos.

    Returns:
        User: El objeto usuario correspondiente al token de sesión, o None si no se encuentra.
    """
    user = db.query(User).filter(User.session_token == session_token).first()
    if not user:
        return None
    return user
