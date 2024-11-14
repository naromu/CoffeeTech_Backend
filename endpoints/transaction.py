from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field, constr
from sqlalchemy.orm import Session
from models.models import (
    TransactionCategory,Transaction, TransactionType, Plot, Farm, User, Status, RolePermission, Permission, UserRoleFarm, Notification, NotificationType
)
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import Optional, List
from utils.response import session_token_invalid_response, create_response
from utils.status import get_status
from datetime import datetime, date
from utils.FCM import send_fcm_notification
import pytz
from fastapi.encoders import jsonable_encoder


router = APIRouter()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bogota_tz = pytz.timezone("America/Bogota")

# Pydantic Models for Transaction Endpoints

class CreateTransactionRequest(BaseModel):
    plot_id: int = Field(..., description="ID del lote asociado a la transacción")
    transaction_type_name: str = Field(..., description="Nombre del tipo de transacción")
    transaction_category_name: str = Field(..., description="Nombre de la categoría de la transacción")

    description: Optional[constr(max_length=50)] = Field(None, description="Descripción de la transacción (máximo 50 caracteres)")
    value: int = Field(..., description="Valor de la transacción")
    transaction_date: date = Field(..., description="Fecha de la transacción")

class UpdateTransactionRequest(BaseModel):
    transaction_id: int = Field(..., description="ID de la transacción a actualizar")
    transaction_type_name: Optional[str] = Field(None, description="Nuevo nombre del tipo de transacción")
    transaction_category_name: Optional[str] = Field(None, description="Nuevo nombre de la categoría de la transacción")
    description: Optional[constr(max_length=50)] = Field(None, description="Nueva descripción de la transacción (máximo 50 caracteres)")
    value: Optional[int] = Field(None, description="Nuevo valor de la transacción")
    transaction_date: Optional[date] = Field(None, description="Nueva fecha de la transacción")

class DeleteTransactionRequest(BaseModel):
    transaction_id: int = Field(..., description="ID de la transacción a eliminar")

class TransactionResponse(BaseModel):
    transaction_id: int
    plot_id: int
    transaction_type_name: str
    transaction_category_name: str  # Nuevo campo

    description: Optional[str]
    value: int
    transaction_date: date
    status: str

