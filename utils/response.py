
from fastapi.responses import JSONResponse

from typing import Any, Dict, Optional
from pydantic import BaseModel
from decimal import Decimal

def create_response(
    status: str,
    message: str,
    data: Optional[Any] = None,  # Permitir cualquier tipo de datos
    status_code: int = 200
) -> JSONResponse:
    """
    Crea una respuesta JSON estructurada para ser devuelta por la API.

    Args:
        status (str): Estado de la respuesta (ej. "success" o "error").
        message (str): Mensaje que describe el estado de la respuesta.
        data (Optional[Any], optional): Datos adicionales a incluir en la respuesta. Puede ser cualquier tipo. Por defecto es None.
        status_code (int, optional): Código de estado HTTP a devolver. Por defecto es 200.

    Returns:
        JSONResponse: Respuesta en formato JSON que incluye el estado, mensaje y datos.
    """
    # Si data es un diccionario, procesar los valores
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, BaseModel):
                data[key] = value.dict()
            elif isinstance(value, Decimal):  # Manejo de objetos Decimal
                data[key] = float(value)
            elif isinstance(value, list):
                data[key] = [item.dict() if isinstance(item, BaseModel) else item for item in value]
    # Si data es una lista, procesarla como corresponde
    elif isinstance(data, list):
        data = [item.dict() if isinstance(item, BaseModel) else float(item) if isinstance(item, Decimal) else item for item in data]

    # Retornar la respuesta en formato JSON
    return JSONResponse(
        status_code=status_code,
        content={
            "status": status,
            "message": message,
            "data": data or {}
        }
    )


def session_token_invalid_response() -> JSONResponse:
    """
    Crea una respuesta JSON específica para cuando el token de sesión es inválido.

    Returns:
        JSONResponse: Respuesta en formato JSON que indica que las credenciales han expirado.
    """
    return create_response(
        status="error",
        message="Credenciales expiradas, cerrando sesión.",
        data={},
        status_code=401
    )