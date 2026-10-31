from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import mediapipe as mp
import numpy as np
import cv2
import uvicorn
from typing import List, Optional, Dict, Any
import math
import time
from pydantic import BaseModel
import uuid
from datetime import datetime, timedelta
import json
import os
import logging
import asyncio
from fastapi import APIRouter
import random

logging.basicConfig(level=logging.INFO)


router=APIRouter()
# Initialize the main FastAPI app
app = FastAPI(title="AI Assessment Proctoring API with Liveness Detection")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MediaPipe Face Mesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,  # ADD THIS - crucial for better eye detection
    min_detection_confidence=0.7,  # Increase from 0.5
    min_tracking_confidence=0.5
)

# Eye landmarks indices (simplified)
LEFT_EYE_INDICES = [362, 385, 387, 263, 373, 380]  # Upper and lower points
RIGHT_EYE_INDICES = [33, 160, 158, 133, 153, 144]  # Upper and lower points

# In-memory storage for demo purposes
# In production, use a proper database
active_sessions = {}
assessments = {}
user_analytics = {}
challenge_sessions = {}

logger = logging.getLogger("main-proctoring")

# --- Enhanced EAR history for robust blink detection ---
challenge_ear_history = {}
challenge_blink_state = {}

# Blink detection constants

EAR_CLOSED_THRESHOLD = 0.22
EAR_OPEN_THRESHOLD = 0.28
BLINK_BUFFER_SIZE = 12
MIN_CONSECUTIVE_CLOSED_FRAMES = 1
MIN_CONSECUTIVE_OPEN_FRAMES = 1

class BlinkState:
    def __init__(self):
        self.state = "OPEN"  # UNKNOWN, OPEN, CLOSED, BLINK_DETECTED
        self.consecutive_closed_frames = 0
        self.consecutive_open_frames = 0
        self.blink_detected = False
        self.last_blink_time = 0
        self.total_blinks = 0  #   
# ============== MODELS ==============

class User(BaseModel):
    user_id: str
    name: str
    email: str

class AssessmentSession(BaseModel):
    session_id: str
    user_id: str
    assessment_id: str
    start_time: datetime
    violations: List[Dict[str, Any]] = []
    liveness_checks: List[Dict[str, Any]] = []
    is_active: bool = True

class ProctorEvent(BaseModel):
    event_type: str  # "face_not_visible", "multiple_faces", "looking_away", etc.
    timestamp: datetime
    confidence: float
    details: Optional[Dict[str, Any]] = None
    
class LivenessCheckRequest(BaseModel):
    session_id: str
    user_id: str

class LivenessResult(BaseModel):
    success: bool
    challenge_completed: bool
    message: str

class StartSessionRequest(BaseModel):
    user_id: str
    name: str
    email: str
    assessment_id: str

class ChallengeRequest(BaseModel):
    user_id: str

class ChallengeResponse(BaseModel):
    challenge_id: str
    challenge_type: str
    expires_at: str
    instructions: str

# ============== ENHANCED LIVENESS DETECTION FUNCTIONS ==============

def calculate_ear(landmarks, eye_indices):
    """Calculate Eye Aspect Ratio (EAR)"""
    # Extract eye landmarks
    points = [landmarks[idx] for idx in eye_indices]
    
    # Calculate vertical distances
    v1 = distance(points[1], points[5])
    v2 = distance(points[2], points[4])
    
    # Calculate horizontal distance
    h = distance(points[0], points[3])
    
    # Avoid division by zero
    if h == 0:
        return 0
    
    # Calculate EAR
    ear = (v1 + v2) / (2.0 * h)
    return ear

def distance(p1, p2):
    """Calculate Euclidean distance between two points"""
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2)

def initialize_challenge_tracking(challenge_id):
    """Initialize tracking for a new challenge"""
    if challenge_id not in challenge_ear_history:
        challenge_ear_history[challenge_id] = []
    if challenge_id not in challenge_blink_state:
        challenge_blink_state[challenge_id] = BlinkState()

