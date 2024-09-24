from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel, EmailStr
from models.models import (
    Farm,
    UserRoleFarm,
    User,
    RolePermission,
    Permission,
    Status,
    StatusType,
    Role
)
from utils.security import verify_session_token
from dataBase import get_db_session
from utils.response import create_response, session_token_invalid_response
from sqlalchemy import func
import logging

# Configuración básica de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

# Modelo Pydantic actualizado para la respuesta de colaborador
class Collaborator(BaseModel):
    user_id: int          # Campo para el ID del usuario
    name: str
    email: EmailStr
    role: str             # Campo para el rol

    class Config:
        from_attributes = True

@router.get("/list-collaborators", response_model=Dict[str, Any])
def list_collaborators(
    farm_id: int,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Endpoint para listar los colaboradores de una finca específica.
    Requiere `farm_id` y `session_token` como parámetros.
    """

    # 1. Verificar el session_token y obtener el usuario autenticado
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    logger.info(f"Usuario autenticado: {user.name} (ID: {user.user_id})")

    # 2. Verificar que la finca exista
    farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
    if not farm:
        logger.error(f"Finca con ID {farm_id} no encontrada")
        return create_response(
            "error",
            "Finca no encontrada",
            status_code=404
        )

    logger.info(f"Finca encontrada: {farm.name} (ID: {farm.farm_id})")

    # 3. Obtener el estado 'Activo' para 'user_role_farm'
    active_status = db.query(Status).join(StatusType).filter(
        Status.name == "Activo",
        StatusType.name == "user_role_farm"
    ).first()

    if not active_status:
        logger.error("Estado 'Activo' no encontrado para 'user_role_farm'")
        return create_response(
            "error",
            "Estado 'Activo' no encontrado para 'user_role_farm'",
            status_code=400
        )

    logger.info(f"Estado 'Activo' encontrado: {active_status.name} (ID: {active_status.status_id})")

    # 4. Obtener el permiso 'read_collaborators' con insensibilidad a mayúsculas
    read_permission = db.query(Permission).filter(
        func.lower(Permission.name) == "read_collaborators"
    ).first()

    logger.info(f"Permiso 'read_collaborators' obtenido: {read_permission}")

    if not read_permission:
        logger.error("Permiso 'read_collaborators' no encontrado en la base de datos")
        return create_response(
            "error",
            "Permiso 'read_collaborators' no encontrado en la base de datos",
            status_code=500
        )

    # 5. Verificar si el usuario tiene el permiso 'read_collaborators' en la finca especificada
    has_permission = db.query(UserRoleFarm).join(RolePermission, UserRoleFarm.role_id == RolePermission.role_id).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm_id,
        UserRoleFarm.status_id == active_status.status_id,
        RolePermission.permission_id == read_permission.permission_id
    ).first()

    if not has_permission:
        logger.warning(f"Usuario {user.name} no tiene permiso 'read_collaborators' en la finca ID {farm_id}")
        return create_response(
            "error",
            "No tienes permiso para leer los colaboradores de esta finca",
            status_code=403
        )

    logger.info(f"Usuario {user.name} tiene permiso 'read_collaborators' en la finca ID {farm_id}")

    # 6. Obtener los colaboradores activos de la finca junto con su rol y user_id
    collaborators_query = db.query(User.user_id, User.name, User.email, Role.name.label("role")).join(
        UserRoleFarm, User.user_id == UserRoleFarm.user_id
    ).join(
        Role, UserRoleFarm.role_id == Role.role_id
    ).filter(
        UserRoleFarm.farm_id == farm_id,
        UserRoleFarm.status_id == active_status.status_id
    ).all()

    logger.info(f"Colaboradores encontrados: {collaborators_query}")

    # 7. Convertir los resultados a una lista de dicts
    collaborators_list = [
        {"user_id": user_id, "name": name, "email": email, "role": role}
        for user_id, name, email, role in collaborators_query
    ]

    # 8. Devolver la respuesta con la lista de colaboradores
    return create_response(
        "success",
        "Colaboradores obtenidos exitosamente",
        data=collaborators_list,
        status_code=200
    )


from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
from pydantic import BaseModel, EmailStr, Field
from models.models import (
    Farm,
    UserRoleFarm,
    User,
    RolePermission,
    Permission,
    Status,
    StatusType,
    Role
)
from utils.security import verify_session_token
from dataBase import get_db_session
from utils.response import create_response, session_token_invalid_response
from sqlalchemy import func
import logging

# Modelo Pydantic para la solicitud de edición de rol
class EditCollaboratorRoleRequest(BaseModel):
    collaborator_user_id: int = Field(..., alias="collaborator_user_id")
    new_role: str

    class Config:
        populate_by_name = True  # Reemplaza 'allow_population_by_field_name = True'
        from_attributes = True    # Reemplaza 'orm_mode = True'

    def validate_input(self):
        if self.new_role not in ["Administrador de finca", "Operador de campo"]:
            raise ValueError("El rol debe ser 'Administrador de finca' o 'Operador de campo'.")

@router.post("/edit-collaborator-role", response_model=Dict[str, Any])
def edit_collaborator_role(
    edit_request: EditCollaboratorRoleRequest,
    farm_id: int,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Endpoint para editar el rol de un colaborador en una finca específica.
    Requiere `farm_id`, `session_token` y un cuerpo de solicitud con `collaborator_user_id` y `new_role`.
    """

    # Validar la entrada
    try:
        edit_request.validate_input()
    except ValueError as e:
        logger.error(f"Validación de entrada fallida: {str(e)}")
        return create_response(
            "error",
            str(e),
            status_code=400
        )

    # 1. Verificar el session_token y obtener el usuario autenticado
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    logger.info(f"Usuario autenticado: {user.name} (ID: {user.user_id})")

    # 2. Verificar que la finca exista
    farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
    if not farm:
        logger.error(f"Finca con ID {farm_id} no encontrada")
        return create_response(
            "error",
            "Finca no encontrada",
            status_code=404
        )

    logger.info(f"Finca encontrada: {farm.name} (ID: {farm.farm_id})")

    # 3. Obtener el estado 'Activo' para 'user_role_farm'
    active_status = db.query(Status).join(StatusType).filter(
        Status.name == "Activo",
        StatusType.name == "user_role_farm"
    ).first()

    if not active_status:
        logger.error("Estado 'Activo' no encontrado para 'user_role_farm'")
        return create_response(
            "error",
            "Estado 'Activo' no encontrado para 'user_role_farm'",
            status_code=400
        )

    logger.info(f"Estado 'Activo' encontrado: {active_status.name} (ID: {active_status.status_id})")

    # 4. Obtener el rol actual del usuario que realiza la acción
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm_id,
        UserRoleFarm.status_id == active_status.status_id
    ).first()

    if not user_role_farm:
        logger.warning(f"Usuario {user.name} no está asociado a la finca ID {farm_id}")
        return create_response(
            "error",
            "No estás asociado a esta finca",
            status_code=403
        )

    # Obtener el rol del usuario que realiza la acción
    current_user_role = db.query(Role).filter(Role.role_id == user_role_farm.role_id).first()
    if not current_user_role:
        logger.error(f"Rol con ID {user_role_farm.role_id} no encontrado")
        return create_response(
            "error",
            "Rol del usuario no encontrado",
            status_code=500
        )

    logger.info(f"Rol del usuario: {current_user_role.name}")

    # 5. Obtener el colaborador a editar
    collaborator = db.query(User).filter(User.user_id == edit_request.collaborator_user_id).first()
    if not collaborator:
        logger.error(f"Colaborador con ID {edit_request.collaborator_user_id} no encontrado")
        return create_response(
            "error",
            "Colaborador no encontrado",
            status_code=404
        )

    logger.info(f"Colaborador a editar: {collaborator.name} (ID: {collaborator.user_id})")

    # 6. Verificar que el usuario no esté intentando cambiar su propio rol
    if user.user_id == collaborator.user_id:
        logger.warning(f"Usuario {user.name} intentó cambiar su propio rol")
        return create_response(
            "error",
            "No puedes cambiar tu propio rol",
            status_code=403
        )

    # 7. Obtener el estado 'Activo' para el colaborador
    collaborator_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == collaborator.user_id,
        UserRoleFarm.farm_id == farm_id,
        UserRoleFarm.status_id == active_status.status_id
    ).first()

    if not collaborator_role_farm:
        logger.error(f"Colaborador {collaborator.name} no está asociado a la finca ID {farm_id}")
        return create_response(
            "error",
            "El colaborador no está asociado a esta finca",
            status_code=404
        )

    # Obtener el rol actual del colaborador
    collaborator_current_role = db.query(Role).filter(Role.role_id == collaborator_role_farm.role_id).first()
    if not collaborator_current_role:
        logger.error(f"Rol con ID {collaborator_role_farm.role_id} no encontrado para el colaborador")
        return create_response(
            "error",
            "Rol actual del colaborador no encontrado",
            status_code=500
        )

    logger.info(f"Rol actual del colaborador: {collaborator_current_role.name}")

    # 8. Verificar si el colaborador ya tiene el rol deseado
    if collaborator_current_role.name == edit_request.new_role:
        logger.info(f"El colaborador {collaborator.name} ya tiene el rol '{edit_request.new_role}'")
        return create_response(
            "error",
            f"El colaborador ya tiene el rol '{edit_request.new_role}'",
            status_code=400
        )

    # 9. Verificar permisos necesarios para cambiar al nuevo rol
    permission_name = ""
    if edit_request.new_role == "Administrador de finca":
        permission_name = "edit_administrador_farm"
    elif edit_request.new_role == "Operador de campo":
        permission_name = "edit_operador_farm"

    if not permission_name:
        logger.error(f"Rol deseado '{edit_request.new_role}' no es válido")
        return create_response(
            "error",
            "Rol deseado no válido",
            status_code=400
        )

    # Obtener el permiso requerido
    required_permission = db.query(Permission).filter(
        func.lower(Permission.name) == permission_name.lower()
    ).first()

    if not required_permission:
        logger.error(f"Permiso '{permission_name}' no encontrado en la base de datos")
        return create_response(
            "error",
            f"Permiso '{permission_name}' no encontrado en la base de datos",
            status_code=500
        )

    logger.info(f"Permiso requerido para asignar '{edit_request.new_role}': {required_permission.name}")

    # Verificar si el usuario tiene el permiso necesario
    has_permission = db.query(RolePermission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        RolePermission.permission_id == required_permission.permission_id
    ).first()

    if not has_permission:
        logger.warning(f"Usuario {user.name} no tiene permiso '{permission_name}'")
        return create_response(
            "error",
            f"No tienes permiso para asignar el rol '{edit_request.new_role}'",
            status_code=403
        )

    logger.info(f"Usuario {user.name} tiene permiso '{permission_name}'")

    # 10. Verificar la jerarquía de roles
    # Definir la jerarquía
    hierarchy = {
        "Propietario": ["Administrador de finca", "Operador de campo"],
        "Administrador de finca": ["Operador de campo"],
        "Operador de campo": []
    }

    if current_user_role.name not in hierarchy:
        logger.error(f"Rol del usuario '{current_user_role.name}' no está definido en la jerarquía")
        return create_response(
            "error",
            "Rol del usuario no está definido en la jerarquía",
            status_code=500
        )

    allowed_roles_to_assign = hierarchy.get(current_user_role.name, [])

    if edit_request.new_role not in allowed_roles_to_assign:
        logger.warning(f"Rol '{edit_request.new_role}' no puede ser asignado por un usuario con rol '{current_user_role.name}'")
        return create_response(
            "error",
            f"No tienes permiso para asignar el rol '{edit_request.new_role}'",
            status_code=403
        )

    logger.info(f"Rol '{edit_request.new_role}' puede ser asignado por un usuario con rol '{current_user_role.name}'")

    # 11. Obtener el rol objetivo
    target_role = db.query(Role).filter(Role.name == edit_request.new_role).first()
    if not target_role:
        logger.error(f"Rol '{edit_request.new_role}' no encontrado en la base de datos")
        return create_response(
            "error",
            f"Rol '{edit_request.new_role}' no encontrado en la base de datos",
            status_code=500
        )

    logger.info(f"Rol objetivo encontrado: {target_role.name} (ID: {target_role.role_id})")

    # 12. Actualizar el rol del colaborador
    try:
        collaborator_role_farm.role_id = target_role.role_id
        db.commit()
        logger.info(f"Rol del colaborador {collaborator.name} actualizado a '{target_role.name}'")
    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar el rol del colaborador: {str(e)}")
        return create_response(
            "error",
            "Error al actualizar el rol del colaborador",
            status_code=500
        )

    # 13. Devolver la respuesta exitosa
    return create_response(
        "success",
        f"Rol del colaborador '{collaborator.name}' actualizado a '{target_role.name}' exitosamente",
        status_code=200
    )

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
from pydantic import BaseModel, Field
from models.models import (
    Farm,
    UserRoleFarm,
    User,
    RolePermission,
    Permission,
    Status,
    StatusType,
    Role
)
from utils.security import verify_session_token
from dataBase import get_db_session
from utils.response import create_response, session_token_invalid_response
from sqlalchemy import func
import logging



