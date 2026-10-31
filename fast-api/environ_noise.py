from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import tensorflow_hub as hub
import tensorflow as tf
import numpy as np
import urllib.request
import asyncio
import os
from fastapi import APIRouter


router=APIRouter()
app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attempt to load the YAMNet model
try:
    print("🔄 Loading YAMNet model from TFHub...")
    yamnet_model = hub.load("https://tfhub.dev/google/yamnet/1")
    print("✅ YAMNet model loaded successfully.")
except Exception as e:
    print(f"❌ Failed to load YAMNet model: {e}")
    raise RuntimeError("Could not load YAMNet model.")

# Load class names
class_map_path = 'yamnet_class_map.csv'
if not tf.io.gfile.exists(class_map_path):
    print("⬇️ Downloading class map...")
    urllib.request.urlretrieve(
        "https://raw.githubusercontent.com/tensorflow/models/master/research/audioset/yamnet/yamnet_class_map.csv",
        class_map_path
    )

class_names = [line.strip().split(',')[2] for line in open(class_map_path).readlines()[1:]]

ACCEPTED_LABELS = [
    "Speech", "Conversation", "Narration, monologue",
    "Silence", "Inside, small room", "Inside, large room or hall",  # Add acceptable quiet states
    "White noise", "Outside, urban or manmade", "Outside, rural or natural"  # Add acceptable background noise
]

# Rolling buffer config
BUFFER_DURATION = 2  # seconds
SAMPLE_RATE = 16000
BUFFER_SIZE = SAMPLE_RATE * BUFFER_DURATION
buffer = np.zeros(BUFFER_SIZE, dtype=np.float32)

# 🔮 Predict using full buffered audio
def predict_audio_full(audio: np.ndarray):
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    if audio.shape[0] < SAMPLE_RATE:
        return "Unknown", 0.01

    # Ensure the input is a float32 Tensor
    audio_tensor = tf.convert_to_tensor(audio, dtype=tf.float32)
    scores, embeddings, spectrogram = yamnet_model(audio_tensor)
    avg_scores = tf.reduce_mean(scores, axis=0).numpy()
    top_index = np.argmax(avg_scores)
    return class_names[top_index], float(avg_scores[top_index])

# 🎧 WebSocket endpoint
@app.websocket("/ws/audio")
async def stream_audio(websocket: WebSocket):
    await websocket.accept()
    print("🔌 WebSocket client connected.")

    global buffer

    try:
        while True:
            raw_bytes = await websocket.receive_bytes()
            audio_np = np.frombuffer(raw_bytes, dtype=np.float32)

            # Update rolling buffer
            buffer = np.roll(buffer, -len(audio_np))
            buffer[-len(audio_np):] = audio_np

            # Predict only if buffer is filled enough
            if np.count_nonzero(buffer) > 0.5 * BUFFER_SIZE:
                label, confidence = predict_audio_full(buffer)

                await websocket.send_json({
                    "label": label,
                    "confidence": confidence,
                    "alert": label not in ACCEPTED_LABELS
                })

                await asyncio.sleep(0.25)

    except WebSocketDisconnect:
        print("❌ WebSocket client disconnected.")
