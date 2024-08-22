from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from models.user import User
from utils.security import hash_password, generate_verification_token, generate_reset_token, verify_password
from utils.email import send_verification_email, send_reset_email
from database import get_db_connection
import secrets

router = APIRouter()

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    passwordConfirmation: str
class VerifyTokenRequest(BaseModel):
    token: str


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

@router.post("/verify")
def verify_email(request: VerifyTokenRequest):
    conn = get_db_connection()
    
    try:
        with conn.cursor() as cursor:
            # Verificar si el token de verificación es válido y si el usuario no está verificado aún
            cursor.execute("""
                SELECT user_id FROM "user" 
                WHERE verification_token = %s AND is_verified = FALSE
            """, (request.token,))
            result = cursor.fetchone()
            
            if not result:
                raise HTTPException(status_code=400, detail="Invalid or expired token")

            user_id = result[0]

            # Marcar el correo como verificado y vaciar el token de verificación
            cursor.execute("""
                UPDATE "user" 
                SET is_verified = TRUE, verification_token = NULL 
                WHERE user_id = %s
            """, (user_id,))
            conn.commit()
    
    except Exception as e:
        raise HTTPException(status_code=400, detail="Verification failed. " + str(e))
    
    finally:
        conn.close()

    return {"message": "Correo electrónico verificado exitosamente"}

#######recuperacion_contraseña
class PasswordResetRequest(BaseModel):
    email: EmailStr

@router.post("/forgot-password")
def forgot_password(request: PasswordResetRequest):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT email FROM "user" WHERE email = %s', (request.email,))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=400, detail="Email not found")

            reset_token = generate_reset_token()
            send_reset_email(request.email, reset_token)
            
            # Save the reset token in the database
            cursor.execute('UPDATE "user" SET verification_token = %s WHERE email = %s', (reset_token, request.email))
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Password reset failed. " + str(e))
    finally:
        conn.close()
    return {"message": "Password reset email sent"}

######restablecer contraseña
class PasswordReset(BaseModel):
    token: str
    new_password: str

@router.post("/reset-password")
def reset_password(reset: PasswordReset):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT email FROM "user" WHERE verification_token = %s', (reset.token,))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=400, detail="Invalid or expired token")

            email = result[0]
            password_hash = hash_password(reset.new_password)
            cursor.execute('UPDATE "user" SET password_hash = %s, verification_token = NULL WHERE email = %s', (password_hash, email))
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Password reset failed. " + str(e))
    finally:
        conn.close()
    return {"message": "contraseña restablecida exitosamente"}

####LOGIN························


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@router.post("/login")
def login(request: LoginRequest):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT password_hash FROM "user" WHERE email = %s', (request.email,))
            result = cursor.fetchone()
            if not result or not verify_password(request.password, result[0]):
                raise HTTPException(status_code=400, detail="Invalid credentials")

            # Token de sesión (simple ejemplo)
            session_token = secrets.token_urlsafe(32)
            cursor.execute('UPDATE "user" SET verification_token = %s WHERE email = %s', (session_token, request.email))
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Login failed. " + str(e))
    finally:
        conn.close()
    return {"message": "Login successful", "verification_token": session_token}

####cambio de contraseña
class PasswordChange(BaseModel):
    current_password: str
    new_password: str

@router.put("/change-password")
def change_password(change: PasswordChange, session_token: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT email FROM "user" WHERE verification_token = %s and is_verified=TRUE', (session_token,))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=400, detail="Invalid session token")

            email = result[0]
            cursor.execute('SELECT password_hash FROM "user" WHERE email = %s', (email,))
            result = cursor.fetchone()
            if not result or not verify_password(change.current_password, result[0]):
                raise HTTPException(status_code=400, detail="Current password is incorrect")

            new_password_hash = hash_password(change.new_password)
            cursor.execute('UPDATE "user" SET password_hash = %s WHERE email = %s', (new_password_hash, email))
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Password change failed. " + str(e))
    finally:
        conn.close()
    return {"message": "Cambio de contraseña exitoso"}

####cierre de sesion
class LogoutRequest(BaseModel):
    session_token: str

@router.post("/logout")
def logout(request: LogoutRequest):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('UPDATE "user" SET verification_token = NULL WHERE verification_token = %s', (request.session_token,))
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Logout failed. " + str(e))
    finally:
        conn.close()
    return {"message": "Logout successful"}


#####eliminacion de cuenta
@router.delete("/delete-account")
def delete_account(session_token: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT email FROM "user" WHERE verification_token = %s', (session_token,))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=400, detail="Invalid session token")

            email = result[0]
            cursor.execute('DELETE FROM "user" WHERE email = %s', (email,))
            conn.commit()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Account deletion failed. " + str(e))
    finally:
        conn.close()
    return {"message": "Account deleted successfully"}

#####modificar info personal

class UpdateProfile(BaseModel):
    new_name: str
    new_email: EmailStr

@router.post("/update-profile")
def update_profile(profile: UpdateProfile, session_token: str):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT email FROM "user" WHERE verification_token = %s', (session_token,))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=400, detail="Invalid session token")

            email = result[0]
            user = User(name=profile.new_name, email=profile.new_email, password_hash=None, verification_token=None)
            user.update(conn, new_name=profile.new_name, new_email=profile.new_email)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Profile update failed. " + str(e))
    finally:
        conn.close()
    return {"message": "Profile updated successfully"}