# Modelo Pydantic para la solicitud de eliminación de colaborador
class DeleteCollaboratorRequest(BaseModel):
    collaborator_user_id: int = Field(..., alias="collaborator_user_id")

    class Config:
        populate_by_name = True
        from_attributes = True

    def validate_input(self):
        if self.collaborator_user_id <= 0:
            raise ValueError("El `collaborator_user_id` debe ser un entero positivo.")

@router.post("/delete-collaborator", response_model=Dict[str, Any])
def delete_collaborator(
    delete_request: DeleteCollaboratorRequest,
    farm_id: int,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Endpoint para eliminar a un colaborador de una finca específica.
    Requiere `farm_id`, `session_token` y un cuerpo de solicitud con `collaborator_user_id`.
    """

    # 1. Validar la entrada
    try:
        delete_request.validate_input()
    except ValueError as e:
        logger.error(f"Validación de entrada fallida: {str(e)}")
        return create_response(
            "error",
            str(e),
            status_code=400
        )

    # 2. Verificar el session_token y obtener el usuario autenticado
    user = verify_session_token(session_token, db)
    if not user:
        return session_token_invalid_response()

    logger.info(f"Usuario autenticado: {user.name} (ID: {user.user_id})")

    # 3. Verificar que la finca exista
    farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
    if not farm:
        logger.error(f"Finca con ID {farm_id} no encontrada")
        return create_response(
            "error",
            "Finca no encontrada",
            status_code=404
        )

    logger.info(f"Finca encontrada: {farm.name} (ID: {farm.farm_id})")

    # 4. Obtener el estado 'Activo' para 'user_role_farm'
    active_status = db.query(Status).join(StatusType).filter(
        Status.name == "Activo",
        StatusType.name == "user_role_farm"
    ).first()

    if not active_status:
        logger.error("Estado 'Activo' no encontrado para 'user_role_farm'")
        return create_response(
            "error",
            "Estado 'Activo' no encontrado para 'user_role_farm'",
            status_code=400
        )

    logger.info(f"Estado 'Activo' encontrado: {active_status.name} (ID: {active_status.status_id})")

    # 5. Obtener la asociación UserRoleFarm del usuario con la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm_id,
        UserRoleFarm.status_id == active_status.status_id
    ).first()

    if not user_role_farm:
        logger.warning(f"Usuario {user.name} no está asociado a la finca ID {farm_id}")
        return create_response(
            "error",
            "No estás asociado a esta finca",
            status_code=403
        )

    # Obtener el rol del usuario que realiza la acción
    current_user_role = db.query(Role).filter(Role.role_id == user_role_farm.role_id).first()
    if not current_user_role:
        logger.error(f"Rol con ID {user_role_farm.role_id} no encontrado")
        return create_response(
            "error",
            "Rol del usuario no encontrado",
            status_code=500
        )

    logger.info(f"Rol del usuario: {current_user_role.name}")

    # 6. Obtener el colaborador a eliminar
    collaborator = db.query(User).filter(User.user_id == delete_request.collaborator_user_id).first()
    if not collaborator:
        logger.error(f"Colaborador con ID {delete_request.collaborator_user_id} no encontrado")
        return create_response(
            "error",
            "Colaborador no encontrado",
            status_code=404
        )

    logger.info(f"Colaborador a eliminar: {collaborator.name} (ID: {collaborator.user_id})")

    # 7. Verificar que el colaborador esté asociado activamente a la finca
    collaborator_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == collaborator.user_id,
        UserRoleFarm.farm_id == farm_id,
        UserRoleFarm.status_id == active_status.status_id
    ).first()

    if not collaborator_role_farm:
        logger.error(f"Colaborador {collaborator.name} no está asociado activamente a la finca ID {farm_id}")
        return create_response(
            "error",
            "El colaborador no está asociado activamente a esta finca",
            status_code=404
        )

    # 8. Verificar que el usuario no esté intentando eliminar su propia asociación
    if user.user_id == collaborator.user_id:
        logger.warning(f"Usuario {user.name} intentó eliminar su propia asociación con la finca")
        return create_response(
            "error",
            "No puedes eliminar tu propia asociación con la finca",
            status_code=403
        )

    # 9. Determinar el permiso requerido basado en el rol del colaborador
    collaborator_role = db.query(Role).filter(Role.role_id == collaborator_role_farm.role_id).first()
    if not collaborator_role:
        logger.error(f"Rol con ID {collaborator_role_farm.role_id} no encontrado para el colaborador")
        return create_response(
            "error",
            "Rol del colaborador no encontrado",
            status_code=500
        )

    logger.info(f"Rol del colaborador: {collaborator_role.name}")

    if collaborator_role.name == "Administrador de finca":
        required_permission_name = "delete_administrador_farm"
    elif collaborator_role.name == "Operador de campo":
        required_permission_name = "delete_operador_farm"
    else:
        logger.error(f"Rol '{collaborator_role.name}' no reconocido para eliminación")
        return create_response(
            "error",
            f"Rol '{collaborator_role.name}' no reconocido para eliminación",
            status_code=400
        )

    # 10. Obtener el permiso requerido
    required_permission = db.query(Permission).filter(
        func.lower(Permission.name) == required_permission_name.lower()
    ).first()

    if not required_permission:
        logger.error(f"Permiso '{required_permission_name}' no encontrado en la base de datos")
        return create_response(
            "error",
            f"Permiso '{required_permission_name}' no encontrado en la base de datos",
            status_code=500
        )

    logger.info(f"Permiso requerido para eliminar '{collaborator_role.name}': {required_permission.name}")

    # 11. Verificar si el usuario tiene el permiso necesario
    has_permission = db.query(RolePermission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        RolePermission.permission_id == required_permission.permission_id
    ).first()

    if not has_permission:
        logger.warning(f"Usuario {user.name} no tiene permiso '{required_permission.name}'")
        return create_response(
            "error",
            f"No tienes permiso para eliminar a un colaborador con rol '{collaborator_role.name}'",
            status_code=403
        )

    logger.info(f"Usuario {user.name} tiene permiso '{required_permission.name}'")

    # 12. Eliminar la asociación del colaborador con la finca (Actualizar el estado a 'Inactivo')
    try:
        # Obtener el estado 'Inactivo' para 'user_role_farm'
        inactive_status = db.query(Status).join(StatusType).filter(
            Status.name == "Inactivo",
            StatusType.name == "user_role_farm"
        ).first()

        if not inactive_status:
            logger.error("Estado 'Inactivo' no encontrado para 'user_role_farm'")
            return create_response(
                "error",
                "Estado 'Inactivo' no encontrado para 'user_role_farm'",
                status_code=500
            )

        collaborator_role_farm.status_id = inactive_status.status_id
        db.commit()
        logger.info(f"Colaborador {collaborator.name} eliminado de la finca ID {farm_id} exitosamente")
    except Exception as e:
        db.rollback()
        logger.error(f"Error al eliminar el colaborador: {str(e)}")
        return create_response(
            "error",
            "Error al eliminar el colaborador",
            status_code=500
        )

    # 13. Devolver la respuesta exitosa
    return create_response(
        "success",
        f"Colaborador '{collaborator.name}' eliminado exitosamente de la finca '{farm.name}'",
        status_code=200
    )
