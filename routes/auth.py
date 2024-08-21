from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from models.user import User
from utils.security import hash_password, generate_verification_token
from utils.email import send_verification_email
from database import get_db_connection

router = APIRouter()

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    passwordConfirmation: str


@router.post("/register")
def register_user(user: UserCreate):
    # Validar que las contraseñas coincidan
    if user.password != user.passwordConfirmation:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    # Conectarse a la base de datos
    conn = get_db_connection()

    # Verificar si el email ya está registrado
    with conn.cursor() as cursor:
        cursor.execute('SELECT user_id FROM "user" WHERE email = %s', (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email is already registered")

    # Hash de la contraseña
    password_hash = hash_password(user.password)

    # Generar un token de verificación
    verification_token = generate_verification_token()

    # Crear un nuevo usuario
    new_user = User(name=user.name, email=user.email, password_hash=password_hash, verification_token=verification_token)

    try:
        user_id = new_user.save(conn)

        # Enviar email de verificación
        send_verification_email(user.email, verification_token)

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail="User registration failed. " + str(e))
    finally:
        conn.close()

    return {"message": "Hemos enviado un correo electrónico para verificar tu cuenta"}

@router.get("/verify")
def verify_email(token: str):
    conn = get_db_connection()
    
    with conn.cursor() as cursor:
        cursor.execute('SELECT user_id FROM "user" WHERE verification_token = %s AND is_verified = FALSE', (token,))
        result = cursor.fetchone()
        
        if not result:
            raise HTTPException(status_code=400, detail="Invalid or expired token")

        user_id = result[0]
        
        # Marcar el correo como verificado
        cursor.execute('UPDATE "user" SET is_verified = TRUE WHERE user_id = %s', (user_id,))
        conn.commit()

    return {"message": "Correo electrónico verificado exitosamente"}
