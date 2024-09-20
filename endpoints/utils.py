from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.models import Role, UnitOfMeasure
from dataBase import get_db_session

router = APIRouter()

@router.get("/list-roles", summary="Obtener lista de roles", description="Obtiene una lista de todos los roles disponibles junto con sus permisos asociados.")
def list_roles(db: Session = Depends(get_db_session)):
    """
    Obtiene una lista de todos los roles disponibles junto con sus permisos asociados.

    Args:
        db (Session): Sesión de base de datos proporcionada por la dependencia.

    Returns:
        dict: Diccionario con el estado, mensaje y datos de los roles y sus permisos.
    """
    roles = db.query(Role).all()

    return {
        "status": "success",
        "message": "Roles obtenidos correctamente",
        "data": [
            {
                "role_id": role.role_id,
                "name": role.name,
                "permissions": [
                    {
                        "permission_id": perm.permission.permission_id,
                        "name": perm.permission.name,
                        "description": perm.permission.description
                    } for perm in role.permissions
                ]
            } for role in roles
        ]
    }

@router.get("/unit-measure", summary="Obtener lista de unidades de medida", description="Obtiene una lista de todas las unidades de medida disponibles junto con su tipo correspondiente.")
def list_unit_measures(db: Session = Depends(get_db_session)):
    """
    Obtiene una lista de todas las unidades de medida disponibles junto con su tipo correspondiente.

    Args:
        db (Session): Sesión de base de datos proporcionada por la dependencia.

    Returns:
        dict: Diccionario con el estado, mensaje y datos de las unidades de medida y sus tipos.
    """
    units_of_measure = db.query(UnitOfMeasure).all()

    return {
        "status": "success",
        "message": "Unidades de medida obtenidas correctamente",
        "data": [
            {
                "unit_of_measure_id": uom.unit_of_measure_id,
                "name": uom.name,
                "abbreviation": uom.abbreviation,
                "unit_of_measure_type": {
                    "unit_of_measure_type_id": uom.unit_of_measure_type.unit_of_measure_type_id,
                    "name": uom.unit_of_measure_type.name
                }
            } for uom in units_of_measure
        ]
    }