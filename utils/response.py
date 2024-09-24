
from fastapi.responses import JSONResponse
from typing import Any, Dict, Optional

def create_response(
    status: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    status_code: int = 200
) -> JSONResponse:
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
