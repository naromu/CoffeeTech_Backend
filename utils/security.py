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
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)



def generate_verification_token(long) -> str:
    return secrets.token_urlsafe(long)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def get_current_user(db: Session = Depends(get_db_session), token: str = Depends(oauth2_scheme)):
    user = db.query(User).filter(User.verification_token == token).first()
    if not user or not user.is_verified:
        raise HTTPException(status_code=401, detail="Invalid or missing token")
    return user