# def detect_blink_robust(frame, challenge_id=None):
#     """
#     Enhanced blink detection using state machine approach
#     Returns: (blink_detected, landmarks, ear_value)
#     """
#     # Convert BGR to RGB
#     rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    
#     # Process frame with Face Mesh
#     results = face_mesh.process(rgb_frame)
    
#     if not results.multi_face_landmarks:
#         return False, None, 0.0
    
#     face_landmarks = results.multi_face_landmarks[0]
#     landmarks = face_landmarks.landmark
    
#     # Calculate EAR for both eyes
#     left_ear = calculate_ear(landmarks, LEFT_EYE_INDICES)
#     right_ear = calculate_ear(landmarks, RIGHT_EYE_INDICES)
    
#     # Average EAR
#     avg_ear = (left_ear + right_ear) / 2.0
    
#     # Use challenge_id for tracking, fallback to 'global'
#     tracking_key = challenge_id or 'global'
    
#     # Initialize tracking if needed
#     initialize_challenge_tracking(tracking_key)
    
#     # Get history and state
#     ear_buffer = challenge_ear_history[tracking_key]
#     blink_state = challenge_blink_state[tracking_key]
    
#     # Add current EAR to buffer
#     ear_buffer.append(avg_ear)
#     if len(ear_buffer) > BLINK_BUFFER_SIZE:
#         ear_buffer.pop(0)
    
#     # State machine for blink detection
#     current_time = time.time()
#     blink_detected = False
    
#     if avg_ear < EAR_CLOSED_THRESHOLD:
#         # Eyes are closed
#         blink_state.consecutive_closed_frames += 1
#         blink_state.consecutive_open_frames = 0
        
#         if (blink_state.state == "OPEN" and 
#             blink_state.consecutive_closed_frames >= MIN_CONSECUTIVE_CLOSED_FRAMES):
#             blink_state.state = "CLOSED"
            
#     elif avg_ear > EAR_OPEN_THRESHOLD:
#         # Eyes are open
#         blink_state.consecutive_open_frames += 1
#         blink_state.consecutive_closed_frames = 0
        
#         if (blink_state.state == "CLOSED" and 
#             blink_state.consecutive_open_frames >= MIN_CONSECUTIVE_OPEN_FRAMES):
#             # Complete blink detected (closed -> open transition)
#             if current_time - blink_state.last_blink_time > 0.5:  # Prevent double counting
#                 blink_detected = True
#                 blink_state.blink_detected = True
#                 blink_state.last_blink_time = current_time
#                 logger.info(f"Blink detected for challenge {tracking_key}")
#             blink_state.state = "OPEN"
#         elif blink_state.state == "UNKNOWN":
#             blink_state.state = "OPEN"
    
#     return blink_detected, landmarks, avg_ear

