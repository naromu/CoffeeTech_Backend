# test_farm_endpoints.py

import pytest
from sqlalchemy.orm import sessionmaker
from httpx import AsyncClient, ASGITransport
from main import app
from dataBase import engine, get_db_session
from models.models import User, Farm, UnitOfMeasure, Role, Status, StatusType, Permission, RolePermission, UserRoleFarm
import uuid

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
async def test_farm_endpoints(app_with_overrides, session_for_tests):
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

        # Preparación: Asegurar que los datos necesarios existen en la base de datos

        # Asegurar que la unidad de medida existe
        unit_measure_name = "Hectárea"
        unit_of_measure = session_for_tests.query(UnitOfMeasure).filter_by(name=unit_measure_name).first()
        if not unit_of_measure:
            # Crear unidad de medida
            unit_of_measure = UnitOfMeasure(name=unit_measure_name, abbreviation="ha", unit_of_measure_type_id=1)  # Asegúrate de que unit_of_measure_type_id=1 existe
            session_for_tests.add(unit_of_measure)
            session_for_tests.commit()
            session_for_tests.refresh(unit_of_measure)

        # Asegurar que el rol "Propietario" existe
        role_name = "Propietario"
        role = session_for_tests.query(Role).filter_by(name=role_name).first()
        if not role:
            role = Role(name=role_name)
            session_for_tests.add(role)
            session_for_tests.commit()
            session_for_tests.refresh(role)

        # Asegurar que el status "Activo" para tipo "Farm" existe
        status_name = "Activo"
        status_type_name = "Farm"
        status_type = session_for_tests.query(StatusType).filter_by(name=status_type_name).first()
        if not status_type:
            status_type = StatusType(name=status_type_name)
            session_for_tests.add(status_type)
            session_for_tests.commit()
            session_for_tests.refresh(status_type)

        status = session_for_tests.query(Status).filter_by(name=status_name, status_type_id=status_type.status_type_id).first()
        if not status:
            status = Status(name=status_name, description="Activo", status_type_id=status_type.status_type_id)
            session_for_tests.add(status)
            session_for_tests.commit()
            session_for_tests.refresh(status)

        # Asegurar que el permiso "edit_farm" existe
        permission_edit_farm = session_for_tests.query(Permission).filter_by(name="edit_farm").first()
        if not permission_edit_farm:
            permission_edit_farm = Permission(name="edit_farm", description="Permiso para editar fincas")
            session_for_tests.add(permission_edit_farm)
            session_for_tests.commit()
            session_for_tests.refresh(permission_edit_farm)

        # Asignar el permiso al rol "Propietario"
        role_permission = session_for_tests.query(RolePermission).filter_by(role_id=role.role_id, permission_id=permission_edit_farm.permission_id).first()
        if not role_permission:
            role_permission = RolePermission(role_id=role.role_id, permission_id=permission_edit_farm.permission_id)
            session_for_tests.add(role_permission)
            session_for_tests.commit()
            
                    # Asegurar que el status "Activo" e "Inactiva" para tipo "user_role_farm" existe
        status_type_name_urf = "user_role_farm"
        status_type_urf = session_for_tests.query(StatusType).filter_by(name=status_type_name_urf).first()
        if not status_type_urf:
            status_type_urf = StatusType(name=status_type_name_urf)
            session_for_tests.add(status_type_urf)
            session_for_tests.commit()
            session_for_tests.refresh(status_type_urf)

        status_urf_active = session_for_tests.query(Status).filter_by(name="Activo", status_type_id=status_type_urf.status_type_id).first()
        if not status_urf_active:
            status_urf_active = Status(name="Activo", description="Activo", status_type_id=status_type_urf.status_type_id)
            session_for_tests.add(status_urf_active)
            session_for_tests.commit()
            session_for_tests.refresh(status_urf_active)

        status_urf_inactive = session_for_tests.query(Status).filter_by(name="Inactiva", status_type_id=status_type_urf.status_type_id).first()
        if not status_urf_inactive:
            status_urf_inactive = Status(name="Inactiva", description="Inactiva", status_type_id=status_type_urf.status_type_id)
            session_for_tests.add(status_urf_inactive)
            session_for_tests.commit()
            session_for_tests.refresh(status_urf_inactive)


        # 7. Crear una nueva finca
        farm_name = "Finca de Prueba"
        response = await client.post(f"/farm/create-farm?session_token={session_token}", json={
            "name": farm_name,
            "area": 100.0,
            "unitMeasure": unit_measure_name
        })
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        farm_id = response.json()["data"]["farm_id"]

        # 8. Listar las fincas del usuario
        response = await client.post(f"/farm/list-farm?session_token={session_token}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        farms = response.json()["data"]["farms"]
        assert len(farms) > 0
        assert any(farm["farm_id"] == farm_id for farm in farms)

        # 9. Obtener los detalles de la finca
        response = await client.get(f"/farm/get-farm/{farm_id}?session_token={session_token}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        farm_data = response.json()["data"]["farm"]
        assert farm_data["farm_id"] == farm_id
        assert farm_data["name"] == farm_name

        # 10. Actualizar la finca
        new_farm_name = "Finca Actualizada"
        response = await client.post(f"/farm/update-farm?session_token={session_token}", json={
            "farm_id": farm_id,
            "name": new_farm_name,
            "area": 150.0,
            "unitMeasure": unit_measure_name
        })
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # 11. Obtener los detalles de la finca actualizados
        response = await client.get(f"/farm/get-farm/{farm_id}?session_token={session_token}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        farm_data = response.json()["data"]["farm"]
        assert farm_data["farm_id"] == farm_id
        assert farm_data["name"] == new_farm_name

        # 12. Eliminar la finca
        response = await client.post(f"/farm/delete-farm/{farm_id}?session_token={session_token}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"

        # 13. Intentar obtener la finca eliminada
        response = await client.get(f"/farm/get-farm/{farm_id}?session_token={session_token}")
        assert response.status_code == 200  # Puede devolver 200 con mensaje de error
        assert response.json()["status"] == "error"
        assert response.json()["message"] == "Finca no encontrada o no pertenece al usuario"

        # ... código anterior ...

        # 14. Listar las fincas (la finca eliminada no debería aparecer)
        response = await client.post(f"/farm/list-farm?session_token={session_token}")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        farms = response.json()["data"]["farms"]
        assert not any(farm["farm_id"] == farm_id for farm in farms)

        # 15. Verificar que la relación en user_role_farm está inactiva
        user_role_farm = session_for_tests.query(UserRoleFarm).filter(
            UserRoleFarm.farm_id == farm_id,
            UserRoleFarm.user_id == user.user_id
        ).first()
        inactive_urf_status = session_for_tests.query(Status).join(StatusType).filter(
            Status.name == "Inactiva",
            StatusType.name == "user_role_farm"
        ).first()
        assert user_role_farm.status_id == inactive_urf_status.status_id

        # 16. Intentar obtener la finca eliminada (debería fallar)
        response = await client.get(f"/farm/get-farm/{farm_id}?session_token={session_token}")
        assert response.status_code == 200
        assert response.json()["status"] == "error"
        assert response.json()["message"] == "Finca no encontrada o no pertenece al usuario"
