from passlib.context import CryptContext
import secrets

from passlib.context import CryptContext

# Cambia el esquema a "argon2"
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)



def generate_verification_token() -> str:
    return secrets.token_urlsafe(16)
