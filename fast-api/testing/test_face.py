import cv2
import websocket
import requests
import json
import time
import tempfile

UPLOAD_URL = "http://localhost:8000/upload-reference/"
WEBSOCKET_URL = "ws://localhost:8000/ws/verify"

def capture_image_from_webcam(prompt="Press SPACE to capture reference image, ESC to exit"):
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("❌ Failed to access webcam.")
        return None

    print(prompt)
    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        cv2.imshow("Capture Frame", frame)
        key = cv2.waitKey(1)
        if key == 27:  # ESC key
            print("❌ Capture cancelled.")
            cap.release()
            cv2.destroyAllWindows()
            return None
        elif key == 32:  # SPACE key
            cap.release()
            cv2.destroyAllWindows()
            return frame

def upload_reference_image_from_frame(frame):
    # Save to temporary file
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
        cv2.imwrite(tmp_file.name, frame)
        tmp_path = tmp_file.name

    with open(tmp_path, "rb") as f:
        files = {'file': ('reference.jpg', f, 'image/jpeg')}
        response = requests.post(UPLOAD_URL, files=files)

    if response.status_code == 200:
        print("✅ Reference image uploaded successfully.")
        return True
    else:
        print("❌ Failed to upload reference image:", response.text)
        return False

def on_message(ws, message):
    data = json.loads(message)
    if "error" in data:
        print("❌ Error:", data["error"])
    else:
        print(f"🟢 Verified: {data['verified']}, Distance: {data['distance']:.4f}, Time: {data['timestamp']}")

def on_error(ws, error):
    print("❌ WebSocket Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("🔴 WebSocket connection closed.")

def on_open(ws):
    print("🟢 WebSocket connection opened. Verifying webcam frames...")

if __name__ == "__main__":
    frame = capture_image_from_webcam()
    if frame is None:
        exit(1)

    success = upload_reference_image_from_frame(frame)
    if not success:
        exit(1)

    print("Connecting to WebSocket for real-time verification...")
    ws = websocket.WebSocketApp(
        WEBSOCKET_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever()
