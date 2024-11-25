from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.models import (
    Transaction, TransactionCategory, TransactionType, Recommendation, Plot,User,CulturalWorkTask,CulturalWork,HealthCheck, Farm, UserRoleFarm, Status, RolePermission, Permission
)
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import List, Optional
from utils.response import create_response, session_token_invalid_response
from utils.status import get_status
from pydantic import BaseModel, Field, conlist
from datetime import date
from fastapi.encoders import jsonable_encoder
from collections import defaultdict

router = APIRouter()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modelos de Pydantic

class FinancialReportRequest(BaseModel):
    plot_ids: conlist(int) = Field(..., description="Lista de IDs de lotes (puede ser un solo ID)")
    fechaInicio: date = Field(..., description="Fecha de inicio del periodo")
    fechaFin: date = Field(..., description="Fecha de fin del periodo")
    include_transaction_history: bool = Field(False, description="Indica si se debe incluir el historial de transacciones")


class FinancialCategoryBreakdown(BaseModel):
    category_name: str
    monto: float

class PlotFinancialData(BaseModel):
    plot_id: int
    plot_name: str
    ingresos: float
    gastos: float
    balance: float
    ingresos_por_categoria: List[FinancialCategoryBreakdown]
    gastos_por_categoria: List[FinancialCategoryBreakdown]

class FarmFinancialSummary(BaseModel):
    total_ingresos: float
    total_gastos: float
    balance_financiero: float
    ingresos_por_categoria: List[FinancialCategoryBreakdown]
    gastos_por_categoria: List[FinancialCategoryBreakdown]


class TransactionHistoryItem(BaseModel):
    date: date
    plot_name: str
    farm_name: str
    transaction_type: str
    transaction_category: str
    creator_name: str
    value: float
    
class FinancialReportResponse(BaseModel):
    finca_nombre: str
    lotes_incluidos: List[str]
    periodo: str
    plot_financials: List[PlotFinancialData]
    farm_summary: FarmFinancialSummary
    analysis: Optional[str] = None
    transaction_history: Optional[List[TransactionHistoryItem]] = None


class DetectionHistoryRequest(BaseModel):
    plot_ids: conlist(int) = Field(..., description="Lista de IDs de lotes (puede ser uno o varios)")
    fechaInicio: date = Field(..., description="Fecha de inicio del periodo")
    fechaFin: date = Field(..., description="Fecha de fin del periodo")

class DetectionHistoryItem(BaseModel):
    date: date
    person_name: str
    detection: str
    recommendation: str
    cultural_work: str
    lote_name: str
    farm_name: str

class DetectionHistoryResponse(BaseModel):
    detections: List[DetectionHistoryItem]