# 4. Fix the blink detection logic in your detect_blink_robust function
def detect_blink_robust(frame, challenge_id=None):
    """Fixed version of your blink detection"""
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb_frame)
    
    if not results.multi_face_landmarks:
        return False, None, 0.0
    
    face_landmarks = results.multi_face_landmarks[0]
    landmarks = face_landmarks.landmark
    
    # Calculate EAR for both eyes
    left_ear = calculate_ear(landmarks, LEFT_EYE_INDICES)
    right_ear = calculate_ear(landmarks, RIGHT_EYE_INDICES)
    avg_ear = (left_ear + right_ear) / 2.0
    
    tracking_key = challenge_id or 'global'
    initialize_challenge_tracking(tracking_key)
    
    ear_buffer = challenge_ear_history[tracking_key]
    blink_state = challenge_blink_state[tracking_key]
    
    ear_buffer.append(avg_ear)
    if len(ear_buffer) > BLINK_BUFFER_SIZE:
        ear_buffer.pop(0)
    
    current_time = time.time()
    blink_detected = False
    
    # logger = logging.getLogger(__name__)
    frame_counter = 0
    frame_counter += 1
    if frame_counter % 30 == 0:
        logger.info(f"EAR: {avg_ear:.3f}, State: {blink_state.state}, "
               f"Closed: {blink_state.consecutive_closed_frames}, "
               f"Open: {blink_state.consecutive_open_frames}, "
               f"Total blinks: {blink_state.total_blinks}")
    
    # FIXED LOGIC HERE
    if avg_ear < EAR_CLOSED_THRESHOLD:
        blink_state.consecutive_closed_frames += 1
        blink_state.consecutive_open_frames = 0
        
        if (blink_state.state == "OPEN" and 
            blink_state.consecutive_closed_frames >= MIN_CONSECUTIVE_CLOSED_FRAMES):
            blink_state.state = "CLOSED"
            
    elif avg_ear > EAR_OPEN_THRESHOLD:
        blink_state.consecutive_open_frames += 1
        blink_state.consecutive_closed_frames = 0
        
        # KEY FIX: Check for transition from CLOSED to OPEN
        if (blink_state.state == "CLOSED" and 
            blink_state.consecutive_open_frames >= MIN_CONSECUTIVE_OPEN_FRAMES and
            current_time - blink_state.last_blink_time > 0.3):  # 300ms cooldown
            
            blink_detected = True
            blink_state.blink_detected = True
            blink_state.total_blinks += 1  # Add this line
            blink_state.last_blink_time = current_time
            blink_state.state = "OPEN"
            logger.info(f"Blink detected for challenge {tracking_key}! Total: {blink_state.total_blinks}")
            
        elif blink_state.state != "CLOSED":
            blink_state.state = "OPEN"
    
    return blink_detected, landmarks, avg_ear

def detect_blink(frame, challenge_id=None):
    """
    Legacy function name for backwards compatibility
    """
    blink_detected, landmarks, _ = detect_blink_robust(frame, challenge_id)
    return blink_detected, landmarks

def check_head_movement(current_landmarks, previous_landmarks=None, threshold=0.01):
    """Check for natural head movements between frames"""
    if previous_landmarks is None:
        return True  # No previous landmarks to compare
    
    # Use nose tip landmark (index 1) for movement detection
    current_nose = current_landmarks[1]
    previous_nose = previous_landmarks[1]
    
    # Calculate movement
    movement = distance(current_nose, previous_nose)
    
    # Some movement is natural, but not too much
    return 0.001 < movement < threshold


# def validate_challenge(challenge_id, landmarks, challenge_type):
#     """Validate if the user completed the requested challenge"""
#     if challenge_type == "look_left":
#         # Check if head is turned left (simplified)
#         nose_tip = landmarks[1]
#         left_ear = landmarks[234]
#         right_ear = landmarks[454]
        
#         # If nose is closer to left ear than right ear, person is looking left
#         return distance(nose_tip, left_ear) < distance(nose_tip, right_ear)
    
#     elif challenge_type == "look_right":
#         nose_tip = landmarks[1]
#         left_ear = landmarks[234]
#         right_ear = landmarks[454]
        
#         # If nose is closer to right ear than left ear, person is looking right
#         return distance(nose_tip, right_ear) < distance(nose_tip, left_ear)
    
#     elif challenge_type == "blink":
#         # Check if blink was detected for this challenge
#         tracking_key = challenge_id or 'global'
#         if tracking_key in challenge_blink_state:
#             return challenge_blink_state[tracking_key].blink_detected
#         return False
    
#     return False

def validate_challenge(challenge_id, landmarks, challenge_type):
    """Fixed challenge validation"""
    if challenge_type == "blink":
        tracking_key = challenge_id or 'global'
        if tracking_key in challenge_blink_state:
            # Check total blinks instead of just blink_detected flag
            return challenge_blink_state[tracking_key].total_blinks > 0
        return False
    
    elif challenge_type == "look_left":
        nose_tip = landmarks[1]
        left_ear = landmarks[234]
        right_ear = landmarks[454]
        return distance(nose_tip, left_ear) < distance(nose_tip, right_ear)
    
    elif challenge_type == "look_right":
        nose_tip = landmarks[1]
        left_ear = landmarks[234] 
        right_ear = landmarks[454]
        return distance(nose_tip, right_ear) < distance(nose_tip, left_ear)
    
    return False

