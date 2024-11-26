# routers/predictions.py
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.orm import Session
from models.models import (
    CulturalWorkTask, HealthCheck, Recommendation,User, Plot, Farm, UserRoleFarm, RolePermission, Permission, Status, StatusType
)
from utils.security import verify_session_token
from dataBase import get_db_session
from utils.response import session_token_invalid_response, create_response
from utils.status import get_status
from datetime import datetime
import io
import base64
from PIL import Image, ImageDraw
import numpy as np
import onnxruntime as ort
import traceback
from utils.FCM import send_fcm_notification
from datetime import datetime
import pytz

colombia_tz = pytz.timezone('America/Bogota')

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modelos de solicitud
class ImageData(BaseModel):
    image_base64: str

class DiseaseDeficiencyDeteccionRequest(BaseModel):
    cultural_work_tasks_id: int = Field(..., description="ID de la tarea de labor cultural")
    images: List[ImageData] = Field(..., description="Lista de imágenes en base64", max_items=10)

class MaturityDeteccionRequest(BaseModel):
    cultural_work_tasks_id: int = Field(..., description="ID de la tarea de labor cultural")
    images: List[ImageData] = Field(..., description="Lista de imágenes en base64", max_items=10)

class AcceptPredictionsRequest(BaseModel):
    prediction_ids: List[int] = Field(..., description="Lista de IDs de predicciones a aceptar")

class UnacceptPredictionsRequest(BaseModel):
    prediction_ids: List[int] = Field(..., description="Lista de IDs de predicciones a desaceptar y eliminar")

class DetectionResponse(BaseModel):
    detection_id: int
    collaborator_name: str
    date: datetime
    result: str
    recommendation: str

class ListDetectionsResponse(BaseModel):
    detections: List[DetectionResponse]
    
class ListDetectionsRequest(BaseModel):
    plot_id: int = Field(..., description="ID del lote (plot) para filtrar las detecciones")

class DeactivatePredictionsRequest(BaseModel):
    prediction_ids: List[int] = Field(..., description="Lista de IDs de predicciones a desactivar")


# Definición del enrutador
router = APIRouter()

# Diccionarios de clases y colores para maduración
class_names_maturity = {0: "Sobremaduro", 1: "Maduro", 2: "Pintón", 3: "Verde"}
class_colors_maturity = {0: (0, 165, 255), 1: (0, 0, 255), 2: (255, 255, 0), 3: (0, 255, 0)}

# Diccionarios de nombres de clases y colores para enfermedades y deficiencias
class_labels_vgg = ['cercospora', 'ferrugem', 'leaf_rust']
class_labels_def = ['hoja_sana', 'nitrogen_N', 'phosphorus_P', 'potassium_K']

class_colors_vgg = {0: (255, 0, 0), 1: (0, 255, 0), 2: (0, 0, 255)}  # Ejemplo de colores
class_colors_def = {0: (0, 255, 0), 1: (255, 0, 0), 2: (0, 0, 255), 3: (255, 255, 0)}  # Ejemplo de colores

# Función para decodificar imágenes en base64
def decode_base64_image(base64_str: str) -> bytes:
    try:
        if base64_str.startswith("data:image/"):
            header, encoded = base64_str.split(",", 1)
            return base64.b64decode(encoded)
        else:
            return base64.b64decode(base64_str)
    except Exception as e:
        logger.error(f"Error decodificando la imagen: {e}")
        raise HTTPException(status_code=400, detail="Imagen en formato base64 inválido.")

# Función de preprocesamiento para modelos de clasificación (.onnx)
def preprocess_image_classification(image: Image.Image, input_size=(224, 224)):
    image = image.resize(input_size)
    image_array = np.array(image).astype('float32') / 255.0  # Normalizar entre 0 y 1
    image_array = np.expand_dims(image_array, axis=0).astype(np.float32)  # Añadir dimensión de batch
    return image_array

# Función de preprocesamiento para modelos de detección (.onnx)
def preprocess_image_Deteccion(image: Image.Image, input_size=(640, 640)):
    img_resized = image.resize(input_size)
    img_array = np.array(img_resized).astype('float32') / 255.0  # Normalizar entre 0 y 1
    img_array = np.transpose(img_array, (2, 0, 1))  # Reordenar canales si es necesario
    img_array = np.expand_dims(img_array, axis=0).astype(np.float32)  # Añadir dimensión de batch
    return img_array

