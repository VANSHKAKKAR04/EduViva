import asyncio
import websockets
import sounddevice as sd
import numpy as np
import json
from queue import Queue, Empty
import threading

WS_URL = "ws://localhost:8000/ws/audio"
SAMPLE_RATE = 16000
CHUNK_DURATION = 2
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_DURATION)

audio_queue = Queue()

def audio_callback(indata, frames, time, status):
    if status:
        print("⚠️ Audio status:", status)
    print("🎤 Audio chunk received.")
    audio_queue.put(indata.copy())

async def send_audio():
    async with websockets.connect(WS_URL) as websocket:
        print("🎙️ Connected to server.")

        def start_audio_stream():
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype='float32',
                                blocksize=CHUNK_SIZE, callback=audio_callback):
                threading.Event().wait()

        threading.Thread(target=start_audio_stream, daemon=True).start()

        while True:
            try:
                audio_chunk = audio_queue.get(timeout=1)
                await websocket.send(audio_chunk.astype(np.float32).tobytes())

                response = await websocket.recv()
                data = json.loads(response)
                print(f"🧠 {data['label']} ({data['confidence']:.2f}) | Alert: {data['alert']}")
            except Empty:
                print("⌛ Waiting for audio...")
            except Exception as e:
                print("❌ Error receiving from server:", e)
                break

asyncio.run(send_audio())