# def reset_challenge_tracking(challenge_id):
#     """Reset tracking data for a challenge"""
#     if challenge_id in challenge_ear_history:
#         challenge_ear_history[challenge_id] = []
#     if challenge_id in challenge_blink_state:
#         challenge_blink_state[challenge_id] = BlinkState()

# 7. Update your reset function to also reset total_blinks
def reset_challenge_tracking(challenge_id):
    """Reset tracking data for a challenge"""
    if challenge_id in challenge_ear_history:
        challenge_ear_history[challenge_id] = []
    if challenge_id in challenge_blink_state:
        state = challenge_blink_state[challenge_id]
        state.state = "OPEN"
        state.consecutive_closed_frames = 0
        state.consecutive_open_frames = 0
        state.blink_detected = False
        state.total_blinks = 0  # ADD THIS LINE
        state.last_blink_time = 0

def get_challenge_debug_info(challenge_id):
    """Get debug information for a challenge"""
    tracking_key = challenge_id or 'global'
    debug_info = {
        "ear_history_length": len(challenge_ear_history.get(tracking_key, [])),
        "current_state": "UNKNOWN",
        "blink_detected": False,
        "consecutive_closed": 0,
        "consecutive_open": 0
    }
    
    if tracking_key in challenge_blink_state:
        state = challenge_blink_state[tracking_key]
        debug_info.update({
            "current_state": state.state,
            "blink_detected": state.blink_detected,
            "consecutive_closed": state.consecutive_closed_frames,
            "consecutive_open": state.consecutive_open_frames
        })
    
    return debug_info

# ============== SESSION MANAGEMENT ENDPOINTS ==============

@app.post("/session/start")
async def start_assessment_session(user: User, assessment_id: str):
    """Start a new assessment session for a user"""
    session_id = str(uuid.uuid4())
    
    # Create a new session
    session = AssessmentSession(
        session_id=session_id,
        user_id=user.user_id,
        assessment_id=assessment_id,
        start_time=datetime.now(),
        violations=[],
        liveness_checks=[],
        is_active=True
    )
    
    # Store the session
    active_sessions[session_id] = session
    
    # Return the session information
    return {
        "session_id": session_id,
        "user_id": user.user_id,
        "assessment_id": assessment_id,
        "start_time": session.start_time.isoformat(),
        "message": "Assessment session started successfully"
    }

@app.post("/session/end")
async def end_assessment_session(session_id: str):
    """End an active assessment session"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Update session status
    active_sessions[session_id].is_active = False
    
    # In a real system, you'd save the session to a database
    
    return {
        "session_id": session_id,
        "end_time": datetime.now().isoformat(),
        "message": "Assessment session ended successfully"
    }

@app.post("/proctor/report-violation")
async def report_violation(session_id: str, event: ProctorEvent):
    """Report a proctoring violation"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    if not session.is_active:
        raise HTTPException(status_code=400, detail="Session is not active")
    
    # Add the violation to the session
    session.violations.append({
        "event_type": event.event_type,
        "timestamp": event.timestamp.isoformat(),
        "confidence": event.confidence,
        "details": event.details
    })
    
    return {
        "success": True,
        "message": f"Violation of type '{event.event_type}' recorded"
    }