# Funciones para cargar modelos ONNX
def load_onnx_model_disease():
    global session_disease
    if 'session_disease' not in globals():
        try:
            onnx_model_path = 'modelsIA/Modelo-Enfermedades/best.onnx'
            session_disease = ort.InferenceSession(onnx_model_path)
            logger.info("Modelo ONNX de Enfermedades cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error cargando el modelo ONNX de Enfermedades: {e}")
            raise
    return session_disease

def load_onnx_model_deficiency():
    global session_deficiency
    if 'session_deficiency' not in globals():
        try:
            onnx_model_path = 'modelsIA/Modelo-Deficiencias/best.onnx'
            session_deficiency = ort.InferenceSession(onnx_model_path)
            logger.info("Modelo ONNX de Deficiencias cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error cargando el modelo ONNX de Deficiencias: {e}")
            raise
    return session_deficiency

def load_onnx_model_maturity():
    global session_maturity
    if 'session_maturity' not in globals():
        try:
            onnx_model_path = 'modelsIA/Modelo-EstadosMaduracion/best.onnx'
            session_maturity = ort.InferenceSession(onnx_model_path)
            logger.info("Modelo ONNX de Maduración cargado exitosamente.")
        except Exception as e:
            logger.error(f"Error cargando el modelo ONNX de Maduración: {e}")
            raise
    return session_maturity

# Función de Supresión de No-Máximos (NMS) personalizada
def non_max_suppression(boxes, scores, iou_threshold=0.4):
    indices = []
    order = scores.argsort()[::-1]
    
    while order.size > 0:
        i = order[0]
        indices.append(i)
        
        if order.size == 1:
            break
        
        iou = calculate_iou(boxes[i], boxes[order[1:]])
        mask = iou < iou_threshold
        order = order[1:][mask]
    
    return indices

# Función para calcular IoU
def calculate_iou(box, boxes):
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])
    
    intersection = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    area_box = (box[2] - box[0]) * (box[3] - box[1])
    area_boxes = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    
    union = area_box + area_boxes - intersection
    return intersection / union

# Función para obtener el status_id basado en nombre y tipo
def get_status_id(db: Session, status_name: str, status_type_name: str) -> Optional[int]:
    """
    Obtiene el status_id basado en el nombre del estado y el tipo de estado.
    
    Args:
        db (Session): La sesión de base de datos activa.
        status_name (str): El nombre del estado que se desea buscar.
        status_type_name (str): El nombre del tipo de estado asociado.
    
    Returns:
        Optional[int]: El status_id correspondiente o None si no se encuentra.
    """

    status = get_status(db, status_name, status_type_name)
    return status.status_id if status else None

