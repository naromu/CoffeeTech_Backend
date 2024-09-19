from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.models import Role, UnitOfMeasure
from dataBase import get_db_session

router = APIRouter()

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.models import Role, RolePermission, Permission
from dataBase import get_db_session

router = APIRouter()

@router.get("/list-roles")
def list_roles(db: Session = Depends(get_db_session)):
    # Consulta los roles y carga los permisos asociados utilizando `joinedload`
    roles = db.query(Role).all()

    # Construir la respuesta con roles y sus permisos
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


@router.get("/unit-measure")
def list_unit_measures(db: Session = Depends(get_db_session)):
    units_of_measure = db.query(UnitOfMeasure).all()
    return {
        "status": "success",
        "message": "Unidades de medida obtenidas correctamente",
        "data": [{
            "unit_of_measure_id": uom.unit_of_measure_id,
            "name": uom.name,
            "abbreviation": uom.abbreviation,
            "unit_of_measure_type": {
                "unit_of_measure_type_id": uom.unit_of_measure_type.unit_of_measure_type_id,
                "name": uom.unit_of_measure_type.name
            }
        } for uom in units_of_measure]
    }
