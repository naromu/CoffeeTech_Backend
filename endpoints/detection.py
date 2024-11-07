import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image, ImageDraw, ImageFont
from PIL import Image as PILImage, ImageDraw
import io
import base64
import numpy as np
import tensorflow as tf
from keras import layers, models
from keras.applications.vgg16 import preprocess_input as preprocess_input_vgg
from keras.applications.mobilenet import preprocess_input as preprocess_input_mobilenet
import onnxruntime as ort
import traceback
import cv2 
import torch
from models.models import *
#########################################
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from models.models import (
    Farm, Plot, CulturalWork, CulturalWorkTask, User, Status, RolePermission, Permission, UserRoleFarm,Notification, NotificationType, Recommendation
)
from utils.security import verify_session_token
from dataBase import get_db_session
import logging
from typing import Optional
from utils.response import session_token_invalid_response, create_response
from utils.status import get_status
from datetime import datetime, date
from utils.FCM import send_fcm_notification
import pytz
from typing import List
from sqlalchemy.orm import Session
from models.models import HealthCheck
from datetime import datetime



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Definir el modelo de datos para las imágenes
class ImageData(BaseModel):
    image_base64: str

# Definir el modelo de solicitud para detección de enfermedades y deficiencias
class DiseaseDeficiencyDetectionRequest(BaseModel):
    session_token: str = Field(..., description="Token de sesión del usuario")
    cultural_work_tasks_id: int = Field(..., description="ID de la tarea de labor cultural")
    images: List[ImageData] = Field(..., description="Lista de imágenes en base64", max_items=10)

# Definir el modelo de solicitud para detección de maduración
class MaturityDetectionRequest(BaseModel):
    session_token: str = Field(..., description="Token de sesión del usuario")
    cultural_work_tasks_id: int = Field(..., description="ID de la tarea de labor cultural")
    images: List[ImageData] = Field(..., description="Lista de imágenes en base64", max_items=10)


# Definición del enrutador
router = APIRouter()

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


# Función de preprocesamiento para el modelo VGG (Enfermedades)
def preprocess_image_vgg(image: Image.Image):
    image = image.resize((224, 224))
    image_array = np.array(image)
    image_array = preprocess_input_vgg(image_array)
    image_array = np.expand_dims(image_array, axis=0)
    return image_array


# Función de preprocesamiento para el modelo de Deficiencias
def preprocess_image_def(image: Image.Image):
    image = image.resize((224, 224))
    image_array = np.array(image)
    image_array = preprocess_input_mobilenet(image_array)
    image_array = np.expand_dims(image_array, axis=0)
    return image_array

# Cargar el modelo VGG para detección de enfermedades
saved_model_path_vgg = "modelsIA/Modelo-Enfermedades"
loaded_model_layer_vgg = layers.TFSMLayer(saved_model_path_vgg, call_endpoint='serving_default')
inputs_vgg = tf.keras.Input(shape=(224, 224, 3))
outputs_vgg = loaded_model_layer_vgg(inputs_vgg)
loaded_model_vgg = models.Model(inputs=inputs_vgg, outputs=outputs_vgg)

# Cargar el modelo de deficiencias
saved_model_path_def = "modelsIA/Modelo-Deficiencias"
loaded_model_layer_def = layers.TFSMLayer(saved_model_path_def, call_endpoint='serving_default')
inputs_def = tf.keras.Input(shape=(224, 224, 3))
outputs_def = loaded_model_layer_def(inputs_def)
loaded_model_def = models.Model(inputs=inputs_def, outputs=outputs_def)

# Cargar el modelo ONNX para detección de maduración
onnx_model_path = 'modelsIA/Modelo-EstadosMaduracion/best.onnx'
session = ort.InferenceSession(onnx_model_path)

# Diccionario de nombres de clases y colores
class_names = {0: "overripe", 1: "ripe", 2: "semi_ripe", 3: "unripe"}
class_colors = {0: (0, 165, 255), 1: (0, 0, 255), 2: (255, 255, 0), 3: (0, 255, 0)}