# Endpoint para detección de enfermedades y deficiencias
@router.post("/detection-disease-deficiency")
def detect_disease_deficiency(
    request: DiseaseDeficiencyDeteccionRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Endpoint para la detección de enfermedades y deficiencias en imágenes.

    Este endpoint recibe una solicitud con varias imágenes y utiliza modelos de aprendizaje automático para identificar enfermedades o deficiencias en las plantas.
    
    - **session_token**: Token de sesión para autenticar al usuario.
    - **request**: Objeto que contiene la información de las imágenes y el ID de la tarea de labor cultural asociada.

    **Response**
    - **200**: Retorna una lista de predicciones con el ID de cada predicción, la recomendación y la confianza del modelo.
    - **401**: Token de sesión faltante o inválido.
    - **400**: Error en los estados requeridos o permisos insuficientes.
    - **500**: Error interno del servidor al procesar imágenes o guardar en la base de datos.
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
    
    # 3. Obtener los estados necesarios
    active_task_status = get_status(db, "Por hacer", "Task")
    active_user_status = get_status(db, "Activo", "User")
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    
    if not all([active_task_status, active_user_status, active_urf_status]):
        logger.error("No se encontraron los estados necesarios")
        return create_response("error", "Estados necesarios no encontrados", status_code=400)
    
    # 4. Obtener la tarea de labor cultural
    cultural_work_task = db.query(CulturalWorkTask).filter(
        CulturalWorkTask.cultural_work_tasks_id == request.cultural_work_tasks_id,
        CulturalWorkTask.status_id == active_task_status.status_id
    ).first()
    if not cultural_work_task:
        logger.warning("La tarea de labor cultural con ID %s no existe o no está activa", request.cultural_work_tasks_id)
        return create_response("error", "La tarea de labor cultural no existe o no está activa")
    
    # 5. Obtener el lote y la finca
    plot = db.query(Plot).filter(Plot.plot_id == cultural_work_task.plot_id).first()
    if not plot:
        logger.warning("El lote asociado a la tarea de labor cultural no existe")
        return create_response("error", "El lote asociado a la tarea de labor cultural no existe")
    
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe")
    
    # 6. Verificar que el usuario está asociado a la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm.farm_id)
        return create_response("error", "No tienes permiso para agregar detecciones en esta finca")
    
    # 7. Verificar permiso 'perform_detection' para el usuario
    role_permission_owner = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "perform_detection"
    ).first()
    if not role_permission_owner:
        logger.warning("El rol del usuario no tiene permiso para realizar detecciones")
        return create_response("error", "No tienes permiso para realizar detecciones en esta finca")
    
    # 8. Obtener el status_id de 'Pendiente' del tipo 'Deteccion'
    Pendiente_status_id = get_status_id(db, "Pendiente", "Deteccion")
    if not Pendiente_status_id:
        logger.error("No se encontró el status_id para 'Pendiente' de tipo 'Deteccion'")
        return create_response("error", "Estado predeterminado no configurado en el sistema", status_code=500)
    
    # 9. Cargar los modelos ONNX
    try:
        session_disease = load_onnx_model_disease()
        session_deficiency = load_onnx_model_deficiency()
    except Exception as e:
        logger.error(f"Error al cargar los modelos ONNX: {e}")
        return create_response("error", "Error al cargar los modelos de detección", status_code=500)
    
    # Procesar cada imagen
    response_data = []
    image_number = 1
    for image_data in request.images:
        try:
            # Decodificar la imagen
            image_bytes = decode_base64_image(image_data.image_base64)
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')

            # Preprocesar la imagen para modelo de enfermedades
            processed_image_disease = preprocess_image_classification(image)
            
            # Inferencia con modelo de enfermedades
            inputs_disease = {session_disease.get_inputs()[0].name: processed_image_disease}
            outputs_disease = session_disease.run(None, inputs_disease)
            predictions_disease = outputs_disease[0]
            predicted_class_index_disease = np.argmax(predictions_disease, axis=1)[0]
            confidence_score_disease = float(np.max(predictions_disease, axis=1)[0])
            predicted_class_disease = class_labels_vgg[predicted_class_index_disease]
            
            # Preprocesar la imagen para modelo de deficiencias
            processed_image_deficiency = preprocess_image_classification(image)
            
            # Inferencia con modelo de deficiencias
            inputs_deficiency = {session_deficiency.get_inputs()[0].name: processed_image_deficiency}
            outputs_deficiency = session_deficiency.run(None, inputs_deficiency)
            predictions_deficiency = outputs_deficiency[0]
            predicted_class_index_deficiency = np.argmax(predictions_deficiency, axis=1)[0]
            confidence_score_deficiency = float(np.max(predictions_deficiency, axis=1)[0])
            predicted_class_deficiency = class_labels_def[predicted_class_index_deficiency]
            
            # Seleccionar la predicción con mayor confianza
            if confidence_score_disease > confidence_score_deficiency:
                predicted_class = predicted_class_disease
                confidence_score = confidence_score_disease
                model_used = "Deteccion_disease"
            else:
                predicted_class = predicted_class_deficiency
                confidence_score = confidence_score_deficiency
                model_used = "Deteccion_deficiency"
            
            # Obtener la recomendación
            recommendation = db.query(Recommendation).filter(Recommendation.name == predicted_class).first()
            recommendation_text = recommendation.recommendation if recommendation else "No se encontró una recomendación para esta clase."
            colombia_tz = pytz.timezone('America/Bogota')

            # Obtén la fecha y hora actual en UTC y conviértela a hora de Colombia
            now_in_colombia = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(colombia_tz)

            # Crear una instancia de HealthCheck con estado 'Pendiente'
            new_health_check = HealthCheck(
                check_date=now_in_colombia,
                cultural_work_tasks_id=request.cultural_work_tasks_id,
                recommendation_id=recommendation.recommendation_id if recommendation else None,
                prediction=predicted_class,
                status_id=Pendiente_status_id  # Estado 'Pendiente'
            )
            
            # Agregar a la sesión de la base de datos
            db.add(new_health_check)
            db.flush()  # Obtener el ID sin hacer commit aún
            
            
            PREDICTION_MAPPING = {
    'nitrogen_N': 'Deficiencia de nitrógeno',
    'phosphorus_P': 'Deficiencia de fósforo',
    'potassium_K': 'Deficiencia de potasio',
    'cercospora': 'Cercospora',
    'ferrugem': 'Mancha de hierro',
    'leaf_rust': 'Roya'
}
            mapped_prediction = PREDICTION_MAPPING.get(predicted_class, predicted_class)

            # Agregar al response
            response_data.append({
                "prediction_id": new_health_check.health_checks_id,  # ID de la predicción
                "imagen_numero": image_number,
                "prediccion": mapped_prediction,
                "recomendacion": recommendation_text,
                "modelo_utilizado": model_used,
                "confianza": confidence_score
            })
            image_number += 1
        except Exception as e:
            logger.error(f"Error procesando la imagen {image_number}: {str(e)}")
            logger.debug(traceback.format_exc())
            return create_response("error", f"Error procesando la imagen {image_number}: {str(e)}", status_code=500)
    
    # Commit all HealthChecks
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Error guardando las detecciones en la base de datos: {str(e)}")
        logger.debug(traceback.format_exc())
        db.rollback()
        return create_response("error", "Error guardando las detecciones en la base de datos", status_code=500)
    
    # Responder con el resultado y los IDs de las predicciones
    return create_response("success", "Detecciones procesadas exitosamente", data=response_data, status_code=200)

