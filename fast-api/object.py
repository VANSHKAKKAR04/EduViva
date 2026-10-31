# --- FASTAPI BACKEND WITH WEBSOCKET ---
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter
from pydantic import BaseModel
from ultralytics import YOLO
from deepface import DeepFace
import cv2
import numpy as np
import os
import tempfile
import time
import json

app = FastAPI()
router = APIRouter()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

# Load model once
model = YOLO("yolov8n.pt")
CANDIDATE_IMAGE_PATH = "candidate_face.jpg"
PROHIBITED_CLASSES = {"cell phone", "book", "paper", "laptop"}

@router.post("/capture-candidate")
async def capture_candidate(file: UploadFile = File(...)):
    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image uploaded.")
    
    cv2.imwrite(CANDIDATE_IMAGE_PATH, frame)
    
    # Extract face template
    success, message = extract_candidate_face_template(CANDIDATE_IMAGE_PATH)
    
    if not success:
        raise HTTPException(status_code=400, detail=message)
    
    return {"message": message}


@router.websocket("/ws/monitor")
async def websocket_monitor(websocket: WebSocket):
    await websocket.accept()

    if not os.path.exists(CANDIDATE_IMAGE_PATH):
        await websocket.send_json({"error": "Candidate image not uploaded yet."})
        await websocket.close()
        return

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        await websocket.send_json({"error": "Could not access webcam."})
        await websocket.close()
        return
    else:
        print("✅ Webcam accessed successfully.")

    try:
        while True:
            ret, frame = cap.read()

            if not ret or frame is None:
                print("❌ Failed to read frame.")
                await websocket.send_json({"error": "Failed to read frame."})
                break

            print("✅ Frame captured at", time.strftime("%H:%M:%S"))
            resized = cv2.resize(frame, (640, 480))
            results = model(resized)[0]

            frame_violations = set()
            alert = False

            for box in results.boxes:
                cls_id = int(box.cls[0])
                class_name = model.names[cls_id]

                if class_name in PROHIBITED_CLASSES:
                    frame_violations.add(f"Prohibited object: {class_name}")
                    alert = True

                elif class_name == "person":
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(resized.shape[1], x2), min(resized.shape[0], y2)
                    face_img = resized[y1:y2, x1:x2]

                    if face_img.size == 0:
                        continue

                    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                        temp_path = tmp_file.name
                        cv2.imwrite(temp_path, face_img)

                    try:
                        result = DeepFace.verify(
                            img1_path=CANDIDATE_IMAGE_PATH,
                            img2_path=temp_path,
                            enforce_detection=False
                        )
                        if not result.get("verified", False):
                            frame_violations.add("Unrecognized person detected")
                            alert = True
                    except Exception as e:
                        print(f"⚠️ DeepFace error: {e}")
                        frame_violations.add("Face verification failed")
                        alert = True
                    finally:
                        os.remove(temp_path)

            await websocket.send_json({
                "alert": alert,
                "violations": list(frame_violations),
                "timestamp": time.strftime("%H:%M:%S")
            })

            # Throttle frame capture rate
            time.sleep(0.2)

    except WebSocketDisconnect:
        print("🔌 WebSocket disconnected.")
    finally:
        cap.release()
        print("📷 Webcam released.")

    await websocket.accept()

def detect_objects_from_frame(frame: np.ndarray, prohibited_classes=None) -> dict:
    """
    Detect objects in a frame using YOLO and return violations for prohibited objects.
    Returns a dict with 'violation', 'violation_type', 'value', 'message', and detected objects.
    """
    if prohibited_classes is None:
        prohibited_classes = {"cell phone", "book", "paper", "laptop"}
    results = model(frame)[0]
    violations = []
    detected_objects = []
    for box in results.boxes:
        cls_id = int(box.cls[0])
        class_name = model.names[cls_id]
        detected_objects.append(class_name)
        if class_name in prohibited_classes:
            violations.append(class_name)
    if violations:
        message = "Prohibited objects detected: " + ", ".join(violations)
        violation_flag = True
        violation_type = 'object_detection'
        value = len(violations)
    else:
        message = "No prohibited objects detected"
        violation_flag = False
        violation_type = None
        value = 0
    return {
        'violation': violation_flag,
        'violation_type': violation_type,
        'value': value,
        'message': message,
        'detected_objects': detected_objects
    }

