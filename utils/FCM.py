import os
import firebase_admin
from firebase_admin import credentials, messaging

# Ruta al archivo JSON de credenciales (asegúrate de que la ruta es correcta)
cred_path = os.path.join(os.getcwd(), 'coffeetech-c5cb7-7edbb325ca73.json')

# Inicializa Firebase con las credenciales de la cuenta de servicio
if not firebase_admin._apps:  # Evita inicializar Firebase múltiples veces
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

def send_fcm_notification(fcm_token: str, title: str, body: str):
    # Construye el mensaje
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=fcm_token,
    )

    # Envía la notificación
    try:
        response = messaging.send(message)
        print('Notificación enviada correctamente:', response)
    except Exception as e:
        print('Error enviando la notificación:', str(e))