# Endpoint para detección de maduración
@router.post("/detection-maturity")
def detect_maturity(
    request: MaturityDeteccionRequest,
    session_token: str,

    db: Session = Depends(get_db_session)
):
    """
    Endpoint para detectar el estado de maduración de frutas en imágenes.

    Este endpoint recibe imágenes y utiliza un modelo de aprendizaje automático para determinar el estado de maduración de las frutas y proporcionar recomendaciones.
    
    - **session_token**: Token de sesión para autenticar al usuario.
    - **request**: Objeto que contiene la información de las imágenes y el ID de la tarea de labor cultural asociada.

    **Response**
    - **200**: Retorna una lista de predicciones con el ID de cada predicción, el estado de maduración y la recomendación.
    - **401**: Token de sesión faltante o inválido.
    - **400**: Error en los estados requeridos o permisos insuficientes.
    - **500**: Error interno del servidor al procesar imágenes o guardar en la base de datos.
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
    

    # 3. Obtener los estados necesarios
    active_task_status = get_status(db, "Por hacer", "Task")
    active_user_status = get_status(db, "Activo", "User")
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    
    if not all([active_task_status, active_user_status, active_urf_status]):
        logger.error("No se encontraron los estados necesarios")
        return create_response("error", "Estados necesarios no encontrados", status_code=400)
    
    # 4. Obtener la tarea de labor cultural
    cultural_work_task = db.query(CulturalWorkTask).filter(
        CulturalWorkTask.cultural_work_tasks_id == request.cultural_work_tasks_id,
        CulturalWorkTask.status_id == active_task_status.status_id
    ).first()
    if not cultural_work_task:
        logger.warning("La tarea de labor cultural con ID %s no existe o no está activa", request.cultural_work_tasks_id)
        return create_response("error", "La tarea de labor cultural no existe o no está activa")
    
    # 5. Obtener el lote y la finca
    plot = db.query(Plot).filter(Plot.plot_id == cultural_work_task.plot_id).first()
    if not plot:
        logger.warning("El lote asociado a la tarea de labor cultural no existe")
        return create_response("error", "El lote asociado a la tarea de labor cultural no existe")
    
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe")
    
    # 6. Verificar que el usuario está asociado a la finca
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm.farm_id)
        return create_response("error", "No tienes permiso para agregar detecciones en esta finca")
    
    # 7. Verificar permiso 'perform_detection' para el usuario
    role_permission_owner = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "perform_detection"
    ).first()
    if not role_permission_owner:
        logger.warning("El rol del usuario no tiene permiso para realizar detecciones de maduración")
        return create_response("error", "No tienes permiso para realizar detecciones de maduración en esta finca")
    
    # 8. Obtener el status_id de 'Pendiente' del tipo 'Deteccion'
    Pendiente_status_id = get_status_id(db, "Pendiente", "Deteccion")
    if not Pendiente_status_id:
        logger.error("No se encontró el status_id para 'Pendiente' de tipo 'Deteccion'")
        return create_response("error", "Estado predeterminado no configurado en el sistema", status_code=500)
    
    # 9. Cargar el modelo ONNX de maduración
    try:
        session_maturity = load_onnx_model_maturity()
    except Exception as e:
        logger.error(f"Error al cargar el modelo ONNX de Maduración: {e}")
        return create_response("error", "Error al cargar el modelo de maduración", status_code=500)
    
    # 10. Inicializar contadores globales para las clases
    global_class_count = {class_name: 0 for class_name in class_names_maturity.values()}

    # Lista para almacenar detalles por imagen (opcional)
    response_data = []
    image_number = 1
    for image_data in request.images:
        try:
            # Decodificar la imagen
            image_bytes = decode_base64_image(image_data.image_base64)
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')

            # Preprocesar la imagen para el modelo ONNX de maduración
            img_width, img_height = image.size
            processed_image_maturity = preprocess_image_Deteccion(image)

            # Ejecutar la inferencia con el modelo ONNX
            inputs = {session_maturity.get_inputs()[0].name: processed_image_maturity}
            outputs = session_maturity.run(None, inputs)
            output = outputs[0][0]  # Extraer la salida para una imagen

            # Procesar las detecciones
            Deteccions = []
            class_count = {}
            for Deteccion in output:
                x_center, y_center, width, height, obj_conf = Deteccion[:5]
                class_probs = Deteccion[5:]

                # Calcular confianza total y clase
                confidence = obj_conf * np.max(class_probs)
                class_id = np.argmax(class_probs)

                # Filtrar por umbral de confianza
                if confidence > 0.5:
                    # Escalar las coordenadas a la imagen original
                    x_center_scaled = x_center * img_width / 640
                    y_center_scaled = y_center * img_height / 640
                    width_scaled = width * img_width / 640
                    height_scaled = height * img_height / 640

                    # Convertir a coordenadas de esquina
                    x1 = int(x_center_scaled - width_scaled / 2)
                    y1 = int(y_center_scaled - height_scaled / 2)
                    x2 = int(x_center_scaled + width_scaled / 2)
                    y2 = int(y_center_scaled + height_scaled / 2)

                    # Añadir a la lista de detecciones
                    Deteccions.append([x1, y1, x2, y2, confidence, class_id])

            # Aplicar NMS si hay detecciones
            if Deteccions:
                boxes = np.array([det[:4] for det in Deteccions])
                scores = np.array([det[4] for det in Deteccions])

                # Aplicar la función de NMS manual
                indices = non_max_suppression(boxes, scores, iou_threshold=0.4)

                # Dibujar cajas y contar clases
                draw = ImageDraw.Draw(image)
                for i in indices:
                    x1, y1, x2, y2, _, class_id = Deteccions[i]

                    # Obtener nombre y color de clase
                    class_name = class_names_maturity.get(class_id, "Unknown")
                    color = class_colors_maturity.get(class_id, (255, 0, 0))

                    # Dibujar caja
                    draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
                    draw.text((x1, y1), class_name, fill=color)

                    # Contar clases
                    if class_name in class_count:
                        class_count[class_name] += 1
                        global_class_count[class_name] += 1
                    else:
                        class_count[class_name] = 1
                        global_class_count[class_name] += 1

            # Obtener la predicción final para esta imagen
            if class_count:
                predicted_class_image = max(class_count, key=class_count.get)
            else:
                predicted_class_image = "No hay granos"

            # Ordenar las clases por un orden predefinido de aparición
            ordered_class_names = ["Verde", "Pintón", "Maduro", "Sobremaduro", "No hay granos"]

            # **Corrección: Usar class_count en lugar de global_class_count**
            prediction_text = ', '.join([
                f"{class_name} = {class_count[class_name]}" 
                for class_name in ordered_class_names 
                if class_count.get(class_name, 0) > 0
            ]) or "No hay granos"

            # Obtener la recomendación para esta imagen
            recommendation = db.query(Recommendation).filter(Recommendation.name == predicted_class_image).first()

            if not recommendation:
                logger.error(f"No se encontró una recomendación para la clase '{predicted_class_image}'.")
                raise HTTPException(
                    status_code=500,
                    detail=f"No se encontró una recomendación para la clase '{predicted_class_image}'. Contacta al administrador."
                )

            recommendation_text = recommendation.recommendation
            colombia_tz = pytz.timezone('America/Bogota')

            # Obtén la fecha y hora actual en UTC y conviértela a hora de Colombia
            now_in_colombia = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(colombia_tz)

            # Crear una instancia de HealthCheck con estado 'Pendiente'
            new_health_check = HealthCheck(
                check_date=now_in_colombia,  # Hora en Colombia
                cultural_work_tasks_id=request.cultural_work_tasks_id,
                recommendation_id=recommendation.recommendation_id,  # Garantizado que no es None
                prediction=prediction_text,
                status_id=Pendiente_status_id  # Estado 'Pendiente'
            )

            # Agregar a la sesión de la base de datos
            db.add(new_health_check)
            db.flush()  # Obtener el ID sin hacer commit aún

            # Agregar al response (opcional)
            response_data.append({
                "prediction_id": new_health_check.health_checks_id,  # ID de la predicción
                "imagen_numero": image_number,
                "prediccion": prediction_text,
                "recomendacion": recommendation_text
            })
            image_number += 1

        except Exception as e:
            logger.error(f"Error procesando la imagen {image_number}: {str(e)}")
            logger.debug(traceback.format_exc())
            return create_response("error", f"Error procesando la imagen {image_number}: {str(e)}", status_code=500)
    
    # 11. Determinar la clase con más detecciones globales
    predominant_class = max(global_class_count, key=global_class_count.get) if any(global_class_count.values()) else "Sin detección"
    
    # 12. Obtener la recomendación basada en la clase predominante
    final_recommendation = db.query(Recommendation).filter(Recommendation.name == predominant_class).first()
    final_recommendation_text = final_recommendation.recommendation if final_recommendation else "No se encontró una recomendación para esta clase."
    
    # 13. Crear resumen de las cuentas por clase
    summary = {
        "cuentas_por_clase": global_class_count,
        "recomendacion_final": final_recommendation_text
    }
    
    # Commit all HealthChecks
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Error guardando las detecciones de maduración en la base de datos: {str(e)}")
        logger.debug(traceback.format_exc())
        db.rollback()
        return create_response("error", "Error guardando las detecciones de maduración en la base de datos", status_code=500)
    
    # Preparar la respuesta final
    return create_response(
        "success",
        "Detecciones de maduración procesadas exitosamente",
        data={
            "detalles_por_imagen": response_data  # Opcional: detalles por cada imagen
        },
        status_code=200
    )

# Endpoint para aceptar predicciones
@router.post("/accept-detection")
def accept_predictions(
    request: AcceptPredictionsRequest,
    session_token: str,

    db: Session = Depends(get_db_session)
):
    """
    Acepta las predicciones previamente generadas, actualizándolas a estado 'Aceptado' y
    cambiando el estado de la tarea cultural asociada a 'Terminado'.
    
    - **request.prediction_ids**: Lista de IDs de las predicciones a aceptar.
    - **session_token**: Token de sesión del usuario realizando la acción.
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

    # 3. Validar que prediction_ids no esté vacío
    if not request.prediction_ids:
        logger.warning("No se proporcionaron IDs de predicciones para aceptar")
        return create_response("error", "Lista de IDs de predicciones vacía", status_code=400)

    # 4. Obtener las predicciones de la base de datos
    predictions = db.query(HealthCheck).filter(HealthCheck.health_checks_id.in_(request.prediction_ids)).all()

    # 5. Obtener el status_id para 'Pendiente' del tipo 'Deteccion'
    pendiente_status_id = get_status_id(db, "Pendiente", "Deteccion")
    if not pendiente_status_id:
        logger.error("No se encontró el status_id para 'Pendiente' de tipo 'Deteccion'")
        return create_response("error", "Estado 'Pendiente' no configurado en el sistema", status_code=500)

    # 6. Verificar que todas las predicciones existen y están en estado 'Pendiente'
    if len(predictions) != len(request.prediction_ids):
        logger.warning("Algunas predicciones no existen")
        return create_response("error", "Algunas predicciones no existen", status_code=404)

    for prediction in predictions:
        if prediction.status_id != pendiente_status_id:
            logger.warning(f"La predicción con ID {prediction.health_checks_id} no está en estado 'Pendiente'")
            return create_response("error", f"La predicción con ID {prediction.health_checks_id} no está en estado 'Pendiente'", status_code=400)

    # 7. Obtener el status_id para 'Aceptado' del tipo 'Deteccion'
    accepted_status_id = get_status_id(db, "Aceptado", "Deteccion")
    if not accepted_status_id:
        logger.error("No se encontró el status_id para 'Aceptado' de tipo 'Deteccion'")
        return create_response("error", "Estado 'Aceptado' no configurado en el sistema", status_code=500)

    # 8. Obtener el status_id para 'Terminado' del tipo 'Task'
    terminado_status_id = get_status_id(db, "Terminado", "Task")
    if not terminado_status_id:
        logger.error("No se encontró el status_id para 'Terminado' de tipo 'Task'")
        return create_response("error", "Estado 'Terminado' no configurado en el sistema", status_code=500)

    # 9. Actualizar el estado de las predicciones y las tareas culturales a 'Aceptado' y 'Terminado'
    try:
        # Actualizar HealthCheck status
        for prediction in predictions:
            prediction.status_id = accepted_status_id
            # Si hay acciones adicionales al aceptar, como enviar notificaciones, realizarlas aquí

        # Obtener unique cultural_work_tasks_id
        task_ids = set(pred.cultural_work_tasks_id for pred in predictions)

        # Actualizar CulturalWorkTask status
        for task_id in task_ids:
            cultural_work_task = db.query(CulturalWorkTask).filter(
                CulturalWorkTask.cultural_work_tasks_id == task_id
            ).first()
            if cultural_work_task:
                cultural_work_task.status_id = terminado_status_id
            else:
                logger.warning(f"CulturalWorkTask con ID {task_id} no encontrada")
                return create_response("error", f"Tarea cultural con ID {task_id} no encontrada", status_code=404)

        # Commit both updates
        db.commit()
    except Exception as e:
        logger.error(f"Error actualizando las predicciones o las tareas culturales: {str(e)}")
        logger.debug(traceback.format_exc())
        db.rollback()
        return create_response("error", "Error al aceptar las predicciones y actualizar las tareas culturales", status_code=500)

    return create_response("success", "Predicciones aceptadas y tareas culturales actualizadas exitosamente", status_code=200)