# Endpoint to Create a Transaction
@router.post("/create-transaction")
def create_transaction(
    request: CreateTransactionRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Crear una nueva transacción para un lote en una finca.

    - **farm_id**: ID de la finca
    - **plot_id**: ID del lote
    - **transaction_type**: Tipo de transacción (Ej. 'ingreso', 'gasto')
    - **category**: Categoría de la transacción (Ej. 'fertilizante', 'mano de obra')
    - **value**: Valor monetario de la transacción
    - **description**: Descripción detallada de la transacción
    """
    # 1. Verificar que el session_token esté presente
    if not session_token:
        logger.warning("No se proporcionó el token de sesión en la cabecera")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # 2. Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # 3. Verificar que el usuario tenga permiso 'add_transaction'
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("Estado 'Activo' para user_role_farm no encontrado")
        return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=400)
    
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    
    if not user_role_farm:
        logger.warning(f"El usuario {user.user_id} no está asociado con ninguna finca activa")
        return create_response("error", "No tienes permisos para agregar transacciones", status_code=403)
    
    # Verificar permiso 'add_transaction'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "add_transaction"
    ).first()
    
    if not role_permission:
        logger.warning(f"El rol {user_role_farm.role_id} del usuario no tiene permiso para agregar transacciones")
        return create_response("error", "No tienes permiso para agregar transacciones", status_code=403)
    
    # 4. Verificar que el lote existe y está activo
    active_plot_status = get_status(db, "Activo", "Plot")
    if not active_plot_status:
        logger.error("Estado 'Activo' para Plot no encontrado")
        return create_response("error", "Estado 'Activo' para Plot no encontrado", status_code=500)
    
    plot = db.query(Plot).filter(
        Plot.plot_id == request.plot_id,
        Plot.status_id == active_plot_status.status_id
    ).first()
    
    if not plot:
        logger.warning(f"El lote con ID {request.plot_id} no existe o no está activo")
        return create_response("error", "El lote especificado no existe o no está activo", status_code=404)
    
    
    # 6. Verificar que el tipo de transacción existe
    transaction_type = db.query(TransactionType).filter(TransactionType.name == request.transaction_type_name).first()
    if not transaction_type:
        logger.warning(f"El tipo de transacción '{request.transaction_type_name}' no existe")
        return create_response("error", "El tipo de transacción especificado no existe", status_code=400)
    
    # 7. Verificar que el valor sea positivo
    if request.value <= 0:
        logger.warning("El valor de la transacción debe ser positivo")
        return create_response("error", "El valor de la transacción debe ser positivo", status_code=400)
    
     # 8. Verificar que la categoría de transacción existe para el tipo de transacción
    transaction_category = db.query(TransactionCategory).filter(
        TransactionCategory.name == request.transaction_category_name,
        TransactionCategory.transaction_type_id == transaction_type.transaction_type_id
    ).first()
    if not transaction_category:
        logger.warning(f"La categoría de transacción '{request.transaction_category_name}' no existe para el tipo '{request.transaction_type_name}'")
        return create_response("error", "La categoría de transacción especificada no existe para el tipo de transacción proporcionado", status_code=400)
    
    
    # 9. Obtener el estado 'Activo' para Transaction
    active_status = get_status(db, "Activo", "Transaction")
    if not active_status:
        logger.error("Estado 'Activo' para Transaction no encontrado")
        return create_response("error", "Estado 'Activo' para Transaction no encontrado", status_code=500)
    
    # 10. Crear la transacción
    try:
        new_transaction = Transaction(
            plot_id=request.plot_id,
            transaction_type_id=transaction_type.transaction_type_id,
            transaction_category_id=transaction_category.transaction_category_id,  # Asignar categoría
            description=request.description,
            value=request.value,
            transaction_date=request.transaction_date,
            status_id=active_status.status_id,
            creador_id=user.user_id
        )
        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)
        
        logger.info(f"Transacción creada exitosamente con ID: {new_transaction.transaction_id}")
        
        response_data = TransactionResponse(
            transaction_id=new_transaction.transaction_id,
            plot_id=new_transaction.plot_id,
            transaction_type_name=transaction_type.name,
            transaction_category_name=transaction_category.name,  # Incluir categoría
            description=new_transaction.description,
            value=new_transaction.value,
            transaction_date=new_transaction.transaction_date,
            status=active_status.name
            )
        
        # Convertir a JSON serializable usando jsonable_encoder
        response_dict = jsonable_encoder(response_data.dict())
        
        return create_response("success", "Transacción creada correctamente", data=response_dict)
    
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error al crear la transacción: {str(e)}")
        return create_response("error", f"Error al crear la transacción: {str(e)}", status_code=500)

# Endpoint to Edit a Transaction
@router.post("/edit-transaction")
def edit_transaction(
    request: UpdateTransactionRequest,
    session_token: str ,
    db: Session = Depends(get_db_session)
):
    """
    Editar una transacción existente para un lote en una finca.

    - **transaction_id**: ID de la transacción
    - **transaction_type**: Nuevo tipo de transacción
    - **category**: Nueva categoría de la transacción
    - **value**: Nuevo valor monetario de la transacción
    - **description**: Nueva descripción de la transacción
    """
    # 1. Verificar que el session_token esté presente
    if not session_token:
        logger.warning("No se proporcionó el token de sesión en la cabecera")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # 2. Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # 3. Obtener la transacción a actualizar
    transaction = db.query(Transaction).filter(Transaction.transaction_id == request.transaction_id).first()
    if not transaction:
        logger.warning(f"La transacción con ID {request.transaction_id} no existe")
        return create_response("error", "La transacción especificada no existe", status_code=404)
    
    # 4. Verificar que la transacción no esté inactiva
    inactive_status = get_status(db, "Inactivo", "Transaction")
    if not inactive_status:
        logger.error("Estado 'Inactivo' para Transaction no encontrado")
        return create_response("error", "Estado 'Inactivo' para Transaction no encontrado", status_code=500)
    
    if transaction.status_id == inactive_status.status_id:
        logger.warning(f"La transacción con ID {request.transaction_id} está inactiva y no puede ser modificada")
        return create_response("error", "La transacción está inactiva y no puede ser modificada", status_code=403)
 
    # 5. Verificar que el usuario esté asociado con la finca del lote de la transacción
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("Estado 'Activo' para user_role_farm no encontrado")
        return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=400)
    
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == transaction.plot.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    
    if not user_role_farm:
        logger.warning(f"El usuario {user.user_id} no está asociado con la finca {transaction.plot.farm_id}")
        return create_response("error", "No tienes permisos para editar transacciones en esta finca", status_code=403)
    
    # 6. Verificar permiso 'edit_transaction'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "edit_transaction"
    ).first()
    
    if not role_permission:
        logger.warning(f"El rol {user_role_farm.role_id} del usuario no tiene permiso para editar transacciones")
        return create_response("error", "No tienes permiso para editar transacciones", status_code=403)
    
    # 7. Realizar las actualizaciones permitidas
    try:
        # Actualizar el tipo de transacción si se proporciona
        if request.transaction_type_name:
            transaction_type = db.query(TransactionType).filter(TransactionType.name == request.transaction_type_name).first()
            if not transaction_type:
                logger.warning(f"El tipo de transacción '{request.transaction_type_name}' no existe")
                return create_response("error", "El tipo de transacción especificado no existe", status_code=400)
            transaction.transaction_type_id = transaction_type.transaction_type_id
        
        # Actualizar la categoría de transacción si se proporciona
        if request.transaction_category_name:
            # Si el tipo de transacción se ha actualizado en este mismo request, usar el nuevo tipo
            current_transaction_type_id = request.transaction_type_name and transaction_type.transaction_type_id or transaction.transaction_type_id
            transaction_category = db.query(TransactionCategory).filter(
                TransactionCategory.name == request.transaction_category_name,
                TransactionCategory.transaction_type_id == current_transaction_type_id
            ).first()
            if not transaction_category:
                logger.warning(f"La categoría de transacción '{request.transaction_category_name}' no existe para el tipo de transacción actual")
                return create_response("error", "La categoría de transacción especificada no existe para el tipo de transacción actual", status_code=400)
            transaction.transaction_category_id = transaction_category.transaction_category_id
        
        # Actualizar la descripción si se proporciona
        if request.description is not None:
            if len(request.description) > 50:
                logger.warning("La descripción excede los 50 caracteres")
                return create_response("error", "La descripción no puede exceder los 50 caracteres", status_code=400)
            transaction.description = request.description
        
        # Actualizar el valor si se proporciona
        if request.value is not None:
            if request.value <= 0:
                logger.warning("El valor de la transacción debe ser positivo")
                return create_response("error", "El valor de la transacción debe ser positivo", status_code=400)
            transaction.value = request.value
        
        # Actualizar la fecha de la transacción si se proporciona
        if request.transaction_date is not None:
            transaction.transaction_date = request.transaction_date
        
        db.commit()
        db.refresh(transaction)
        
        # Obtener el estado actual
        status = db.query(Status).filter(Status.status_id == transaction.status_id).first()
        status_name = status.name if status else "Desconocido"
        
        # Obtener el tipo de transacción actualizado
        txn_type = db.query(TransactionType).filter(TransactionType.transaction_type_id == transaction.transaction_type_id).first()
        txn_type_name = txn_type.name if txn_type else "Desconocido"
        
        # Obtener la categoría de transacción actualizada
        txn_category = db.query(TransactionCategory).filter(TransactionCategory.transaction_category_id == transaction.transaction_category_id).first()
        txn_category_name = txn_category.name if txn_category else "Desconocido"
        
        response_data = TransactionResponse(
            transaction_id=transaction.transaction_id,
            plot_id=transaction.plot_id,
            transaction_type_name=txn_type_name,
            transaction_category_name=txn_category_name,  # Incluir categoría
            description=transaction.description,
            value=transaction.value,
            transaction_date=transaction.transaction_date,
            status=status_name
        )
        
        response_dict = jsonable_encoder(response_data.dict())

        logger.info(f"Transacción con ID {transaction.transaction_id} actualizada exitosamente")
        
        return create_response("success", "Transacción actualizada correctamente", data=response_dict)
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error al actualizar la transacción: {str(e)}")
        return create_response("error", f"Error al actualizar la transacción: {str(e)}", status_code=500)

# Endpoint to Delete a Transaction
@router.post("/delete-transaction")
def delete_transaction(
    request: DeleteTransactionRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Eliminar una transacción existente para un lote.

    - **transaction_id**: ID de la transacción a eliminar
    - **session_token**: Token de sesión del usuario para verificar permisos y autenticación
    """
    # 1. Verificar que el session_token esté presente
    if not session_token:
        logger.warning("No se proporcionó el token de sesión en la cabecera")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # 2. Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # 3. Obtener la transacción a eliminar
    transaction = db.query(Transaction).filter(Transaction.transaction_id == request.transaction_id).first()
    if not transaction:
        logger.warning(f"La transacción con ID {request.transaction_id} no existe")
        return create_response("error", "La transacción especificada no existe", status_code=404)
    
    # 4. Verificar que la transacción no esté ya inactiva
    inactive_status = get_status(db, "Inactivo", "Transaction")
    if not inactive_status:
        logger.error("Estado 'Inactivo' para Transaction no encontrado")
        return create_response("error", "Estado 'Inactivo' para Transaction no encontrado", status_code=500)
    
    if transaction.status_id == inactive_status.status_id:
        logger.warning(f"La transacción con ID {request.transaction_id} ya está inactiva")
        return create_response("error", "La transacción ya está eliminada", status_code=400)
    
    # 5. Verificar que el usuario esté asociado con la finca del lote de la transacción
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("Estado 'Activo' para user_role_farm no encontrado")
        return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=400)
    
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == transaction.plot.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    
    if not user_role_farm:
        logger.warning(f"El usuario {user.user_id} no está asociado con la finca {transaction.plot.farm_id}")
        return create_response("error", "No tienes permisos para eliminar transacciones en esta finca", status_code=403)
    
    # 6. Verificar permiso 'delete_transaction'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "delete_transaction"
    ).first()
    
    if not role_permission:
        logger.warning(f"El rol {user_role_farm.role_id} del usuario no tiene permiso para eliminar transacciones")
        return create_response("error", "No tienes permiso para eliminar transacciones", status_code=403)
    
    # 7. Cambiar el estado de la transacción a 'Inactivo'
    try:
        transaction.status_id = inactive_status.status_id
        db.commit()
        logger.info(f"Transacción con ID {transaction.transaction_id} eliminada exitosamente")
        return create_response("success", "Transacción eliminada correctamente", data={"transaction_id": transaction.transaction_id})
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error al eliminar la transacción: {str(e)}")
        return create_response("error", f"Error al eliminar la transacción: {str(e)}", status_code=500)

