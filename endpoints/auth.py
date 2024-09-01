from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from models.user import User
from utils.security import hash_password, generate_verification_token, generate_reset_token, verify_password
from utils.email import send_verification_email, send_reset_email
from dataBase import get_db_session
import secrets
import datetime

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

@router.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db_session)):
    if user.password != user.passwordConfirmation:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email is already registered")

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

    send_verification_email(user.email, verification_token)

    return {"message": "Hemos enviado un correo electrónico para verificar tu cuenta"}

@router.post("/verify")
def verify_email(request: VerifyTokenRequest, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.verification_token == request.token, User.is_verified == False).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired token")

    user.is_verified = True
    user.verification_token = None
    db.commit()

    return {"message": "Correo electrónico verificado exitosamente"}

@router.post("/forgot-password")
def forgot_password(request: PasswordResetRequest):
    reset_token = secrets.token_urlsafe(32)
    expiration_time = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)

    reset_tokens[request.email] = {
        "token": reset_token,
        "expires_at": expiration_time
    }

    send_reset_email(request.email, reset_token)

    return {"message": "Password reset email sent"}

@router.post("/reset-password")
def reset_password(reset: PasswordReset):
    for email, token_data in reset_tokens.items():
        if token_data["token"] == reset.token:
            if datetime.datetime.utcnow() > token_data["expires_at"]:
                raise HTTPException(status_code=400, detail="Token has expired")

            # Aquí se actualizaría la contraseña del usuario
            del reset_tokens[email]
            return {"message": "Password successfully reset"}

    raise HTTPException(status_code=400, detail="Invalid token")

@router.post("/login")
def login(request: LoginRequest, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    session_token = secrets.token_urlsafe(32)
    user.verification_token = session_token
    db.commit()

    return {"message": "Login successful", "verification_token": session_token}

@router.put("/change-password")
def change_password(change: PasswordChange, session_token: str, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.verification_token == session_token, User.is_verified == True).first()
    if not user or not verify_password(change.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    new_password_hash = hash_password(change.new_password)
    user.password_hash = new_password_hash
    db.commit()

    return {"message": "Cambio de contraseña exitoso"}

@router.post("/logout")
def logout(request: LogoutRequest, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.verification_token == request.session_token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid session token")

    user.verification_token = None
    db.commit()

    return {"message": "Logout successful"}

@router.delete("/delete-account")
def delete_account(session_token: str, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.verification_token == session_token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid session token")

    db.delete(user)
    db.commit()

    return {"message": "Account deleted successfully"}

@router.post("/update-profile")
def update_profile(profile: UpdateProfile, session_token: str, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(User.verification_token == session_token).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid session token")

    user.name = profile.new_name
    user.email = profile.new_email
    db.commit()

    return {"message": "Profile updated successfully"}