@router.post("/discard-detection")
def unaccept_predictions(
    request: UnacceptPredictionsRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Desacepta y elimina las predicciones previamente aceptadas de la base de datos.
    
    - **request.prediction_ids**: Lista de IDs de las predicciones a desaceptar.
    - **session_token**: Token de sesión del usuario realizando la acción.
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
    
    # 3. Validar que prediction_ids no esté vacío
    if not request.prediction_ids:
        logger.warning("No se proporcionaron IDs de predicciones para desaceptar")
        return create_response("error", "Lista de IDs de predicciones vacía", status_code=400)
    
    # 4. Obtener las predicciones de la base de datos
    predictions = db.query(HealthCheck).filter(HealthCheck.health_checks_id.in_(request.prediction_ids)).all()
    
    # 5. Verificar que todas las predicciones existen y están en estado 'Descartado'
    if len(predictions) != len(request.prediction_ids):
        logger.warning("Algunas predicciones no existen")
        return create_response("error", "Algunas predicciones no existen", status_code=404)
    
    # Obtener el status_id para 'accepted' del tipo 'Deteccion'
    accepted_status_id = get_status_id(db, "Descartado", "Deteccion")
    if not accepted_status_id:
        logger.error("No se encontró el status_id para 'Descartado' de tipo 'Deteccion'")
        return create_response("error", "Estado 'Descartado' no configurado en el sistema", status_code=500)
    
    # 6. Eliminar las predicciones de la base de datos
    try:
        for prediction in predictions:
            db.delete(prediction)
            # Si hay acciones adicionales al eliminar, como enviar notificaciones, realizarlas aquí
        db.commit()
    except Exception as e:
        logger.error(f"Error eliminando las predicciones: {str(e)}")
        logger.debug(traceback.format_exc())
        db.rollback()
        return create_response("error", "Error eliminando las predicciones", status_code=500)
    
    return create_response("success", "Predicciones desaceptadas y eliminadas exitosamente", status_code=200)


@router.post("/list-detections")
def list_detections(
    request: ListDetectionsRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Obtiene las detecciones realizadas en un lote específico con estado 'Aceptado' y tipo 'Deteccion'.
    
    - **request.plot_id**: ID del lote para el cual se listan las detecciones.
    - **session_token**: Token de sesión del usuario que realiza la consulta.
    
    Returns:
        - Lista de detecciones, con el colaborador que realizó la detección, la fecha y la recomendación.
    """
    logger.info("Iniciando la lista de detecciones para plot_id: %s", request.plot_id)
    
    # 1. Verificar el token de sesión
    user = verify_session_token(session_token, db)
    if not user:
        logger.warning("Token de sesión inválido o usuario no encontrado")
        raise HTTPException(status_code=401, detail="Token de sesión inválido")
    
    # 2. Obtener el status_id para 'Aceptado' del tipo 'Deteccion'
    aceptado_status = db.query(Status).join(StatusType).filter(
        Status.name == "Aceptado",
        StatusType.name == "Deteccion"
    ).first()
    
    if not aceptado_status:
        logger.error("No se encontró el status 'Aceptado' del tipo 'Deteccion'")
        return create_response(
            status="error",
            message="Estado 'Aceptado' no configurado en el sistema",
            data=None,
            status_code=500
        )
    
    # 3. Verificar que el lote (plot) existe
    plot = db.query(Plot).filter(Plot.plot_id == request.plot_id).first()
    if not plot:
        logger.warning("El lote con ID %s no existe", request.plot_id)
        return create_response(
            status="error",
            message="El lote especificado no existe",
            data=None,
            status_code=404
        )
    
    # 4. Obtener la finca asociada al lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote con ID %s no existe", plot.farm_id)
        return create_response(
            status="error",
            message="La finca asociada al lote no existe",
            data=None,
            status_code=404
        )
    
    # 5. Obtener el estado 'Activo' para 'user_role_farm'
    active_urf_status = db.query(Status).join(StatusType).filter(
        StatusType.name == "user_role_farm",
        Status.name == "Activo"
    ).first()
    
    if not active_urf_status:
        logger.error("No se encontró el estado 'Activo' para 'user_role_farm'")
        return create_response(
            status="error",
            message="Estado 'Activo' para 'user_role_farm' no configurado en el sistema",
            data=None,
            status_code=500
        )
    
    # 6. Verificar que el usuario está asociado con la finca del lote
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    
    if not user_role_farm:
        logger.warning("El usuario con ID %s no está asociado con la finca con ID %s", user.user_id, farm.farm_id)
        return create_response(
            status="error",
            message="No tienes permiso para acceder a las detecciones de este lote",
            data=None,
            status_code=403
        )
    
    # 7. Verificar permiso 'perform_detection' para el usuario
    role_permission_owner = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "perform_detection"
    ).first()
    
    if not role_permission_owner:
        logger.warning("El rol del usuario no tiene permiso para realizar detecciones")
        return create_response(
            status="error",
            message="No tienes permiso para acceder a las detecciones en este lote",
            data=None,
            status_code=403
        )
    
    # 8. Consultar las detecciones aceptadas para el plot_id especificado con un join para obtener el colaborador
    detections = db.query(
        HealthCheck.health_checks_id,
        HealthCheck.check_date,
        HealthCheck.prediction,
        Recommendation.recommendation,
        User.name.label("collaborator_name")
    ).join(CulturalWorkTask, HealthCheck.cultural_work_tasks_id == CulturalWorkTask.cultural_work_tasks_id)\
     .join(User, CulturalWorkTask.collaborator_user_id == User.user_id)\
     .outerjoin(Recommendation, HealthCheck.recommendation_id == Recommendation.recommendation_id)\
     .filter(
         HealthCheck.status_id == aceptado_status.status_id,
         CulturalWorkTask.plot_id == request.plot_id
     ).all()
    
    logger.info("Número de detecciones encontradas: %s", len(detections))
    
    # 9. Estructurar los datos para la respuesta
    detections_response = []
    for det in detections:
        recommendation_text = det.recommendation if det.recommendation else "No hay recomendación."
        
        detections_response.append({
            "detection_id": det.health_checks_id,
            "collaborator_name": det.collaborator_name,
            "date": det.check_date.isoformat(),
            "result": det.prediction,
            "recommendation": recommendation_text
        })
    
    # 10. Retornar la respuesta usando `create_response`
    return create_response(
        status="success",
        message="Detecciones recuperadas exitosamente",
        data={"detections": detections_response},
        status_code=200
    )

@router.post("/delete-detection")
def deactivate_predictions(
    request: DeactivatePredictionsRequest,
    session_token: str,
    db: Session = Depends(get_db_session)
):
    """
    Desactivar predicciones cambiando su estado a 'Desactivado' para el tipo de estado 'Deteccion'.
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
    
    # 3. Validar que prediction_ids no esté vacío
    if not request.prediction_ids:
        logger.warning("No se proporcionaron IDs de predicciones para desactivar")
        return create_response("error", "Lista de IDs de predicciones vacía", status_code=400)
    
    # 4. Obtener las predicciones de la base de datos
    predictions = db.query(HealthCheck).filter(HealthCheck.health_checks_id.in_(request.prediction_ids)).all()
    
    # 5. Verificar que todas las predicciones existen
    if len(predictions) != len(request.prediction_ids):
        logger.warning("Algunas predicciones no existen")
        return create_response("error", "Algunas predicciones no existen", status_code=404)
    
    # 6. Obtener el status_id para 'Desactivado' del tipo 'Deteccion'
    desactivado_status_id = get_status_id(db, "Desactivado", "Deteccion")
    if not desactivado_status_id:
        logger.error("No se encontró el status_id para 'Desactivado' de tipo 'Deteccion'")
        return create_response("error", "Estado 'Desactivado' no configurado en el sistema", status_code=500)
    
    # 7. Actualizar el estado de las predicciones a 'Desactivado'
    try:
        for prediction in predictions:
            prediction.status_id = desactivado_status_id
            # Si hay acciones adicionales al desactivar, como enviar notificaciones, realizarlas aquí
        db.commit()
    except Exception as e:
        logger.error(f"Error actualizando el estado de las predicciones: {str(e)}")
        logger.debug(traceback.format_exc())
        db.rollback()
        return create_response("error", "Error al desactivar las predicciones", status_code=500)
    
    return create_response("success", "Predicciones desactivadas exitosamente", status_code=200)