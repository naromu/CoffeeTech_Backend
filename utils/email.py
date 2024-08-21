import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
load_dotenv()

def send_verification_email(email, token):
    

    
    #smtp_user = 'coffeetech361@zohomail.com'
    #smtp_pass = 'CoffeTech123' # Usa la contraseña de aplicación si tienes 2FA habilitado
    
    smtp_user = os.getenv("SMTPP_USER")
    smtp_pass = os.getenv("SMTPP_PASS")

    if not smtp_user or not smtp_pass:
        print("Error: Las credenciales SMTP no están configuradas correctamente.")
        return
 # Usa la contraseña de aplicación si tienes 2FA habilitado

    smtp_host = "smtp.zoho.com"
    smtp_port = 465  # Usar SSL en el puerto 465

    # Crear el mensaje de correo electrónico
    subject = "Prueba de correo"
    body = f"Hola {token}"

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = email  # Aquí debe ser una cadena, no un conjunto

    try:
        # Conectar al servidor SMTP de Zoho usando SSL
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, email, msg.as_string())
            print("Correo enviado exitosamente")
    except Exception as e:
        print(f"Error al enviar correo: {e}")
