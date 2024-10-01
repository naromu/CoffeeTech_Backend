# tests.py

import pytest
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from main import app
from dataBase import engine, get_db_session
from models.models import User
import uuid
import asyncio

# Crear una sesión independiente para las pruebas
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def session_for_tests():
    """Inicia una transacción al inicio de cada prueba y la revierte al final."""
    connection = engine.connect()
    transaction = connection.begin()

    # Crear una sesión local conectada a esta transacción
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()

@pytest.fixture(scope="function")
def app_with_overrides(session_for_tests):
    # Función para sobrescribir la dependencia get_db_session
    def override_get_db_session():
        try:
            yield session_for_tests
        finally:
            pass

    app.dependency_overrides[get_db_session] = override_get_db_session
    yield app
    app.dependency_overrides.clear()
@pytest.mark.asyncio
async def test_register_and_verify_user(app_with_overrides, session_for_tests):
    transport = ASGITransport(app=app_with_overrides)

    # Generar un correo electrónico único usando uuid
    unique_email = f"test_{uuid.uuid4()}@example.com"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Registrar un nuevo usuario con correo único
        response = await client.post("/auth/register", json={
            "name": "Test User",
            "email": unique_email,
            "password": "TestPassword123!",
            "passwordConfirmation": "TestPassword123!"
        })

        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # 2. Obtener el verification_token de la base de datos
        user = session_for_tests.query(User).filter(User.email == unique_email).first()
        assert user is not None
        verification_token = user.verification_token
        assert verification_token is not None

        # 3. Verificar el correo electrónico usando el token
        response = await client.post("/auth/verify", json={"token": verification_token})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # 4. Iniciar sesión con el correo verificado
        response = await client.post("/auth/login", json={
            "email": unique_email,
            "password": "TestPassword123!",
            "fcm_token": "dummy_fcm_token"
        })

        assert response.status_code == 200
        assert "session_token" in response.json()["data"]

        # 5. Almacenar el session_token para usar en la verificación
        session_token = response.json()["data"]["session_token"]

        # 6. Verificar que el session_token se haya almacenado en la base de datos
        user = session_for_tests.query(User).filter(User.email == unique_email).first()
        assert user.session_token == session_token

        # 7. Cambiar la contraseña
        response = await client.put(f"/auth/change-password?session_token={session_token}", json={
            "current_password": "TestPassword123!",
            "new_password": "NewPassword123!"
        })
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # 8. Cerrar sesión
        response = await client.post("/auth/logout", json={"session_token": session_token})
        assert response.status_code == 200
        assert response.json()["status"] == "success"

