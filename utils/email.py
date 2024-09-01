import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def send_email(email, token, email_type):
    """
    Envía un correo electrónico basado en el tipo especificado.

    :param email: Dirección de correo electrónico del destinatario.
    :param token: Token a incluir en el cuerpo del correo electrónico.
    :param email_type: Tipo de correo a enviar ('verification' o 'reset').
    """
    smtp_user = os.getenv("SMTPP_USER")
    smtp_pass = os.getenv("SMTPP_PASS")

    if not smtp_user or not smtp_pass:
        print("Error: Las credenciales SMTP no están configuradas correctamente.")
        return

    smtp_host = "smtp.zoho.com"
    smtp_port = 465  # Usar SSL en el puerto 465

    # URL pública del logo (reemplázala con la URL correcta de tu logo)
    logo_url = "https://raw.githubusercontent.com/naromu/CoffeeTech_Backend/develop/assets/logo.jpeg"  # Cambia esto a la URL de tu logo

    # Definir el asunto y el cuerpo del correo basado en el tipo de correo
    if email_type == 'verification':
        subject = "Verificación de Correo Electrónico"
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background-color: #f7f7f7;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    width: 100%;
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    text-align: center;
                    padding-bottom: 20px;
                }}
                .logo {{
                    max-width: 150px;
                    height: auto;
                    margin-bottom: 20px;
                }}
                .content {{
                    text-align: center;
                }}
                .token-box {{
                    background-color: #f2f2f2;
                    padding: 10px;
                    border-radius: 5px;
                    display: inline-block;
                    margin: 20px 0;
                    font-size: 18px;
                    font-weight: bold;
                }}
                .footer {{
                    margin-top: 30px;
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="{logo_url}" alt="Logo de CoffeTech" class="logo">
                    <h2>Hola,</h2>
                </div>
                <div class="content">
                    <p>Gracias por registrarte en Coffeetech. Por favor, verifica tu dirección de correo electrónico usando el siguiente código:</p>
                    <div class="token-box" id="token">{token}</div>
                    <p>Por favor, copia el código anterior para verificar tu cuenta.</p>
                </div>
                <div class="footer">
                    <p>Gracias,<br/>El equipo de CoffeTech</p>
                </div>
            </div>
        </body>
        </html>
        """
    elif email_type == 'reset':
        subject = "Restablecimiento de Contraseña"
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background-color: #f7f7f7;
                    margin: 0;
                    padding: 0;
                }}
                .container {{
                    width: 100%;
                    max-width: 600px;
                    margin: 0 auto;
                    background-color: #ffffff;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
                }}
                .header {{
                    text-align: center;
                    padding-bottom: 20px;
                }}
                .logo {{
                    max-width: 150px;
                    height: auto;
                    margin-bottom: 20px;
                }}
                .content {{
                    text-align: center;
                }}
                .token-box {{
                    background-color: #f2f2f2;
                    padding: 10px;
                    border-radius: 5px;
                    display: inline-block;
                    margin: 20px 0;
                    font-size: 18px;
                    font-weight: bold;
                }}
                .footer {{
                    margin-top: 30px;
                    text-align: center;
                    font-size: 12px;
                    color: #777;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <img src="{logo_url}" alt="Logo de CoffeTech" class="logo">
                    <h2>Hola,</h2>
                </div>
                <div class="content">
                    <p>Hemos recibido una solicitud para restablecer tu contraseña. Utiliza el siguiente código para continuar:</p>
                    <div class="token-box" id="token">{token}</div>
                    <p>Por favor, copia el código anterior para restablecer tu contraseña.</p>
                    <p>Ten en cuenta que vence en 15 minutos. <p>


                </div>
                <div class="footer">
                    <p>Si no solicitaste restablecer tu contraseña, ignora este correo.</p>
                    <p>Gracias,<br/>El equipo de CoffeTech</p>
                </div>
            </div>
        </body>
        </html>
        """
    else:
        print("Error: Tipo de correo no reconocido.")
        return

    # Crear el mensaje de correo electrónico
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = email

    # Agregar cuerpo en formato HTML
    msg.attach(MIMEText(body_html, "html"))

    try:
        # Conectar al servidor SMTP de Zoho usando SSL
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, email, msg.as_string())
            print(f"Correo de {email_type} enviado exitosamente")
    except Exception as e:
        print(f"Error al enviar correo de {email_type}: {e}")

# Ejemplo de uso
send_email('destinatario@example.com', 'tu_token', 'verification')
send_email('destinatario@example.com', 'tu_token', 'reset')
