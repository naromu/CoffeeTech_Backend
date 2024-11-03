import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from PIL import Image
import io
import base64
import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, models
from tensorflow.keras.applications.vgg16 import preprocess_input as preprocess_input_vgg
from tensorflow.keras.applications.mobilenet import preprocess_input as preprocess_input_mobilenet
import onnxruntime as ort
import traceback
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



# Definición del enrutador
router = APIRouter()


class CreateHistorialDeteccionRequest(BaseModel):
    user_id: int = Field(..., description="ID del usuario que realiza la detección")
    plot_id: int = Field(..., description="ID del lote asociado a la detección")
    farm_id: int = Field(..., description="ID de la finca asociada a la detección")
    fecha: Optional[datetime] = Field(default_factory=datetime.utcnow, description="Fecha de la detección (por defecto, la fecha actual)")

# Clase para recibir datos de imagen en formato base64
class ImageData(BaseModel):
    image_base64: str

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

# Preprocesamiento de imagen para el modelo VGG
def preprocess_image_vgg(image: Image.Image):
    image = image.resize((224, 224))
    image_array = np.array(image)
    image_array = preprocess_input_vgg(image_array)
    image_array = np.expand_dims(image_array, axis=0)
    return image_array

# Preprocesamiento de imagen para el modelo de deficiencias
def preprocess_image_def(image: Image.Image):
    image = image.resize((224, 224))
    image_array = np.array(image)
    image_array = preprocess_input_mobilenet(image_array)
    image_array = np.expand_dims(image_array, axis=0)
    return image_array

# Función para decodificar imagen base64
def decode_base64_image(base64_str: str) -> bytes:
    if base64_str.startswith("data:image/"):
        header, encoded = base64_str.split(",", 1)
        return base64.b64decode(encoded)
    else:
        return base64.b64decode(base64_str)
    
