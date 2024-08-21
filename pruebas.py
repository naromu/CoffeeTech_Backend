import os

smtp_user = os.getenv("SMTP_USER")
smtp_pass = os.getenv("SMTP_PASS")

if smtp_user is None or smtp_pass is None:
    print("Variables de entorno no cargadas correctamente.")
else:
    print(f"SMTP_USER: '{smtp_user}'")
    print(f"SMTP_PASS: '{smtp_pass}'")

# Aquí coloca el código para enviar el correo.