@app.get("/session/{session_id}/violations")
async def get_session_violations(session_id: str):
    """Get all violations for a session"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    return {
        "session_id": session_id,
        "violations_count": len(session.violations),
        "violations": session.violations
    }

@app.post("/proctor/record-liveness-check")
async def record_liveness_check(session_id: str, result: LivenessResult):
    """Record the result of a liveness check"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    if not session.is_active:
        raise HTTPException(status_code=400, detail="Session is not active")
    
    # Add the liveness check to the session
    session.liveness_checks.append({
        "timestamp": datetime.now().isoformat(),
        "success": result.success,
        "challenge_completed": result.challenge_completed,
        "message": result.message
    })
    
    return {
        "success": True,
        "message": f"Liveness check recorded: {'passed' if result.success else 'failed'}"
    }

@app.get("/session/{session_id}/info")
async def get_session_info(session_id: str):
    """Get detailed information about a session"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    # Convert session to dict for response
    session_data = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "assessment_id": session.assessment_id,
        "start_time": session.start_time.isoformat(),
        "is_active": session.is_active,
        "violations_count": len(session.violations),
        "liveness_checks_count": len(session.liveness_checks),
        "duration_minutes": (datetime.now() - session.start_time).total_seconds() / 60
    }
    
    return JSONResponse(session_data)

@app.websocket("/ws/session/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"Session {session_id} WebSocket connected.")
    user_analytics[session_id] = {
        "gaze": [],
        "posture": [],
        "voice": [],
        "env_noise": [],
        "face": [],
        "start_time": time.time(),
    }
    try:
        while True:
            data = await websocket.receive_json()
            # Expecting: {"type": "video"/"audio", "payload": ...}
            msg_type = data.get("type")
            payload = data.get("payload")
            if msg_type == "video":
                # Forward to gaze_posture WebSocket logic
                # Here, you would call the gaze_posture manager's analysis functions
                # For demo, just append
                user_analytics[session_id]["gaze"].append(payload)
                user_analytics[session_id]["posture"].append(payload)
            elif msg_type == "audio":
                # Forward to voice WebSocket logic
                user_analytics[session_id]["voice"].append(payload)
            elif msg_type == "env_noise":
                # Forward to environ_noise logic
                user_analytics[session_id]["env_noise"].append(payload)
            elif msg_type == "face":
                # Forward to face_verify logic
                user_analytics[session_id]["face"].append(payload)
            elif msg_type == "get_analytics":
                # Return analytics summary
                summary = {
                    "gaze": len(user_analytics[session_id]["gaze"]),
                    "posture": len(user_analytics[session_id]["posture"]),
                    "voice": len(user_analytics[session_id]["voice"]),
                    "env_noise": len(user_analytics[session_id]["env_noise"]),
                    "face": len(user_analytics[session_id]["face"]),
                    "duration": time.time() - user_analytics[session_id]["start_time"]
                }
                await websocket.send_json({"type": "analytics", "summary": summary})
            else:
                await websocket.send_json({"type": "error", "message": "Unknown message type"})
    except WebSocketDisconnect:
        logger.info(f"Session {session_id} WebSocket disconnected.")
    except Exception as e:
        logger.error(f"Error in session {session_id} WebSocket: {e}")

@app.get("/session/{session_id}/analytics")
async def get_session_analytics(session_id: str):
    if session_id not in user_analytics:
        raise HTTPException(status_code=404, detail="Session not found")
    summary = {
        "gaze": len(user_analytics[session_id]["gaze"]),
        "posture": len(user_analytics[session_id]["posture"]),
        "voice": len(user_analytics[session_id]["voice"]),
        "env_noise": len(user_analytics[session_id]["env_noise"]),
        "face": len(user_analytics[session_id]["face"]),
        "duration": time.time() - user_analytics[session_id]["start_time"]
    }
    return summary

CHALLENGE_TYPES = ["blink", "look_left", "look_right", "nod"]

async def create_random_challenge():
    challenge_id = str(uuid.uuid4())
    challenge_type = random.choice(CHALLENGE_TYPES)
    expiration_seconds = 45 if challenge_type == "blink" else 30
    expires_at = datetime.now() + timedelta(seconds=expiration_seconds)
    
    challenge_sessions[challenge_id] = {
        "type": challenge_type,
        "expires_at": expires_at,
        "completed": False,
        "attempts": 0
    }
    
    logger.info(f"[LIVENESS] Created random challenge: type={challenge_type}, id={challenge_id}")
    return {
        "challenge_id": challenge_id,
        "challenge_type": challenge_type,
        "expires_at": expires_at.isoformat(),
        "instructions": {
            "look_left": "Please turn your head slightly to the left",
            "look_right": "Please turn your head slightly to the right",
            "nod": "Please nod your head up and down",
            "blink": "Please blink naturally 2-3 times"
        }[challenge_type],
        "timeout": expiration_seconds
    }

@app.websocket("/ws/video-stream/{session_id}")
async def video_stream_websocket(websocket: WebSocket, session_id: str, challenge_id: str = None):
    await websocket.accept()
    logger.info(f"Video stream WebSocket connected for session {session_id}")
    
    # Initialize user analytics data
    user_analytics[session_id] = {
        "gaze": [],
        "posture": [],
        "voice": [],
        "env_noise": [],
        "face": [],
        "start_time": time.time(),
    }
    
    try:
        while True:
            message = await websocket.receive_json()
            msg_type = message.get('type')
            logger.info(f"[WS] Received message type: {msg_type} for session {session_id}")

            if msg_type == "liveness_check":
                # If no challenge_type provided, create a random challenge
                if not message.get('challenge_id'):
                    challenge = await create_random_challenge()
                    logger.info(f"[WS] Created new random challenge for session {session_id}")
                    await websocket.send_json({
                        'type': 'liveness_challenge',
                        **challenge
                    })
                    continue

                # Process frame for existing challenge
                frame_data = message.get('data')
                challenge_id = message.get('challenge_id')
                challenge_type = message.get('challenge_type')
                # ...rest of the liveness frame processing code...
            else:
                await websocket.send_json({"type": "error", "message": "Unknown message type"})
    except WebSocketDisconnect:
        logger.info(f"Session {session_id} WebSocket disconnected.")
    except Exception as e:
        logger.error(f"Error in session {session_id} WebSocket: {e}")

@app.post("/auth/request-challenge")
async def request_challenge(request: ChallengeRequest):
    """Request a new liveness challenge"""
    # Generate a unique challenge ID
    challenge_id = str(uuid.uuid4())
    
    # Choose a random challenge type
    challenge_types = ["look_left", "look_right", "blink"]
    challenge_type = np.random.choice(challenge_types)
    
    # Create challenge instructions based on type
    instructions = {
        "look_left": "Please turn your head slightly to the left",
        "look_right": "Please turn your head slightly to the right",
        "blink": "Please blink naturally 2-3 times"
    }[challenge_type]
    
    # Set expiration time (45 seconds for blink challenges, 30 for others)
    expiration_seconds = 45 if challenge_type == "blink" else 30
    expires_at = datetime.now() + timedelta(seconds=expiration_seconds)
    
    # Initialize tracking for this challenge
    reset_challenge_tracking(challenge_id)
    
    # Store challenge in session
    challenge_sessions[challenge_id] = {
        "user_id": request.user_id,
        "type": challenge_type,
        "expires_at": expires_at,
        "completed": False,
        "attempts": 0
    }
    
    return ChallengeResponse(
        challenge_id=challenge_id,
        challenge_type=challenge_type,
        expires_at=expires_at.isoformat(),
        instructions=instructions
    )

@app.post("/auth/check-liveness")
async def check_liveness(request: Request):
    """Check liveness from video frame with enhanced blink detection"""
    # Get form data
    form_data = await request.form()
    challenge_id = form_data.get("challenge_id")
    video_frame = await form_data.get("video_frame").read()
    
    # Check if challenge exists
    if challenge_id not in challenge_sessions:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    challenge = challenge_sessions[challenge_id]
    
    # Check if challenge has expired
    if datetime.now() > challenge["expires_at"]:
        raise HTTPException(status_code=400, detail="Challenge has expired")
    
    # Convert image bytes to numpy array
    nparr = np.frombuffer(video_frame, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    # Enhanced blink detection
    blink_detected, landmarks, current_ear = detect_blink_robust(frame, challenge_id)
    
    if landmarks is None:
        raise HTTPException(status_code=400, detail="No face detected")
    
    # Increment attempt counter
    challenge["attempts"] += 1
    
    # Perform challenge validation
    challenge_passed = False
    debug_info = get_challenge_debug_info(challenge_id)
    
    if challenge["type"] == "blink":
        challenge_passed = validate_challenge(challenge_id, landmarks, challenge["type"])
        logger.info(f"Blink challenge {challenge_id}: passed={challenge_passed}, "
                   f"state={debug_info['current_state']}, ear={current_ear:.3f}")
    elif challenge["type"] in ["look_left", "look_right"]:
        challenge_passed = validate_challenge(challenge_id, landmarks, challenge["type"])
    
    # Update challenge status
    if challenge_passed:
        challenge_sessions[challenge_id]["completed"] = True
    
    # Additional anti-spoofing checks
    # 1. Check for natural micro-movements
    has_natural_movement = True  # Simplified for demo, implement proper check
    
    # 2. Check for texture patterns that might indicate printed face
    texture_check_passed = True  # Simplified for demo, implement proper check
    
    # Combined result
    liveness_verified = challenge_passed and has_natural_movement and texture_check_passed
    
    # Prepare response message
    message = "Liveness verified" if liveness_verified else "Liveness check failed"
    if challenge["type"] == "blink" and not challenge_passed:
        if debug_info['current_state'] == "UNKNOWN":
            message = "Please look directly at the camera and blink naturally"
        elif debug_info['current_state'] == "OPEN":
            message = "Blink detected, but challenge not yet complete. Please blink again."
        else:
            message = "Processing blink... Please wait"
    
    return JSONResponse({
        "success": liveness_verified,
        "challenge_completed": challenge_passed,
        "message": message,
        "debug": {
            "ear_value": current_ear,
            "attempts": challenge["attempts"],
            "challenge_type": challenge["type"],
            "blink_state": debug_info
        }
    })

@app.get("/auth/challenge/{challenge_id}/status")
async def get_challenge_status(challenge_id: str):
    """Get current status of a challenge"""
    if challenge_id not in challenge_sessions:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    challenge = challenge_sessions[challenge_id]
    debug_info = get_challenge_debug_info(challenge_id)
    
    return {
        "challenge_id": challenge_id,
        "type": challenge["type"],
        "completed": challenge["completed"],
        "expired": datetime.now() > challenge["expires_at"],
        "attempts": challenge.get("attempts", 0),
        "debug": debug_info
    }

@app.post("/auth/challenge/{challenge_id}/reset")
async def reset_challenge(challenge_id: str):
    """Reset a challenge's tracking state"""
    if challenge_id not in challenge_sessions:
        raise HTTPException(status_code=404, detail="Challenge not found")
    
    reset_challenge_tracking(challenge_id)
    challenge_sessions[challenge_id]["completed"] = False
    challenge_sessions[challenge_id]["attempts"] = 0
    
    return {
        "success": True,
        "message": "Challenge tracking reset successfully"
    }

# ============== ROOT ENDPOINT ==============

@app.get("/")
async def root():
    return {"message": "AI Assessment Proctoring API with Enhanced Liveness Detection is running"}

# ============== MAIN ==============

if __name__ == "__main__":
    uvicorn.run("liveness_detection:app", host="0.0.0.0", port=8001, reload=True)

__all__ = [
    'detect_blink',
    'detect_blink_robust',
    'calculate_ear',
    'distance',
    'check_head_movement',
    'validate_challenge',
    'reset_challenge_tracking',
    'get_challenge_debug_info',
    'face_mesh',
    'LEFT_EYE_INDICES',
    'RIGHT_EYE_INDICES',
    'BlinkState',
]