# Endpoint to Read Transactions for a Plot
@router.get("/list-transactions/{plot_id}")
def read_transactions(
    plot_id: int,
    session_token: str ,
    db: Session = Depends(get_db_session)
):
    """
    Obtener la lista de transacciones de un lote específico.

    - **plot_id**: ID del lote del que se desea obtener las transacciones
    - **session_token**: Token de sesión del usuario para verificar permisos y autenticación
    """
    # 1. Verificar que el session_token esté presente
    if not session_token:
        logger.warning("No se proporcionó el token de sesión en la cabecera")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # 2. Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        return session_token_invalid_response()
    
    # 3. Verificar que el lote exista y esté activo
    active_plot_status = get_status(db, "Activo", "Plot")
    if not active_plot_status:
        logger.error("Estado 'Activo' para Plot no encontrado")
        return create_response("error", "Estado 'Activo' para Plot no encontrado", status_code=400)
    
    plot = db.query(Plot).filter(
        Plot.plot_id == plot_id,
        Plot.status_id == active_plot_status.status_id
    ).first()
    if not plot:
        logger.warning(f"El lote con ID {plot_id} no existe o no está activo")
        return create_response("error", "El lote no existe o no está activo", status_code=404)
    
    # 4. Verificar que el usuario esté asociado con la finca del lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe", status_code=404)
    
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    if not active_urf_status:
        logger.error("Estado 'Activo' para user_role_farm no encontrado")
        return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=400)
    
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    
    if not user_role_farm:
        logger.warning(f"El usuario no está asociado con la finca con ID {farm.farm_id}")
        return create_response("error", "No tienes permiso para ver las transacciones en esta finca", status_code=403)
    
    # 5. Verificar permiso 'read_transaction'
    role_permission = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "read_transaction"
    ).first()
    if not role_permission:
        logger.warning("El rol del usuario no tiene permiso para leer transacciones")
        return create_response("error", "No tienes permiso para ver las transacciones en esta finca", status_code=403)
    
    # 6. Obtener el estado "Inactivo" para Transaction
    inactive_transaction_status = get_status(db, "Inactivo", "Transaction")
    if not inactive_transaction_status:
        logger.error("Estado 'Inactivo' para Transaction no encontrado")
        return create_response("error", "Estado 'Inactivo' para Transaction no encontrado", status_code=500)
    
    # 7. Consultar las transacciones del lote que no están inactivas
    transactions = db.query(Transaction).filter(
        Transaction.plot_id == plot_id,
        Transaction.status_id != inactive_transaction_status.status_id
    ).all()
    
    # 8. Preparar la lista de transacciones
    transaction_list = []
    for txn in transactions:
        # Obtener el tipo de transacción
        txn_type = db.query(TransactionType).filter(TransactionType.transaction_type_id == txn.transaction_type_id).first()
        txn_type_name = txn_type.name if txn_type else "Desconocido"
        
        # Obtener la categoría de la transacción
        txn_category = db.query(TransactionCategory).filter(TransactionCategory.transaction_category_id == txn.transaction_category_id).first()
        txn_category_name = txn_category.name if txn_category else "Desconocido"
        
        # Obtener el estado de la transacción
        status = db.query(Status).filter(Status.status_id == txn.status_id).first()
        status_name = status.name if status else "Desconocido"
        
        transaction_list.append({
            "transaction_id": txn.transaction_id,
            "plot_id": txn.plot_id,
            "transaction_type_name": txn_type_name,
            "transaction_category_name": txn_category_name,  # Incluir categoría
            "description": txn.description,
            "value": txn.value,
            "transaction_date": txn.transaction_date.isoformat(),
            "status": status_name
        })
    
    if not transaction_list:
        return create_response("success", "El lote no tiene transacciones registradas", {"transactions": []})
    
    return create_response("success", "Transacciones obtenidas exitosamente", {"transactions": transaction_list})
