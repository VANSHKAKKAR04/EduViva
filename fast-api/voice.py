from fastapi import FastAPI, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from resemblyzer import VoiceEncoder, preprocess_wav
import numpy as np
from scipy.spatial.distance import cosine
import tempfile
import os
from fastapi.middleware.cors import CORSMiddleware
import base64
import io
import wave
import audioop
from pydantic import BaseModel
import json
import logging
import asyncio
from typing import Dict, List, Optional, Union
from fastapi import APIRouter


router=APIRouter()

# Set up logging with more detailed formatting
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Authentication API")
encoder = VoiceEncoder()
stored_embeddings = {}
active_sessions = {}

# CORS middleware settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins in development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration constants
THRESHOLD = 0.45  # Similarity threshold for voice verification
VAD_THRESHOLD = 200  # Voice activity detection threshold
SILENCE_LIMIT = 15  # Number of consecutive silence chunks before ending recording
MIN_AUDIO_LENGTH = 5.0  # Minimum audio length in seconds for processing
MAX_AUDIO_LENGTH = 15.0  # Maximum audio length in seconds
SAMPLE_RATE = 16000  # Sample rate for audio processing
BYTES_PER_SAMPLE = 2  # 16-bit audio

# Models for request/response validation
class AudioChunk(BaseModel):
    audio: str  # Base64 encoded audio data
    real_time: bool = False
    final_processing: bool = False

class EnrollmentRequest(BaseModel):
    candidate_id: str
    mode: str  # "enroll" or "verify"

class SessionData:
    def __init__(self, candidate_id: str, mode: str):
        self.candidate_id = candidate_id
        self.mode = mode
        self.audio_data: List[bytes] = []
        self.silence_count = 0
        self.is_speaking = False
        self.processed_duration = 0.0
        self.last_activity = asyncio.get_event_loop().time()
        self.real_time_embedding: Optional[np.ndarray] = None
    
    def add_audio(self, chunk: bytes) -> float:
        """Add audio chunk and return current duration in seconds"""
        self.audio_data.append(chunk)
        samples = sum(len(chunk) // BYTES_PER_SAMPLE for chunk in self.audio_data)
        return samples / SAMPLE_RATE
    
    def get_complete_audio(self) -> bytes:
        """Get processed complete audio data"""
        return preprocess_audio_chunks(self.audio_data)
    
    def reset(self):
        """Reset session audio data"""
        self.audio_data = []
        self.silence_count = 0
        self.is_speaking = False
        self.processed_duration = 0.0
        self.last_activity = asyncio.get_event_loop().time()

def preprocess_audio_chunks(chunks: List[bytes]) -> bytes:
    """
    Ensure audio data is properly formatted for WAV file creation.
    - Combines all chunks and ensures proper byte alignment
    - Returns processed audio data ready for WAV writing
    """
    if not chunks:
        return b''
    
    complete_audio = b''.join(chunks)
    
    # Ensure we have a whole number of frames (16-bit samples)
    if len(complete_audio) % BYTES_PER_SAMPLE != 0:
        complete_audio += b'\x00' * (BYTES_PER_SAMPLE - (len(complete_audio) % BYTES_PER_SAMPLE))
    
    return complete_audio

def create_wav_file(audio_data: bytes) -> str:
    """Create a temporary WAV file from audio data and return the path"""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    
    try:
        with wave.open(temp_file.name, 'wb') as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(BYTES_PER_SAMPLE)  # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio_data)
        
        return temp_file.name
    except Exception as e:
        # Clean up if there's an error
        os.unlink(temp_file.name)
        raise RuntimeError(f"Failed to create WAV file: {str(e)}")

async def process_audio_for_verification(audio_path: str, candidate_id: str) -> Dict:
    """Process audio for verification and return results"""
    if candidate_id not in stored_embeddings:
        raise ValueError(f"Candidate ID not enrolled: {candidate_id}")
    
    wav = preprocess_wav(audio_path)
    embedding = encoder.embed_utterance(wav)
    
    enrolled_embedding = np.array(stored_embeddings[candidate_id])
    similarity = 1 - cosine(embedding, enrolled_embedding)
    is_match = similarity >= THRESHOLD
    
    return {
        "similarity_score": float(similarity),
        "threshold": THRESHOLD,
        "match": bool(is_match),
        "embedding": embedding
    }


def process_audio_for_enrollment(audio_path: str, candidate_id: str) -> Dict:
    """Process audio for enrollment and store embedding"""
    wav = preprocess_wav(audio_path)
    embedding = encoder.embed_utterance(wav)
    stored_embeddings[candidate_id] = embedding.tolist()
    
    return {
        "candidate_id": candidate_id,
        "embedding": embedding
    }

def validate_wav_format(file: UploadFile):
    """Validate that the uploaded file is a WAV format"""
    if not file.filename.lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="Only .wav files are supported.")
    if file.content_type not in ["audio/wav", "audio/x-wav"]:
        raise HTTPException(status_code=400, detail="Invalid content type for WAV file.")

