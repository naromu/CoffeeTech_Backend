
import os
import json
import firebase_admin
from firebase_admin import credentials, messaging
from dotenv import load_dotenv
import tempfile

# Cargar las variables de entorno
load_dotenv()

# Crear un diccionario con las credenciales desde las variables de entorno
firebase_credentials = {
    "type": os.getenv("TYPE"),
    "project_id": os.getenv("PROJECT_ID"),
    "private_key_id": os.getenv("PRIVATE_KEY_ID"),
    "private_key": os.getenv("PRIVATE_KEY").replace("\\n", "\n"),  # Asegurarse de tener saltos de línea correctos
    "client_email": os.getenv("CLIENT_EMAIL"),
    "client_id": os.getenv("CLIENT_ID"),
    "auth_uri": os.getenv("AUTH_URI"),
    "token_uri": os.getenv("TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("AUTH_PROVIDER_X509_CERT_URL"),
    "client_x509_cert_url": os.getenv("CLIENT_X509_CERT_URL"),
    "universe_domain":os.getenv("googleapis.com")
}

# Crear un archivo temporal con las credenciales
with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_json_file:
    json.dump(firebase_credentials, temp_json_file)
    temp_json_file_name = temp_json_file.name

# Inicializar Firebase con el archivo JSON temporal
if not firebase_admin._apps:  # Evitar inicializar Firebase múltiples veces
    cred = credentials.Certificate(temp_json_file_name)
    firebase_admin.initialize_app(cred)




def send_fcm_notification(fcm_token: str, title: str, body: str):
    """
    Envía una notificación utilizando Firebase Cloud Messaging (FCM).

    Args:
        fcm_token (str): El token de registro FCM del dispositivo al que se enviará la notificación.
        title (str): El título de la notificación.
        body (str): El cuerpo del mensaje de la notificación.

    Raises:
        Exception: Si hay un error al enviar la notificación.
    """
    # Construir el mensaje
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=fcm_token,
    )


    # Enviar la notificación
    try:
        response = messaging.send(message)
        print('Notificación enviada correctamente:', response)
    except Exception as e:
        print('Error enviando la notificación:', str(e))
