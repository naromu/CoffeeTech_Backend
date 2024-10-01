import pytest
from sqlalchemy.orm import sessionmaker

import sys
import os

# Agrega la ruta raíz del proyecto al sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../')

from dataBase import engine, get_db_session

# Crear una sesión independiente para las pruebas
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function", autouse=True)
def session_for_tests():
    """Inicia una transacción al inicio de cada prueba y la revierte al final."""
    connection = engine.connect()
    transaction = connection.begin()  # Iniciar una transacción

    # Crear una sesión local conectada a esta transacción
    session = SessionLocal(bind=connection)
    try:
        yield session
    finally:
        transaction.rollback()  # Revertir los cambios al final de la prueba
        connection.close()
