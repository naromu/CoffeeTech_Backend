from typing import Dict, Any

def session_token_invalid_response():
    return create_response("error", "Credenciales expiradas, cerrando sesión.")


def create_response(status: str, message: str, data: Dict[str, Any] = None):
    return {
        "status": status,
        "message": message,
        "data": data or {}
    }