async def cleanup_inactive_sessions():
    """Background task to clean up inactive sessions"""
    while True:
        await asyncio.sleep(60)  # Check every minute
        current_time = asyncio.get_event_loop().time()
        
        inactive_sessions = []
        for session_id, session in active_sessions.items():
            # Remove sessions inactive for more than 10 minutes
            if current_time - session.last_activity > 600:
                inactive_sessions.append(session_id)
        
        for session_id in inactive_sessions:
            logger.info(f"Removing inactive session: {session_id}")
            del active_sessions[session_id]

# Start the background session cleanup task
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_inactive_sessions())

# Keep the existing HTTP endpoints for backward compatibility
@app.post("/enroll/{candidate_id}", response_model=Dict[str, str])
async def enroll(candidate_id: str, file: UploadFile = File(...)):
    """Enroll a new voice profile using a WAV file"""
    logger.info(f"Enrolling candidate ID: {candidate_id}")
    logger.info(f"Filename: {file.filename}, Content-Type: {file.content_type}")
    
    validate_wav_format(file)
    
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    
    temp_audio_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(contents)
            temp_audio_path = temp_audio.name
        
        wav = preprocess_wav(temp_audio_path)
        embedding = encoder.embed_utterance(wav)
        stored_embeddings[candidate_id] = embedding.tolist()
        logger.info(f"Enrollment successful for candidate ID: {candidate_id}")
        return {"message": "Enrollment successful", "candidate_id": candidate_id}
    except Exception as e:
        logger.error(f"Audio processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Audio processing failed: {str(e)}")
    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

