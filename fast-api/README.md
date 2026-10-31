# EduViva Proctoring Microservice Backend (`fast-api`)

This directory houses the core FastAPI backend and multimodal AI proctoring engines for EduViva.

For full architectural documentation, workflow diagrams, and API specifications, please refer to the [Root README](../README.md).

---

## Quickstart

### 1. Environment Setup
```bash
python -m venv venv
# On Windows:
.\venv\Scripts\Activate.ps1
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Run the Service
```bash
python main.py
```
Or via Uvicorn:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- WebSocket Gateway: `ws://localhost:8000/ws/proctoring/{session_id}`

---

## Modules Directory

- **`main.py`**: FastAPI application entry point, session orchestrator, and WebSocket handler.
- **`object.py`**: YOLOv8 prohibited object detection (`yolov8n.pt`).
- **`face_verify.py`**: DeepFace facial verification and template enrollment.
- **`environ_noise.py`**: YAMNet acoustic event classification (`yamnet_class_map.csv`).
- **`gaze_posture.py`**: MediaPipe FaceMesh gaze estimation and Pose ergonomic posture analysis.
- **`liveness_detection.py`**: Challenge-response EAR blink and texture anti-spoofing verification.
- **`voice.py`**: Resemblyzer voiceprint enrollment and real-time speaker verification.

