from sqlalchemy.orm import Session  # Asegúrate de importar Session
from models.models import Status, StatusType  # Importar Status y StatusType

def get_status(db: Session, status_name: str, status_type_name: str) -> Status:
    # Obtener el status_type correspondiente al nombre dado
    status_type = db.query(StatusType).filter(StatusType.name == status_type_name).first()

    if not status_type:
        return None  # Devuelve None si no se encuentra el tipo de estatus

    # Obtener el estado basado en el nombre y el tipo de estatus
    status = db.query(Status).filter(
        Status.name == status_name,
        Status.status_type_id == status_type.status_type_id
    ).first()

    if not status:
        return None  # Devuelve None si no se encuentra el estado

    return status