@router.post("/detectdisease_and_deficiency")
def detect_disease_deficiency(
    request: DiseaseDeficiencyDetectionRequest,
    db: Session = Depends(get_db_session)
):
    """
    Crear un historial de detección de enfermedades y deficiencias para múltiples imágenes.
    """
    # 1. Verificar que el session_token esté presente
    if not request.session_token:
        logger.warning("No se proporcionó el token de sesión en la solicitud")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # 2. Verificar el token de sesión
    user = verify_session_token(request.session_token, db)
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
    
    # 8. Procesar cada imagen
    response_data = []
    image_number = 1
    for image_data in request.images:
        try:
            # Decodificar la imagen
            image_bytes = decode_base64_image(image_data.image_base64)
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')

            # Procesar con modelo de enfermedades
            processed_image_vgg = preprocess_image_vgg(image)
            predictions_vgg = loaded_model_vgg.predict(processed_image_vgg)
            predictions_array_vgg = predictions_vgg['output_0']
            predicted_class_index_vgg = np.argmax(predictions_array_vgg, axis=1)[0]
            confidence_score_vgg = float(np.max(predictions_array_vgg))
            class_labels_vgg = ['cercospora', 'ferrugem', 'leaf_rust']
            predicted_class_vgg = class_labels_vgg[predicted_class_index_vgg]

            # Procesar con modelo de deficiencias
            processed_image_def = preprocess_image_def(image)
            predictions_def = loaded_model_def.predict(processed_image_def)
            predictions_array_def = predictions_def['output_0']
            predicted_class_index_def = np.argmax(predictions_array_def, axis=1)[0]
            confidence_score_def = float(np.max(predictions_array_def))
            class_labels_def = ['hoja_sana', 'nitrogen_N', 'phosphorus_P', 'potassium_K']
            predicted_class_def = class_labels_def[predicted_class_index_def]

            # Seleccionar la predicción con mayor confianza
            if confidence_score_vgg > confidence_score_def:
                predicted_class = predicted_class_vgg
                confidence_score = confidence_score_vgg
                model_used = "detection_vgg"
            else:
                predicted_class = predicted_class_def
                confidence_score = confidence_score_def
                model_used = "detection_def"

            # Obtener la recomendación
            recommendation = db.query(Recommendation).filter(Recommendation.name == predicted_class).first()
            recommendation_text = recommendation.recommendation if recommendation else "No se encontró una recomendación para esta clase."

            # Crear una instancia de HealthCheck
            new_health_check = HealthCheck(
                check_date=datetime.utcnow(),
                cultural_work_tasks_id=request.cultural_work_tasks_id,
                recommendation_id=recommendation.recommendation_id if recommendation else None,
                prediction=predicted_class
                # plot_id no se asigna ya que no existe en el modelo original
            )

            # Agregar a la sesión de la base de datos
            db.add(new_health_check)

            # Agregar al response
            response_data.append({
                "imagen_numero": image_number,
                "prediccion": predicted_class,
                "recomendacion": recommendation_text
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

    # Responder con el resultado
    return create_response("success", "Detecciones procesadas exitosamente", data=response_data, status_code=200)


@router.post("/deteccionmaduracion")
def detect_maturity(
    request: MaturityDetectionRequest,
    db: Session = Depends(get_db_session)
):
    """
    Detectar el estado de maduración de frutas en múltiples imágenes y proporcionar recomendaciones basadas en las detecciones.
    """
    # 1. Verificar que el session_token esté presente
    if not request.session_token:
        logger.warning("No se proporcionó el token de sesión en la solicitud")
        return create_response("error", "Token de sesión faltante", status_code=401)
    
    # 2. Verificar el token de sesión
    user = verify_session_token(request.session_token, db)
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
    
    # 8. Inicializar contadores globales para las clases
    global_class_count = {class_name: 0 for class_name in class_names.values()}
    
    # Lista para almacenar detalles por imagen (opcional)
    response_data = []
    image_number = 1
    for image_data in request.images:
        try:
            # Decodificar la imagen
            image_bytes = decode_base64_image(image_data.image_base64)
            image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    
            # Preprocesar la imagen para el modelo ONNX
            img_width, img_height = image.size
            img_resized = image.resize((640, 640))
            img_array = np.array(img_resized).astype('float32') / 255.0
            img_array = np.transpose(img_array, (2, 0, 1))[np.newaxis, ...]
    
            # Ejecutar la inferencia con el modelo ONNX
            outputs = session.run(None, {'images': img_array})
            output = outputs[0][0]  # Extraer la salida para una imagen
    
            # Procesar las detecciones
            detections = []
            class_count = {}
            for detection in output:
                x_center, y_center, width, height, obj_conf = detection[:5]
                class_probs = detection[5:]
    
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
                    detections.append([x1, y1, x2, y2, confidence, class_id])
    
            # Aplicar NMS si hay detecciones
            if detections:
                boxes = torch.tensor([det[:4] for det in detections], dtype=torch.float32)
                scores = torch.tensor([det[4] for det in detections], dtype=torch.float32)
    
                # Aplicar la función de NMS manual
                indices = non_max_suppression(boxes, scores, iou_threshold=0.4)
    
                # Dibujar cajas y contar clases
                draw = ImageDraw.Draw(image)
                for i in indices:
                    x1, y1, x2, y2, _, class_id = detections[i]
    
                    # Obtener nombre y color de clase
                    class_name = class_names.get(class_id, "Unknown")
                    color = class_colors.get(class_id, (255, 0, 0))
    
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
    
            # Obtener la predicción final para esta imagen (opcional)
            if class_count:
                predicted_class_image = max(class_count, key=class_count.get)
            else:
                predicted_class_image = "Sin detección"
    
            # Obtener la recomendación para esta imagen (opcional)
            recommendation = db.query(Recommendation).filter(Recommendation.name == predicted_class_image).first()
            recommendation_text = recommendation.recommendation if recommendation else "No se encontró una recomendación para esta clase."
    


            # Crear una instancia de HealthCheck
            new_health_check = HealthCheck(
                check_date=datetime.utcnow(),
                cultural_work_tasks_id=request.cultural_work_tasks_id,
                recommendation_id=recommendation.recommendation_id if recommendation else None,
                prediction=predicted_class_image
                # plot_id no se asigna ya que no existe en el modelo original
            )
    
            # Agregar a la sesión de la base de datos
            db.add(new_health_check)
            

            # Agregar al response (opcional)
            response_data.append({
                "imagen_numero": image_number,
                "prediccion": predicted_class_image,
                "recomendacion": recommendation_text
            })
            image_number += 1
        except Exception as e:
            logger.error(f"Error procesando la imagen {image_number}: {str(e)}")
            logger.debug(traceback.format_exc())
            return create_response("error", f"Error procesando la imagen {image_number}: {str(e)}", status_code=500)
    
    # 9. Determinar la clase con más detecciones globales
    predominant_class = max(global_class_count, key=global_class_count.get) if any(global_class_count.values()) else "Sin detección"
    
    # 10. Obtener la recomendación basada en la clase predominante
    final_recommendation = db.query(Recommendation).filter(Recommendation.name == predominant_class).first()
    final_recommendation_text = final_recommendation.recommendation if final_recommendation else "No se encontró una recomendación para esta clase."
    
    # 11. Crear resumen de las cuentas por clase
    summary = {
        "cuentas_por_clase": global_class_count,
        "recomendacion_final": final_recommendation_text
    }
    
    # 12. Commit all HealthChecks
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Error guardando las detecciones de maduración en la base de datos: {str(e)}")
        logger.debug(traceback.format_exc())
        db.rollback()
        return create_response("error", "Error guardando las detecciones de maduración en la base de datos", status_code=500)
    
    # 13. Preparar la respuesta final
    return create_response(
        "success",
        "Detecciones de maduración procesadas exitosamente",
        data={
            "detalles_por_imagen": response_data,  # Opcional: detalles por cada imagen
            "resumen": summary
        },
        status_code=200
    )



# Función de Supresión de No-Máximos (NMS) personalizada
def non_max_suppression(boxes, scores, iou_threshold=0.4):
    indices = []
    order = scores.argsort(descending=True)
    
    while order.numel() > 0:
        i = order[0].item()
        indices.append(i)
        
        if order.numel() == 1:
            break
        
        iou = calculate_iou(boxes[i], boxes[order[1:]])
        mask = iou < iou_threshold
        order = order[1:][mask]
    
    return indices

# Función para calcular IoU
def calculate_iou(box, boxes):
    x1 = torch.max(box[0], boxes[:, 0])
    y1 = torch.max(box[1], boxes[:, 1])
    x2 = torch.min(box[2], boxes[:, 2])
    y2 = torch.min(box[3], boxes[:, 3])
    
    intersection = torch.clamp(x2 - x1, min=0) * torch.clamp(y2 - y1, min=0)
    area_box = (box[2] - box[0]) * (box[3] - box[1])
    area_boxes = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    
    union = area_box + area_boxes - intersection
    return intersection / union

# Diccionario de nombres de clases y colores para maduración
class_names = {0: "overripe", 1: "ripe", 2: "semi_ripe", 3: "unripe"}
class_colors = {0: (0, 165, 255), 1: (0, 0, 255), 2: (255, 255, 0), 3: (0, 255, 0)}

