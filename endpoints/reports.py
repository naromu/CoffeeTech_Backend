from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from models.models import (
    Transaction, TransactionCategory, TransactionType, Plot, Farm, UserRoleFarm, Status, RolePermission, Permission
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

class FinancialReportResponse(BaseModel):
    finca_nombre: str
    lotes_incluidos: List[str]
    periodo: str
    plot_financials: List[PlotFinancialData]
    farm_summary: FarmFinancialSummary
    analysis: Optional[str] = None

# Endpoint para generar el reporte financiero
@router.post("/financial-report")
def financial_report(
    request: FinancialReportRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
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
            txn_type = db.query(TransactionType).filter(TransactionType.transaction_type_id == txn.transaction_type_id).first()
            txn_category = db.query(TransactionCategory).filter(TransactionCategory.transaction_category_id == txn.transaction_category_id).first()
            
            if not txn_type or not txn_category:
                logger.warning(f"Transacción con ID {txn.transaction_id} tiene tipo o categoría inválidos")
                continue  # Omitir transacciones incompletas
            
            category = txn_category.name
            monto = float(txn.value)
            
            if txn_type.name.lower() in ["ingreso", "income", "revenue"]:  # Asegúrate de que los nombres coincidan
                plot_financials[plot_id]["ingresos"] += monto
                plot_financials[plot_id]["ingresos_por_categoria"][category] += monto
                farm_ingresos += monto
                farm_ingresos_categorias[category] += monto
            elif txn_type.name.lower() in ["gasto", "expense", "cost"]:  # Asegúrate de que los nombres coincidan
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
        
        logger.info(f"Reporte financiero generado para el usuario {user.user_id} en la finca '{farm.name}'")
        
        return create_response("success", "Reporte financiero generado correctamente", data=jsonable_encoder(report_response))
    
    except Exception as e:
        logger.error(f"Error al generar el reporte financiero: {str(e)}")
        return create_response("error", f"Error al generar el reporte financiero: {str(e)}", status_code=500)