@app.post("/verify/{candidate_id}")
async def verify(candidate_id: str, file: UploadFile = File(...)):
    """Verify a voice against an enrolled profile using a WAV file"""
    logger.info(f"Verifying candidate ID: {candidate_id}")
    
    if candidate_id not in stored_embeddings:
        logger.warning(f"Candidate ID not enrolled: {candidate_id}")
        raise HTTPException(status_code=404, detail="Candidate not enrolled.")
    
    validate_wav_format(file)
    
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")
    
    temp_audio_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(contents)
            temp_audio_path = temp_audio.name
        
        result = await process_audio_for_verification(temp_audio_path, candidate_id)
        # Remove the embedding from the result to avoid large responses
        result.pop("embedding", None)
        
        logger.info(f"Verification result for {candidate_id}: Match={result['match']}, Score={result['similarity_score']}")
        return result
    except Exception as e:
        logger.error(f"Audio processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Audio processing failed: {str(e)}")
    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint for checking API status"""
    return HTMLResponse(content="""
    <html>
    <head>
        <title>Voice Authentication API</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            h1 { color: #333366; }
            .status { padding: 10px; background-color: #d4edda; border-radius: 5px; }
            .endpoints { margin-top: 20px; }
            code { background-color: #f8f9fa; padding: 2px 5px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>Voice Authentication API</h1>
        <div class="status">Status: Running</div>
        <div class="endpoints">
            <h2>Available Endpoints:</h2>
            <ul>
                <li><code>GET /ping</code> - Check if the server is running</li>
                <li><code>POST /enroll/{candidate_id}</code> - Enroll a voice profile</li>
                <li><code>POST /verify/{candidate_id}</code> - Verify against an enrolled profile</li>
                <li><code>WebSocket /ws/audio</code> - Real-time audio processing</li>
            </ul>
        </div>
    </body>
    </html>
    """)

@app.get("/ping")
async def ping():
    """Ping endpoint for health checking"""
    return {
        "status": "ok", 
        "message": "Server is running",
        "active_sessions": len(active_sessions),
        "enrolled_profiles": len(stored_embeddings)
    }

@app.get("/profiles")
async def list_profiles():
    """List all enrolled profile IDs"""
    return {
        "profiles": list(stored_embeddings.keys()),
        "count": len(stored_embeddings)
    }

@app.delete("/profiles/{candidate_id}")
async def delete_profile(candidate_id: str):
    """Delete an enrolled profile"""
    if candidate_id in stored_embeddings:
        del stored_embeddings[candidate_id]
        return {"message": f"Profile {candidate_id} deleted successfully"}
    else:
        raise HTTPException(status_code=404, detail="Profile not found")

@app.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time voice authentication"""
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    # Generate a unique session ID
    session_id = f"session_{id(websocket)}"
    
    try:
        # Send initial message to client that connection is established
        await websocket.send_json({"status": "connected", "session_id": session_id})
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Initial setup message with candidate_id and mode
            if "candidate_id" in message and "mode" in message:
                candidate_id = message.get("candidate_id")
                mode = message.get("mode")
                logger.info(f"Initial setup: candidate_id={candidate_id}, mode={mode}")
                
                if not candidate_id:
                    await websocket.send_json({"status": "error", "error": "Missing candidate_id"})
                    continue
                
                # If verifying, check if the candidate exists
                if mode == "verify" and candidate_id not in stored_embeddings:
                    logger.warning(f"Verification attempt for non-enrolled candidate: {candidate_id}")
                    await websocket.send_json({
                        "status": "error", 
                        "error": "Candidate not enrolled",
                        "enrolled_profiles": list(stored_embeddings.keys())
                    })
                    continue
                
                # Create or reset session
                active_sessions[session_id] = SessionData(candidate_id, mode)
                await websocket.send_json({"status": "ready"})
                continue
            
            # Handle reset command
            elif "command" in message and message["command"] == "reset":
                if session_id in active_sessions:
                    logger.info(f"Reset command received for session {session_id}")
                    active_sessions[session_id].reset()
                    await websocket.send_json({"status": "reset"})
                else:
                    await websocket.send_json({
                        "status": "error", 
                        "error": "No active session found"
                    })
                continue
            
            # Process audio chunk
            if "audio" in message:
                # Check if we have an active session
                if session_id not in active_sessions:
                    await websocket.send_json({
                        "status": "error",
                        "error": "No active session. Send candidate_id and mode first."
                    })
                    continue
                
                session = active_sessions[session_id]
                session.last_activity = asyncio.get_event_loop().time()
                
                try:
                    # Decode base64 audio data
                    try:
                        chunk_data = base64.b64decode(message["audio"])
                    except Exception as e:
                        logger.error(f"Failed to decode base64 audio: {str(e)}")
                        await websocket.send_json({
                            "status": "error",
                            "message": f"Invalid audio data: {str(e)}"
                        })
                        continue
                    
                    # Ensure chunk data is valid (even number of bytes for 16-bit audio)
                    if len(chunk_data) % 2 != 0:
                        chunk_data += b'\x00'  # Pad with a zero byte
                    
                    # Check if this is final processing request
                    if message.get("final_processing", False):
                        await process_full_audio(websocket, session, chunk_data)
                        continue
                    
                    # Check if this is real-time verification request
                    if message.get("real_time", False) and session.mode == "verify":
                        await process_real_time_audio(websocket, session, chunk_data)
                        continue
                    
                    # Perform voice activity detection
                    try:
                        rms = audioop.rms(chunk_data, 2)  # Assuming 16-bit audio
                    except Exception as e:
                        logger.error(f"Error calculating RMS: {str(e)}")
                        await websocket.send_json({
                            "status": "error", 
                            "message": f"Error processing audio chunk: {str(e)}"
                        })
                        continue
                    
                    # Update session with new audio
                    session.add_audio(chunk_data)
                    current_duration = len(session.audio_data) * len(chunk_data) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
                    
                    # Detect if user is speaking or silent
                    if rms > VAD_THRESHOLD:
                        session.is_speaking = True
                        session.silence_count = 0
                        await websocket.send_json({"status": "recording"})
                    elif session.is_speaking:
                        # User was speaking but is now silent
                        session.silence_count += 1
                        
                        # If silence has continued for enough time or max duration reached, process the audio
                        if session.silence_count >= SILENCE_LIMIT or current_duration >= MAX_AUDIO_LENGTH:
                            await process_full_audio(websocket, session)
                
                except Exception as e:
                    logger.error(f"Error processing audio chunk: {str(e)}")
                    await websocket.send_json({
                        "status": "error",
                        "message": f"Error processing audio: {str(e)}"
                    })
            else:
                logger.warning(f"Received unrecognized message format: {message}")
                await websocket.send_json({
                    "status": "error",
                    "message": "Invalid message format"
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session {session_id}")
        # Clean up session when client disconnects
        if session_id in active_sessions:
            del active_sessions[session_id]
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        try:
            await websocket.send_json({
                "status": "error",
                "message": f"Server error: {str(e)}"
            })
        except:
            pass  # Client might be already disconnected
        
        # Clean up session on error
        if session_id in active_sessions:
            del active_sessions[session_id]

async def process_real_time_audio(websocket: WebSocket, session: SessionData, new_chunk: bytes = None):
    """Process audio chunk for real-time verification"""
    if session.mode != "verify":
        return
    
    candidate_id = session.candidate_id
    
    # If we have a new chunk, add it to the buffer
    if new_chunk:
        session.add_audio(new_chunk)
    
    # Check if we have enough audio for processing
    current_duration = sum(len(chunk) for chunk in session.audio_data) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
    if current_duration < MIN_AUDIO_LENGTH:
        return
    
    try:
        # Create a temporary WAV file with current audio data
        complete_audio = session.get_complete_audio()
        temp_file_path = create_wav_file(complete_audio)
        
        try:
            # Process for voice verification
            result = await process_audio_for_verification(temp_file_path, candidate_id)
            similarity = result["similarity_score"]
            
            # Send real-time similarity update
            await websocket.send_json({
                "status": "real_time_similarity",
                "similarity_score": float(similarity),
                "threshold": THRESHOLD
            })
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    
    except Exception as e:
        logger.error(f"Real-time processing error: {str(e)}")
        # Don't send error to client for real-time processing to avoid spamming

async def process_full_audio(websocket: WebSocket, session: SessionData, final_audio: bytes = None):
    """Process complete audio for enrollment or verification"""
    await websocket.send_json({"status": "processing"})
    
    candidate_id = session.candidate_id
    mode = session.mode
    
    try:
        # Get complete audio data - either from the final chunk or accumulated chunks
        complete_audio = final_audio if final_audio else session.get_complete_audio()
        
        # Check if we have enough audio
        audio_duration = len(complete_audio) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
        if audio_duration < MIN_AUDIO_LENGTH:
            await websocket.send_json({
                "status": "error",
                "message": f"Audio duration too short ({audio_duration:.1f}s). Please record at least {MIN_AUDIO_LENGTH}s."
            })
            return
        
        # Create a temporary WAV file
        temp_file_path = create_wav_file(complete_audio)
        
        try:
            # Process for enrollment or verification
            if mode == "enroll":
                await process_audio_for_enrollment(temp_file_path, candidate_id)
                await websocket.send_json({
                    "status": "complete",
                    "message": "Enrollment successful",
                    "candidate_id": candidate_id,
                    "audio_duration": round(audio_duration, 2)
                })
            else:  # verify
                result = await process_audio_for_verification(temp_file_path, candidate_id)
                # Remove the embedding from the result to avoid large responses
                result.pop("embedding", None)
                result["status"] = "complete"
                result["audio_duration"] = round(audio_duration, 2)
                await websocket.send_json(result)
        
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
        
        # Reset session for next recording
        session.reset()
    
    except Exception as e:
        logger.error(f"Audio processing failed: {str(e)}")
        error_details = {
            "status": "error",
            "message": f"Audio processing failed: {str(e)}",
            "error_type": type(e).__name__
        }
        await websocket.send_json(error_details)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)