import os
import uuid
import sounddevice as sd
import soundfile as sf
import requests

# Configuration
duration = 5  # seconds
sample_rate = 16000
output_dir = "assets"
base_url = "http://127.0.0.1:8000"  # FastAPI server URL

# Generate unique candidate ID and filenames
candidate_id = f"candidate_{uuid.uuid4().hex[:8]}"
enroll_path = os.path.join(output_dir, f"enroll_{candidate_id}.wav")
verify_path = os.path.join(output_dir, f"verify_{candidate_id}.wav")

# Ensure the output directory exists
os.makedirs(output_dir, exist_ok=True)

def record_audio(path, label):
    print(f"🎙️ Recording {label} audio for {duration} seconds...")
    audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
    sd.wait()
    sf.write(path, audio, sample_rate)
    print(f"💾 Saved {label} audio to: {path}")

def upload_audio(endpoint, file_path):
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f, "audio/wav")}
        response = requests.post(endpoint, files=files)
    return response

# Step 1: Record enrollment audio
record_audio(enroll_path, "enrollment")

# Step 2: Send to /enroll endpoint
enroll_url = f"{base_url}/enroll/{candidate_id}"
enroll_response = upload_audio(enroll_url, enroll_path)

print("\n----- Enrollment Response -----")
print("Candidate ID:", candidate_id)
print("Status Code:", enroll_response.status_code)
print("Response:", enroll_response.json())

# Step 3: Record verification audio
record_audio(verify_path, "verification")

# Step 4: Send to /verify endpoint
verify_url = f"{base_url}/verify/{candidate_id}"
verify_response = upload_audio(verify_url, verify_path)

print("\n----- Verification Response -----")
print("Status Code:", verify_response.status_code)
print("Response:", verify_response.json())