@router.post("/detectdisease_and_deficiency")
def CreateHistorialDeteccionRequest(
    request: CreateHistorialDeteccionRequest,
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
    
    # 3. Obtener los estados necesarios
    active_plot_status = get_status(db, "Activo", "Plot")
  
    active_user_status = get_status(db, "Activo", "User")
    active_urf_status = get_status(db, "Activo", "user_role_farm")
    
    if not all([active_plot_status, task_terminated_status, pending_task_status, active_user_status, active_urf_status]):
        logger.error("No se encontraron los estados necesarios")
        return create_response("error", "Estados necesarios no encontrados", status_code=400)
    
    # 4. Obtener el lote
    plot = db.query(Plot).filter(
        Plot.plot_id == request.plot_id,
        Plot.status_id == active_plot_status.status_id
    ).first()
    if not plot:
        logger.warning("El lote con ID %s no existe o no está activo", request.plot_id)
        return create_response("error", "El lote no existe o no está activo")
    
    # 5. Verificar que el usuario propietario está asociado a la finca del lote
    farm = db.query(Farm).filter(Farm.farm_id == plot.farm_id).first()
    if not farm:
        logger.warning("La finca asociada al lote no existe")
        return create_response("error", "La finca asociada al lote no existe")
    
    user_role_farm = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == user.user_id,
        UserRoleFarm.farm_id == farm.farm_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()
    if not user_role_farm:
        logger.warning("El usuario no está asociado con la finca con ID %s", farm.farm_id)
        return create_response("error", "No tienes permiso para agregar una tarea en esta finca")
    
    # 6. Verificar permiso 'add_cultural_work_task' para el propietario
    role_permission_owner = db.query(RolePermission).join(Permission).filter(
        RolePermission.role_id == user_role_farm.role_id,
        Permission.name == "perform_detection"
    ).first()
    if not role_permission_owner:
        logger.warning("El rol del usuario no tiene permiso para agregar una tarea de labor cultural")
        return create_response("error", "No tienes permiso para agregar una tarea de labor cultural en esta finca")
    
    # 7.1 Buscar el ID de la labor cultural a partir de su nombre
    cultural_work = db.query(CulturalWork).filter(CulturalWork.name == request.cultural_works_name).first()
    if not cultural_work:
        logger.warning("La labor cultural con nombre %s no existe", request.cultural_works_name)
        return create_response("error", "La labor cultural especificada no existe")
    
    
    # 7.2 Verificar que el colaborador está activo

    # Log para verificar el valor de request.collaborator_user_id
    logger.info("Valor de request.collaborator_user_id: %s", request.collaborator_user_id)

    # Log para verificar el valor de active_urf_status.status_id
    logger.info("Valor de active_urf_status.status_id: %s", active_urf_status.status_id)

    # Ejecutar la consulta del colaborador
    collaborator = db.query(UserRoleFarm).filter(
        UserRoleFarm.user_id == request.collaborator_user_id,
        UserRoleFarm.status_id == active_urf_status.status_id
    ).first()

    # Log para verificar si se encontró el colaborador
    if collaborator:
        logger.info("Colaborador encontrado: %s", collaborator)
    else:
        logger.warning("El colaborador con ID %s no existe o no está activo", request.collaborator_user_id)

    # Si no se encuentra el colaborador, retornar la respuesta
    if not collaborator:
        return create_response("error", "El colaborador no existe en la finca")
        
   
    
    
    #######################
async def predict_combined(image_data: ImageData, db_session: Session):
    try:
        image_bytes = decode_base64_image(image_data.image_base64)
        image = Image.open(io.BytesIO(image_bytes))

        # Procesar la imagen con el modelo de enfermedades
        processed_image_vgg = preprocess_image_vgg(image)
        predictions_vgg = loaded_model_vgg.predict(processed_image_vgg)
        predictions_array_vgg = predictions_vgg['output_0']
        predicted_class_index_vgg = np.argmax(predictions_array_vgg, axis=1)[0]
        confidence_score_vgg = float(np.max(predictions_array_vgg))
        class_labels_vgg = ['cercospora', 'ferrugem', 'leaf_rust']
        predicted_class_vgg = class_labels_vgg[predicted_class_index_vgg]

        # Procesar la imagen con el modelo de deficiencias
        processed_image_def = preprocess_image_def(image)
        predictions_def = loaded_model_def.predict(processed_image_def)
        predictions_array_def = predictions_def['output_0']
        predicted_class_index_def = np.argmax(predictions_array_def, axis=1)[0]
        confidence_score_def = float(np.max(predictions_array_def))
        class_labels_def = ['hoja_sana', 'nitrogen_N', 'phosphorus_P', 'potassium_K']
        predicted_class_def = class_labels_def[predicted_class_index_def]

        # Comparar las confianzas y seleccionar la predicción más confiable
        if confidence_score_vgg > confidence_score_def:
            predicted_class = predicted_class_vgg
            confidence_score = confidence_score_vgg
        else:
            predicted_class = predicted_class_def
            confidence_score = confidence_score_def

        # Consultar la recomendación en la base de datos
        recommendation_query = select(Recommendation.recommendation).where(Recommendation.name == predicted_class)
        recommendation_result = db_session.execute(recommendation_query).scalar_one_or_none()

        # Si se encuentra una recomendación, incluirla en la respuesta
        if recommendation_result:
            recommendation_text = recommendation_result
        else:
            recommendation_text = "No se encontró una recomendación para esta clase."

        return {
            "model": "detection_vgg" if confidence_score_vgg > confidence_score_def else "detection_def",
            "predicted_class": predicted_class,
            "confidence_score": confidence_score,
            "recommendation": recommendation_text
        }

    except Exception as e:
        error_trace = traceback.format_exc()
        print(error_trace)
        raise HTTPException(status_code=500, detail=f"Error procesando la imagen: {str(e)}")

# # Endpoint para detección de enfermedades usando VGG
# @router.post("/detection_vgg")
# async def predict_vgg(image_data: ImageData):
#     try:
#         # Decodificar la imagen de base64
#         image_bytes = decode_base64_image(image_data.image_base64)

#         # Cargar la imagen y preprocesarla
#         image = Image.open(io.BytesIO(image_bytes))
#         processed_image = preprocess_image_vgg(image)

#         # Realizar la predicción
#         predictions_vgg = loaded_model_vgg.predict(processed_image)
#         predictions_array_vgg = predictions_vgg['output_0']

#         # Determinar la clase y la confianza
#         predicted_class_index_vgg = np.argmax(predictions_array_vgg, axis=1)[0]
#         confidence_score_vgg = float(np.max(predictions_array_vgg)) if predictions_array_vgg.size > 0 else 0.0
#         class_labels_vgg = ['cercospora', 'ferrugem', 'leaf_rust']
#         predicted_class_vgg = class_labels_vgg[predicted_class_index_vgg]

#         return {
#             "predicted_class": predicted_class_vgg,
#             "confidence_score": confidence_score_vgg
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# # Endpoint para detección de deficiencias
# @router.post("/detection")
# async def predict_def(image_data: ImageData):
#     try:
#         # Decodificar la imagen de base64
#         image_bytes = decode_base64_image(image_data.image_base64)

#         # Cargar la imagen y preprocesarla
#         image = Image.open(io.BytesIO(image_bytes))
#         processed_image = preprocess_image_def(image)

#         # Realizar la predicción
#         predictions_def = loaded_model_def.predict(processed_image)
#         predictions_array_def = predictions_def['output_0']

#         # Determinar la clase y la confianza
#         predicted_class_index_def = np.argmax(predictions_array_def, axis=1)[0]
#         confidence_score = float(np.max(predictions_array_def))
#         class_labels_def = ['hoja_sana', 'nitrogen_N', 'phosphorus_P', 'potassium_K']
#         predicted_class_def = class_labels_def[predicted_class_index_def]

#         return {
#             "predicted_class": predicted_class_def,
#             "confidence_score": confidence_score
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# Preprocesamiento de imagen para el modelo ONNX
def preprocess_image(image: Image.Image):
    img = image.resize((640, 640)).convert('RGB')
    img = np.array(img).astype('float32') / 255.0
    img = np.transpose(img, (2, 0, 1))[np.newaxis, ...]
    return img

# Endpoint para detección de maduración
@router.post("/deteccionmaduracion")

async def detect_image(data: ImageData):
    try:
        # Decodificar la imagen
        if data.image_base64.startswith("data:image/"):
            header, encoded = data.image_base64.split(",", 1)
            image_bytes = base64.b64decode(encoded)
        else:
            image_bytes = base64.b64decode(data.image_base64)

        image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        preprocessed_image = preprocess_image(image)

        # Realizar predicción con el modelo ONNX
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: preprocessed_image})

        # Extraer la salida y revisar la forma
        outputs_array = outputs[0]
        print(f"Forma de outputs_array antes de cualquier reducción: {outputs_array.shape}")

        # Verificar si outputs_array tiene la forma esperada para detección
        if len(outputs_array.shape) == 3 and outputs_array.shape[2] == 9:
            # Seleccionar las detecciones con confianza alta (por ejemplo, >0.5)
            detection_threshold = 0.5
            detections = outputs_array[0]  # Remover la dimensión inicial de batch
            high_confidence_detections = [
                detection for detection in detections if detection[4] > detection_threshold
            ]

            if not high_confidence_detections:
                raise ValueError("No se encontraron detecciones con confianza suficiente.")

            # Obtener la detección con la mayor confianza
            best_detection = max(high_confidence_detections, key=lambda x: x[4])
            detected_class_index = int(np.argmax(best_detection[5:]))  # Índice de la clase
            confidence = float(best_detection[4])

            # Validar el índice
            if detected_class_index not in range(len(class_names)):
                raise ValueError(f"Índice de clase detectada fuera de rango: {detected_class_index}")

            # Devolver la clase, la confianza y la imagen procesada en formato base64
            buffered = io.BytesIO()
            image.save(buffered, format="PNG")  # Cambia el formato según sea necesario
            image_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')

            result = {
                "class": class_names[detected_class_index],
                "confidence": confidence,
                "processed_image": f"data:image/png;base64,{image_base64}"
            }
            return result
        else:
            raise ValueError(f"Salida del modelo no coincide con la forma esperada para detección.")

    except Exception as e:
        # Registro detallado del error
        error_trace = traceback.format_exc()
        print(error_trace)
        raise HTTPException(status_code=500, detail=f"Error procesando la imagen: {str(e)}")
    
    
# @router.post("/test_decoding")
# async def test_decoding(image_data: ImageData):
#     try:
#         image_bytes = base64.b64decode(image_data.image_base64)
#         return {"message": "Imagen decodificada correctamente"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


