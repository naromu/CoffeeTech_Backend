

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
    return create_response(
        status="error",
        message="Credenciales expiradas, cerrando sesión.",
        data={},
        status_code=401
    )
