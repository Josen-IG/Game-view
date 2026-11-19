# Game-view

Aplicación local para analizar grabaciones de fútbol y base para comparar
detectores y seguimiento. Extraída de la pestaña Vídeo de
[Match View](https://github.com/Josen-IG/Match_view/tree/64f4a26).

## Ejecutar

Requiere Python 3.12 y los ejecutables `ffmpeg` y `ffprobe` en PATH.
Ejecuta estos comandos desde la raíz del repositorio:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py --server.address 127.0.0.1
```

Introduce la ruta de un vídeo local, el minuto de inicio y el alcance.
El reproductor se abre cuando acaba el tracking. El vídeo original se
conserva y los resultados se guardan en una carpeta junto a él, donde
el proceso necesita permiso de escritura. La aplicación usa los nombres y
colores por defecto del motor. Para indicar colores reales usa la CLI.

## Modelos y evaluación

Los pesos incluidos son `modelo_propio.pt` (modelo principal),
`pitch_keypoints.pt` (campo) y `yolo11s.pt` (alternativo). El modo
automático usa los respaldos disponibles y muestra su estado. Consulta
[la integración de modelos](MODEL_INTEGRATIONS.md) para instalar YOLOv9,
RF-DETR, el campo de 32 puntos, OpenSportsLab y SoccerNet Game State.

```powershell
python video_track.py --help
python model_evaluation.py --help
python -m unittest discover -s tests
```

En `dataset/` están las etiquetas y la configuración heredadas;
las imágenes completas de entrenamiento se obtienen por separado.
Los vídeos y resultados locales no se versionan.
