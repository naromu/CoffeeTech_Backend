import base64

def convertir_imagen_a_base64_y_guardar(ruta_imagen, ruta_salida):
    with open(ruta_imagen, "rb") as imagen_file:
        imagen_base64 = base64.b64encode(imagen_file.read())
        with open(ruta_salida, "w") as archivo_salida:
            archivo_salida.write(imagen_base64.decode('utf-8'))

# Uso
ruta = 'ferrogum.jpeg'  # Reemplaza esto con la ruta de tu imagen
ruta_salida = 'imagen_base64.txt'  # Nombre del archivo de salida
convertir_imagen_a_base64_y_guardar(ruta, ruta_salida)

print(f"La imagen se ha convertido y guardado en {ruta_salida}")