# Endpoint para generar el reporte financiero
@router.post("/financial-report")
def financial_report(
    request: FinancialReportRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Genera un reporte financiero detallado de los lotes seleccionados en una finca específica.

    - **request**: Contiene los IDs de los lotes, el rango de fechas y si se debe incluir el historial de transacciones.
    - **session_token**: Token de sesión del usuario para validar su autenticación.
    - **db**: Sesión de base de datos proporcionada automáticamente por FastAPI.

    El reporte incluye ingresos, gastos y balance financiero de los lotes y la finca en general.
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
    
    try:
        # 3. Obtener los lotes seleccionados
        plots = db.query(Plot).filter(Plot.plot_id.in_(request.plot_ids)).all()
        if not plots:
            logger.warning("No se encontraron lotes con los IDs proporcionados")
            return create_response("error", "No se encontraron lotes con los IDs proporcionados", status_code=404)
        
        # Asegurarse de que todos los lotes pertenezcan a la misma finca
        farm_ids = {plot.farm_id for plot in plots}
        if len(farm_ids) != 1:
            logger.warning("Los lotes seleccionados pertenecen a diferentes fincas")
            return create_response("error", "Los lotes seleccionados pertenecen a diferentes fincas", status_code=400)
        
        farm_id = farm_ids.pop()
        farm = db.query(Farm).filter(Farm.farm_id == farm_id).first()
        if not farm:
            logger.warning("La finca asociada a los lotes no existe")
            return create_response("error", "La finca asociada a los lotes no existe", status_code=404)
        
        # 4. Verificar que el usuario esté asociado con esta finca y tenga permisos
        active_urf_status = get_status(db, "Activo", "user_role_farm")
        if not active_urf_status:
            logger.error("Estado 'Activo' para user_role_farm no encontrado")
            return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=500)
        
        user_role_farm = db.query(UserRoleFarm).filter(
            UserRoleFarm.user_id == user.user_id,
            UserRoleFarm.farm_id == farm_id,
            UserRoleFarm.status_id == active_urf_status.status_id
        ).first()
        
        if not user_role_farm:
            logger.warning(f"El usuario {user.user_id} no está asociado con la finca {farm_id}")
            return create_response("error", "No tienes permisos para ver reportes financieros de esta finca", status_code=403)
        
        # Verificar permiso 'read_financial_report'
        role_permission = db.query(RolePermission).join(Permission).filter(
            RolePermission.role_id == user_role_farm.role_id,
            Permission.name == "read_financial_report"
        ).first()
        
        if not role_permission:
            logger.warning(f"El rol {user_role_farm.role_id} del usuario no tiene permiso para ver reportes financieros")
            return create_response("error", "No tienes permiso para ver reportes financieros", status_code=403)
        
        # 5. Obtener el estado 'Activo' para Transaction
        active_transaction_status = get_status(db, "Activo", "Transaction")
        if not active_transaction_status:
            logger.error("Estado 'Activo' para Transaction no encontrado")
            return create_response("error", "Estado 'Activo' para Transaction no encontrado", status_code=500)
        
        # 6. Consultar las transacciones de los lotes seleccionados dentro del rango de fechas
        transactions = db.query(Transaction).filter(
            Transaction.plot_id.in_(request.plot_ids),
            Transaction.transaction_date >= request.fechaInicio,
            Transaction.transaction_date <= request.fechaFin,
            Transaction.status_id == active_transaction_status.status_id
        ).all()
        
        # 7. Procesar las transacciones para agregaciones
        plot_financials = {}
        farm_ingresos = 0.0
        farm_gastos = 0.0
        farm_ingresos_categorias = defaultdict(float)
        farm_gastos_categorias = defaultdict(float)
        
        for plot in plots:
            plot_financials[plot.plot_id] = {
                "plot_id": plot.plot_id,
                "plot_name": plot.name,
                "ingresos": 0.0,
                "gastos": 0.0,
                "balance": 0.0,
                "ingresos_por_categoria": defaultdict(float),
                "gastos_por_categoria": defaultdict(float)
            }
        
        for txn in transactions:
            plot_id = txn.plot_id
            txn_type = txn.transaction_type
            txn_category = txn.transaction_category
            
            if not txn_type or not txn_category:
                logger.warning(f"Transacción con ID {txn.transaction_id} tiene tipo o categoría inválidos")
                continue  # Omitir transacciones incompletas
            
            category = txn_category.name
            monto = float(txn.value)
            
            if txn_type.name.lower() in ["ingreso", "income", "revenue"]:
                plot_financials[plot_id]["ingresos"] += monto
                plot_financials[plot_id]["ingresos_por_categoria"][category] += monto
                farm_ingresos += monto
                farm_ingresos_categorias[category] += monto
            elif txn_type.name.lower() in ["gasto", "expense", "cost"]:
                plot_financials[plot_id]["gastos"] += monto
                plot_financials[plot_id]["gastos_por_categoria"][category] += monto
                farm_gastos += monto
                farm_gastos_categorias[category] += monto
            else:
                logger.warning(f"Transacción con ID {txn.transaction_id} tiene un tipo desconocido '{txn_type.name}'")
        
        # Calcular balances por lote
        plot_financials_list = []
        for plot_id, data in plot_financials.items():
            data["balance"] = data["ingresos"] - data["gastos"]
            # Convertir defaultdict a list de FinancialCategoryBreakdown
            data["ingresos_por_categoria"] = [
                FinancialCategoryBreakdown(category_name=k, monto=v) for k, v in data["ingresos_por_categoria"].items()
            ]
            data["gastos_por_categoria"] = [
                FinancialCategoryBreakdown(category_name=k, monto=v) for k, v in data["gastos_por_categoria"].items()
            ]
            plot_financials_list.append(PlotFinancialData(**data))
        
        # Resumen financiero de la finca
        farm_balance = farm_ingresos - farm_gastos
        farm_summary = FarmFinancialSummary(
            total_ingresos=farm_ingresos,
            total_gastos=farm_gastos,
            balance_financiero=farm_balance,
            ingresos_por_categoria=[
                FinancialCategoryBreakdown(category_name=k, monto=v) for k, v in farm_ingresos_categorias.items()
            ],
            gastos_por_categoria=[
                FinancialCategoryBreakdown(category_name=k, monto=v) for k, v in farm_gastos_categorias.items()
            ]
        )
        
        # Preparar la respuesta
        report_response = FinancialReportResponse(
            finca_nombre=farm.name,
            lotes_incluidos=[plot.name for plot in plots],
            periodo=f"{request.fechaInicio.isoformat()} a {request.fechaFin.isoformat()}",
            plot_financials=plot_financials_list,
            farm_summary=farm_summary,
            analysis=None  # Puedes agregar lógica para generar un análisis automático si lo deseas
        )
        
        # Agregar historial de transacciones si se solicita
        if request.include_transaction_history:
            transaction_history = []
            for txn in transactions:
                try:
                    # Obtener el nombre del creador consultando la tabla User
                    creator = db.query(User).filter(User.user_id == txn.creador_id).first()
                    creator_name = creator.name if creator else "Desconocido"

                    history_item = TransactionHistoryItem(
                        date=txn.transaction_date,
                        plot_name=txn.plot.name,
                        farm_name=txn.plot.farm.name,
                        transaction_type=txn.transaction_type.name,
                        transaction_category=txn.transaction_category.name,
                        creator_name=creator_name,
                        value=float(txn.value)
                    )
                    transaction_history.append(history_item)
                except Exception as e:
                    logger.warning(f"Error al procesar la transacción ID {txn.transaction_id}: {str(e)}")
                    continue  # Omitir transacciones con errores
            report_response.transaction_history = transaction_history

        
        logger.info(f"Reporte financiero generado para el usuario {user.user_id} en la finca '{farm.name}'")
        
        return create_response("success", "Reporte financiero generado correctamente", data=jsonable_encoder(report_response))
    
    except Exception as e:
        logger.error(f"Error al generar el reporte financiero: {str(e)}")
        return create_response("error", f"Error al generar el reporte financiero: {str(e)}", status_code=500)
    

