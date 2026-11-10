"""
Extensión - YOLO como servicio web, con el mismo patrón FastAPI del taller Docker + TensorFlow.
Uso:  uvicorn yolo_api:app --host 0.0.0.0 --port 8000     y abrir  http://<IP_PI>:8000/docs
Requiere:  pip install fastapi uvicorn python-multipart
"""
import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile
from ultralytics import YOLO

app = FastAPI(title="Detector de objetos YOLO")
modelo = YOLO("yolo26n.pt")


@app.post("/detectar/")
async def detectar(file: UploadFile = File(...)):
    datos = np.frombuffer(await file.read(), np.uint8)
    img = cv2.imdecode(datos, cv2.IMREAD_COLOR)
    r = modelo(img, conf=0.5, verbose=False)[0]
    return {"objetos": [
        {"clase": modelo.names[int(c.cls)],
         "confianza": round(float(c.conf), 2),
         "caja": [int(v) for v in c.xyxy[0]]}
        for c in r.boxes
    ]}
