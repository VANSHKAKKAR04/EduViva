import cv2
import asyncio
import websockets
import requests
import json
import tempfile
import os

SERVER_URL = "http://localhost:8000"
WS_URL = "ws://localhost:8000/ws/monitor"

def capture_and_upload_candidate():
    print("📸 Capturing candidate image...")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Unable to access webcam.")
        return False

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("❌ Failed to capture image.")
        return False

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
        cv2.imwrite(tmp.name, frame)
        image_path = tmp.name

    print("📤 Uploading candidate image to backend...")
    try:
        with open(image_path, "rb") as f:
            response = requests.post(f"{SERVER_URL}/capture-candidate", files={"file": f})
        if response.status_code == 200:
            print("✅ Image uploaded successfully.")
            return True
        else:
            print("❌ Upload failed:", response.text)
            return False
    finally:
        os.remove(image_path)

async def monitor_websocket():
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("🔌 Connected to WebSocket for monitoring.")
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)

                if "error" in data:
                    print("❌ Error from server:", data["error"])
                    break

                print(f"\n🕒 Time: {data['timestamp']}")
                print("🚨 Alert Status:", "Yes" if data['alert'] else "No")
                if data['violations']:
                    for v in data['violations']:
                        print(f"   ⚠️ Violation: {v}")
                else:
                    print("✅ No violations.")
                print("-" * 40)
    except Exception as e:
        print("❌ WebSocket connection error:", e)

if __name__ == "__main__":
    if capture_and_upload_candidate():
        asyncio.run(monitor_websocket())