@router.post("/detection-report", response_model=DetectionHistoryResponse)
def detection_history(
    request: DetectionHistoryRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Genera un historial de detecciones de salud para los lotes seleccionados.

    - **request**: Contiene los IDs de los lotes y el rango de fechas.
    - **session_token**: Token de sesión del usuario para validar su autenticación.
    - **db**: Sesión de base de datos proporcionada automáticamente por FastAPI.

    El historial de detecciones incluye información detallada de las detecciones aceptadas en los lotes especificados.
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
    
    try:
        # 3. Obtener los lotes seleccionados
        plots = db.query(Plot).filter(Plot.plot_id.in_(request.plot_ids)).all()
        if not plots:
            logger.warning("No se encontraron lotes con los IDs proporcionados")
            return create_response("error", "No se encontraron lotes con los IDs proporcionados", status_code=404)
        
        # 4. Obtener las fincas asociadas a los lotes
        farm_ids = {plot.farm_id for plot in plots}
        farms = db.query(Farm).filter(Farm.farm_id.in_(farm_ids)).all()
        if not farms:
            logger.warning("No se encontraron fincas asociadas a los lotes proporcionados")
            return create_response("error", "No se encontraron fincas asociadas a los lotes proporcionados", status_code=404)
        
        # 5. Verificar que el usuario esté asociado con todas las fincas y tenga permisos
        active_urf_status = get_status(db, "Activo", "user_role_farm")
        if not active_urf_status:
            logger.error("Estado 'Activo' para user_role_farm no encontrado")
            return create_response("error", "Estado 'Activo' para user_role_farm no encontrado", status_code=500)
        
        # Verificar permisos para cada finca
        for farm in farms:
            user_role_farm = db.query(UserRoleFarm).filter(
                UserRoleFarm.user_id == user.user_id,
                UserRoleFarm.farm_id == farm.farm_id,
                UserRoleFarm.status_id == active_urf_status.status_id
            ).first()
            
            if not user_role_farm:
                logger.warning(f"El usuario {user.user_id} no está asociado con la finca {farm.farm_id}")
                return create_response("error", f"No tienes permisos para ver reportes de la finca '{farm.name}'", status_code=403)
            
            # Verificar permiso 'read_health_checks_report'
            role_permission = db.query(RolePermission).join(Permission).filter(
                RolePermission.role_id == user_role_farm.role_id,
                Permission.name == "read_health_checks_report"
            ).first()
            
            if not role_permission:
                logger.warning(f"El rol {user_role_farm.role_id} del usuario no tiene permiso para ver reportes de salud")
                return create_response("error", "No tienes permiso para ver reportes de salud", status_code=403)
        
        # 6. Obtener el estado 'Aceptado' para Deteccion
        accepted_status = get_status(db, "Aceptado", "Deteccion")
        if not accepted_status:
            logger.error("Estado 'Aceptado' para Deteccion no encontrado")
            return create_response("error", "Estado 'Aceptado' para Deteccion no encontrado", status_code=500)
        
        # 7. Consultar las detecciones dentro del rango de fechas y con estado 'Aceptado' y tipo 'Deteccion'
        detections = db.query(HealthCheck).join(CulturalWorkTask).join(Plot).join(Farm).join(Recommendation).filter(
            CulturalWorkTask.plot_id.in_(request.plot_ids),
            HealthCheck.check_date >= request.fechaInicio,
            HealthCheck.check_date <= request.fechaFin,
            HealthCheck.status_id == accepted_status.status_id
            ).all()
        
        # 8. Procesar las detecciones para la respuesta
        detection_history = []
        for detection in detections:
            cultural_work_task = detection.cultural_work_task
            
            # Obtener el usuario colaborador
            collaborator_user = db.query(User).filter(
                User.user_id == cultural_work_task.collaborator_user_id
            ).first()
            collaborator_name = collaborator_user.name if collaborator_user else "Desconocido"
            
            
            PREDICTION_MAPPING = {
                'nitrogen_N': 'Deficiencia de nitrógeno',
                'phosphorus_P': 'Deficiencia de fósforo',
                'potassium_K': 'Deficiencia de potasio',
                'cercospora': 'Cercospora',
                'ferrugem': 'Mancha de hierro',
                'leaf_rust': 'Roya'
            }

            mapped_prediction = PREDICTION_MAPPING.get(detection.prediction, detection.prediction)

            detection_item = DetectionHistoryItem(
                date=detection.check_date,
                person_name=collaborator_name,  # Asignar al colaborador
                detection=mapped_prediction,     # Asignar la predicción mapeada
                recommendation=detection.recommendation.recommendation if detection.recommendation else "Sin recomendación",
                cultural_work=cultural_work_task.cultural_work.name if cultural_work_task.cultural_work else "Sin tarea cultural",
                lote_name=cultural_work_task.plot.name if cultural_work_task.plot else "Sin lote",
                farm_name=cultural_work_task.plot.farm.name if cultural_work_task.plot and cultural_work_task.plot.farm else "Sin finca"
            )
            detection_history.append(detection_item)
        
        response = DetectionHistoryResponse(detections=detection_history)
        
        logger.info(f"Historial de detecciones generado para el usuario {user.user_id}")
        
        return create_response("success", "Historial de detecciones generado correctamente", data=jsonable_encoder(response))
    
    except Exception as e:
        logger.error(f"Error al generar el historial de detecciones: {str(e)}")
        return create_response("error", f"Error al generar el historial de detecciones: {str(e)}", status_code=500)
