# --- Imports and Logging Setup ---
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import asyncio
import json
import logging
import base64
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
import threading
from concurrent.futures import ThreadPoolExecutor
import queue
import numpy as np
import cv2
import tempfile
import os
from pathlib import Path
import aiofiles
import time
import random
import shutil

# Import routers and processing functions
from object import router as object_router, detect_objects_from_frame
from face_verify import router as face_router, process_face_enrollment_async, verify_faces_async
from environ_noise import router as noise_router, predict_audio_full, SAMPLE_RATE, ACCEPTED_LABELS
from gaze_posture import router as gaze_router, analyze_gaze, analyze_posture
from liveness_detection import router as liveness_router, detect_blink, calculate_ear, distance, check_head_movement, validate_challenge, face_mesh, LEFT_EYE_INDICES, RIGHT_EYE_INDICES
from voice import router as voice_router, process_audio_for_enrollment, process_audio_for_verification, create_wav_file

# --- Logging Configuration ---
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('proctoring_logs.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- FastAPI App Setup ---
app = FastAPI(
    title="AI Proctoring Assessment System",
    description="Real-time AI-powered proctoring for online assessments",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers ---
app.include_router(object_router, prefix="/api/object", tags=["Object Detection"])
app.include_router(face_router, prefix="/api/face", tags=["Face Verification"])
app.include_router(noise_router, prefix="/api/noise", tags=["Environment Monitoring"])
app.include_router(gaze_router, prefix="/api/gaze", tags=["Gaze & Posture Tracking"])
app.include_router(liveness_router, prefix="/api/liveness", tags=["Liveness Detection"])
app.include_router(voice_router, prefix="/api/voice", tags=["Voice Authentication"])

# --- Global State ---
active_sessions: Dict[str, "ProctoringSession"] = {}
processing_executor = ThreadPoolExecutor(max_workers=15)

PROCTORING_CONFIG = {
    "max_gaze_away_duration": 10,  # seconds
    "max_noise_incidents": 3,
    "prohibited_objects": {"cell phone", "book", "paper", "laptop", "tablet"},
    "min_face_confidence": 0.7,
    "max_people_allowed": 1,
    "alert_thresholds": {
        "gaze_away": 5,  # seconds before alert
        "noise_level": 0.8,
        "face_not_detected": 3,  # seconds
        "multiple_faces": 1  # immediate alert
    }
}


class ProctoringSession:
    def __init__(self, session_id: str, candidate_id: str, exam_id: str):
        self.session_id = session_id
        self.candidate_id = candidate_id
        self.exam_id = exam_id
        self.websocket: Optional[WebSocket] = None
        
        # Session state
        self.status = "initialized"  # initialized, pre_assessment, active, paused, completed
        self.start_time = None
        self.end_time = None
        self.is_authenticated = False
        
        # Pre-assessment results
        self.liveness_verified = False
        self.face_enrolled = False
        self.voice_enrolled = False
        self.environment_verified = False
        self.candidate_reference_image = None
        # Real-time monitoring data
        self.violations = []
        self.alerts = []
        self.monitoring_data = {
            'gaze_tracking': [],
            'posture_analysis': [],
            'noise_levels': [],
            'object_detections': [],
            'face_verifications': [],
            'voice_verifications': [],
            'liveness_checks': []
        }
        
        # Behavioral analytics
        self.behavior_metrics = {
            'total_gaze_away_time': 0,
            'noise_incidents': 0,
            'unauthorized_objects_detected': 0,
            'face_verification_failures': 0,
            'voice_verification_failures':0,
            'suspicious_activities': 0,
            'attention_score': 100.0,
            'integrity_score': 100.0
        }
        
        # Session files
        self.session_dir = Path(f"sessions/{session_id}")
        self.session_dir.mkdir(parents=True, exist_ok=True)

        self.real_time_alerts = []
        self.alert_queue = asyncio.Queue()
        self.monitoring_active = False
        
        # Alert configuration
        self.alert_config = {
            'unauthorized_object': {'cooldown': 5, 'max_per_minute': 3},
            'multiple_faces': {'cooldown': 2, 'max_per_minute': 5},
            'environmental_noise': {'cooldown': 10, 'max_per_minute': 2},
            'face_not_detected': {'cooldown': 3, 'max_per_minute': 4}
        }
        
        # Alert tracking
        self.alert_timestamps = {}
        self.last_alerts = {}
    def get_pre_assessment_progress(self):
        steps = {
        'liveness_check': {
            'completed': self.liveness_verified,
            'status': 'passed' if self.liveness_verified else 'pending',
            'description': 'Verify you are a real person'
        },
        'face_enrollment': {
            'completed': self.face_enrolled,
            'status': 'passed' if self.face_enrolled else 'pending',
            'description': 'Register your face for identity verification'
        },
        'voice_enrollment': {
            'completed': self.voice_enrolled,
            'status': 'passed' if self.voice_enrolled else 'pending',
            'description': 'Register your voice for authentication'
        },
        'environment_check': {
            'completed': self.environment_verified,
            'status': 'passed' if self.environment_verified else 'pending',
            'description': 'Verify your testing environment'
        }
    }
        completed_count = sum(1 for step in steps.values() if step['completed'])
        total_steps = len(steps)
        return {
        'steps': steps,
        'progress_percentage': (completed_count / total_steps) * 100,
        'completed_steps': completed_count,
        'total_steps': total_steps,
        'all_complete': completed_count == total_steps
    }
    
    async def send_real_time_alert(self, alert_type: str, severity: str, message: str, metadata: dict = None):
        """Send immediate alert to frontend with cooldown logic"""
        current_time = time.time()
        
        # Check cooldown
        if alert_type in self.last_alerts:
            time_since_last = current_time - self.last_alerts[alert_type]
            cooldown = self.alert_config.get(alert_type, {}).get('cooldown', 5)
            
            if time_since_last < cooldown:
                return  # Skip alert due to cooldown
        
        # Check rate limiting
        minute_ago = current_time - 60
        if alert_type not in self.alert_timestamps:
            self.alert_timestamps[alert_type] = []
        
        # Clean old timestamps
        self.alert_timestamps[alert_type] = [
            ts for ts in self.alert_timestamps[alert_type] if ts > minute_ago
        ]
        
        max_per_minute = self.alert_config.get(alert_type, {}).get('max_per_minute', 3)
        if len(self.alert_timestamps[alert_type]) >= max_per_minute:
            return  # Rate limit exceeded
        
        # Create alert
        alert = {
            'id': str(uuid.uuid4()),
            'type': 'real_time_alert',
            'alert_type': alert_type,
            'severity': severity,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'metadata': metadata or {}
        }
        
        # Update tracking
        self.last_alerts[alert_type] = current_time
        self.alert_timestamps[alert_type].append(current_time)
        self.real_time_alerts.append(alert)
        
        # Send to frontend immediately
        if self.websocket:
            try:
                await self.websocket.send_text(json.dumps(to_native(alert)))
                logger.info(f"Real-time alert sent: {alert_type} - {message}")
            except Exception as e:
                logger.error(f"Failed to send alert: {str(e)}")
        
        # Also log as violation
        await self.log_violation(alert_type, severity, message, metadata)
        
    async def log_violation(self, violation_type: str, severity: str, description: str, metadata: dict = None):
        """Log proctoring violations"""
        violation = {
            'id': str(uuid.uuid4()),
            'timestamp': datetime.now().isoformat(),
            'session_id': self.session_id,
            'candidate_id': self.candidate_id,
            'violation_type': violation_type,
            'severity': severity,  # low, medium, high, critical
            'description': description,
            'metadata': metadata or {}
        }
        self.violations.append(violation)
        logger.warning(f"Violation logged: {violation_type} - {description}")
        # Send real-time alert to monitoring dashboard
        if self.websocket:
            await self.websocket.send_text(json.dumps(to_native({
                'type': 'violation_alert',
                'violation': violation
            })))
    
    async def update_behavior_metrics(self, metric_type: str, value: Any):
        """Update behavioral metrics and scores"""
        if metric_type == 'gaze_away_duration':
            self.behavior_metrics['total_gaze_away_time'] += value
            if self.behavior_metrics['total_gaze_away_time'] > PROCTORING_CONFIG['max_gaze_away_duration']:
                await self.log_violation(
                    'gaze_violation', 'high', 
                    f'Excessive gaze away time: {self.behavior_metrics["total_gaze_away_time"]}s'
                )
        
        elif metric_type == 'noise':
            self.behavior_metrics['noise_incidents'] += 1
            if self.behavior_metrics['noise_incidents'] > PROCTORING_CONFIG['max_noise_incidents']:
                await self.log_violation(
                    'environment_violation', 'medium',
                    f'Excessive noise incidents: {self.behavior_metrics["noise_incidents"]}'
                )
        
        elif metric_type == 'unauthorized_object':
            self.behavior_metrics['unauthorized_objects_detected'] += 1
            await self.log_violation(
                'object_violation', 'critical',
                f'Unauthorized object detected: {value}',
                {'object_type': value}
            )
        
        elif metric_type == 'face_verification_failure':
            self.behavior_metrics['face_verification_failures'] += 1
            await self.log_violation(
                'identity_violation', 'critical',
                'Face verification failed - potential impersonation'
            )
        
        elif metric_type == 'voice_verification_failure':
            self.behavior_metrics['voice_verification_failures'] += 1
            await self.log_violation(
                'identity_violation', 'critical',
                'Voice verification failed - potential impersonation'
            )
        # Update integrity and attention scores
        self._update_scores()
    
    def _update_scores(self):
        """Update attention and integrity scores based on behavior metrics"""
        # Attention score calculation
        base_attention = 100.0
        gaze_penalty = min(self.behavior_metrics['total_gaze_away_time'] * 2, 50)
        noise_penalty = min(self.behavior_metrics['noise_incidents'] * 5, 30)
        
        self.behavior_metrics['attention_score'] = max(0, base_attention - gaze_penalty - noise_penalty)
        
        # Integrity score calculation
        base_integrity = 100.0
        object_penalty = self.behavior_metrics['unauthorized_objects_detected'] * 25
        identity_penalty = self.behavior_metrics['face_verification_failures'] * 30
        
        self.behavior_metrics['integrity_score'] = max(0, base_integrity - object_penalty - identity_penalty)
    
    def get_noise_threshold(self):
        """Return the noise threshold for this session. Can be made dynamic per session if needed."""
        # You can make this configurable per session if needed
        return 0.3


# --- WebSocket Endpoint ---
@app.websocket("/ws/proctoring/{session_id}")
async def proctoring_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    if session_id not in active_sessions:
        await websocket.send_text(json.dumps({
            'type': 'error',
            'message': 'Session not found. Please start a new proctoring session.'
        }))
        await websocket.close()
        return
    session = active_sessions[session_id]
    session.websocket = websocket
    logger.info(f"Proctoring WebSocket connected for session: {session_id}")
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            message_type = message.get('type')
            if message_type == 'start_pre_assessment':
                await handle_pre_assessment_start(session, message)
            elif message_type == 'liveness_check':
                await handle_liveness_check(session, message)
            elif message_type == 'face_enrollment':
                await handle_face_enrollment(session, message)
            elif message_type == 'voice_enrollment':
                await handle_voice_enrollment(session, message)
            elif message_type == 'environment_check':
                await handle_environment_check(session, message)
            elif message_type == 'start_assessment':
                await handle_assessment_start(session, message)
            elif message_type == 'video_stream':
                await handle_video_monitoring(session, message)
            elif message_type == 'audio_stream':
                await handle_audio_monitoring(session, message)
            elif message_type == 'pause_assessment':
                await handle_assessment_pause(session, message)
            elif message_type == 'resume_assessment':
                await handle_assessment_resume(session, message)
            elif message_type == 'end_assessment':
                await handle_assessment_end(session, message)
            elif message_type == 'heartbeat':
                await websocket.send_text(json.dumps({'type': 'heartbeat_ack'}))
    except WebSocketDisconnect:
        logger.info(f"Proctoring WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Proctoring WebSocket error: {str(e)}")
        await session.log_violation('system_error', 'medium', f'WebSocket error: {str(e)}')
    finally:
        if session.websocket == websocket:
            session.websocket = None


# --- Session Management Endpoints ---
@app.post("/api/proctoring/session/create")
async def create_proctoring_session(session_data: dict):
    """Create a new proctoring session"""
    session_id = str(uuid.uuid4())
    candidate_id = session_data.get('candidate_id')
    exam_id = session_data.get('exam_id')
    
    if not candidate_id or not exam_id:
        raise HTTPException(status_code=400, detail="candidate_id and exam_id are required")
    
    session = ProctoringSession(session_id, candidate_id, exam_id)
    active_sessions[session_id] = session
    
    logger.info(f"Created proctoring session: {session_id} for candidate: {candidate_id}")
    
    return {
        "session_id": session_id,
        "candidate_id": candidate_id,
        "exam_id": exam_id,
        "status": "created",
        "websocket_url": f"/ws/proctoring/{session_id}"
    }


@app.get("/api/proctoring/session/{session_id}/status")
async def get_session_status(session_id: str):
    """Get current session status"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    return {
        "session_id": session_id,
        "status": session.status,
        "candidate_id": session.candidate_id,
        "exam_id": session.exam_id,
        "is_authenticated": session.is_authenticated,
        "pre_assessment_complete": all([
            session.liveness_verified,
            session.face_enrolled,
            session.voice_enrolled,
            session.environment_verified
        ]),
        "violations_count": len(session.violations),
        "behavior_metrics": session.behavior_metrics
    }


# --- Pre-assessment handlers ---
# Enhanced pre-assessment handlers
async def handle_pre_assessment_start(session: ProctoringSession, message: dict):
    """Start pre-assessment phase with progress tracking"""
    session.status = "pre_assessment"
    progress = session.get_pre_assessment_progress()
    
    await session.websocket.send_text(json.dumps({
        'type': 'pre_assessment_started',
        'message': 'Starting pre-assessment verification',
        'progress': progress,
        'instructions': {
            'liveness_check': 'Look directly at the camera and blink normally',
            'face_enrollment': 'Position your face clearly in the camera frame',
            'voice_enrollment': 'Speak clearly for 5-10 seconds',
            'environment_check': 'Ensure good lighting and minimal background noise'
        }
    }))


async def handle_liveness_check(session: ProctoringSession, message: dict):
    """Handle liveness detection using updated logic and send challenge instructions"""
    try:
        image_data = message.get('image_data')
        challenge_type = message.get('challenge_type')
        challenge_id = message.get('challenge_id', None)
        # If no challenge_type, pick a random one
        if not challenge_type:
            challenge_type = random.choice(['blink', 'look_left', 'look_right'])
        # If no image_data, this is a request to start a challenge
        if not image_data:
            # Always generate a new challenge_id for each challenge
            challenge_id = str(uuid.uuid4())
            instructions_map = {
                'blink': 'Please blink your eyes normally while looking at the camera.',
                'look_left': 'Please turn your head to the LEFT while looking at the camera.',
                'look_right': 'Please turn your head to the RIGHT while looking at the camera.'
            }
            instructions = instructions_map.get(challenge_type, 'Please follow the liveness challenge instructions.')
            # Store the challenge as active for this session
            if not hasattr(session, 'active_liveness_challenge'):
                session.active_liveness_challenge = {}
            session.active_liveness_challenge = {
                'challenge_id': challenge_id,
                'challenge_type': challenge_type,
                'start_time': time.time(),
                'completed': False,
                'timeout': 30.0,
                'failed': False
            }
            await session.websocket.send_text(json.dumps({
                'type': 'liveness_challenge',
                'challenge_type': challenge_type,
                'challenge_id': challenge_id,
                'instructions': instructions,
                'timeout': 30
            }))
            return
        # Only process frames if a challenge is active and not completed/failed
        if not hasattr(session, 'active_liveness_challenge') or not session.active_liveness_challenge:
            await session.websocket.send_text(json.dumps({
                'type': 'liveness_check_result',
                'status': 'error',
                'challenge_type': challenge_type,
                'message': 'No active liveness challenge. Please request a new challenge.'
            }))
            return
        active = session.active_liveness_challenge
        # Only accept frames for the current challenge_id
        if challenge_id != active['challenge_id']:
            await session.websocket.send_text(json.dumps({
                'type': 'liveness_check_result',
                'status': 'error',
                'challenge_type': challenge_type,
                'message': 'Challenge ID mismatch. Please retry the current challenge.'
            }))
            return
        # Check if challenge has already been completed or failed
        if active.get('completed'):
            await session.websocket.send_text(json.dumps({
                'type': 'liveness_check_result',
                'status': 'passed',
                'challenge_type': challenge_type,
                'message': 'Challenge already completed.'
            }))
            return
        if active.get('failed'):
            await session.websocket.send_text(json.dumps({
                'type': 'liveness_check_result',
                'status': 'failed',
                'challenge_type': challenge_type,
                'message': 'Challenge already failed.'
            }))
            return
        # Give the user up to 30 seconds to perform the challenge
        elapsed = time.time() - active['start_time']
        if elapsed > active['timeout']:
            session.active_liveness_challenge['failed'] = True
            await session.websocket.send_text(json.dumps({
                'type': 'liveness_check_result',
                'status': 'failed',
                'challenge_type': challenge_type,
                'message': 'Liveness challenge timed out. Please try again.'
            }))
            await session.log_violation(
                'liveness_timeout', 'high',
                'Liveness challenge timed out.'
            )
            return
        # Process the liveness check
        image_bytes = base64.b64decode(image_data.split(',')[1])
        temp_path = session.session_dir / f"liveness_{int(time.time())}.jpg"
        with open(temp_path, 'wb') as f:
            f.write(image_bytes)
        liveness_result = await process_liveness_detection(str(temp_path), challenge_type, challenge_id)
        if liveness_result.get('success', False):
            session.liveness_verified = True
            session.monitoring_data['liveness_checks'].append({
                'timestamp': datetime.now().isoformat(),
                'result': 'passed',
                'challenge_type': challenge_type,
                'challenge_completed': liveness_result.get('challenge_completed', False),
                'message': liveness_result.get('message', '')
            })
            session.active_liveness_challenge['completed'] = True
            await session.websocket.send_text(json.dumps({
                'type': 'liveness_check_result',
                'status': 'passed',
                'challenge_type': challenge_type,
                'message': liveness_result.get('message', 'Liveness verification successful')
            }))
        else:
            # Do not fail immediately, just send feedback (user can keep trying until timeout)
            await session.websocket.send_text(json.dumps({
                'type': 'liveness_check_result',
                'status': 'pending',
                'challenge_type': challenge_type,
                'message': liveness_result.get('message', 'Liveness check not yet successful. Please try again.')
            }))
    except Exception as e:
        logger.error(f"Liveness check error: {str(e)}")
        await session.websocket.send_text(json.dumps({
            'type': 'liveness_check_result',
            'status': 'error',
            'challenge_type': challenge_type,
            'message': f'Liveness check error: {str(e)}'
        }))
        await session.log_violation('system_error', 'medium', f'Liveness check error: {str(e)}')

async def handle_face_enrollment(session: ProctoringSession, message: dict):
    """Handle face enrollment for identity verification"""
    try:
        image_data = message.get('image_data')
        if not image_data:
            await session.websocket.send_text(json.dumps({
                'type': 'face_enrollment_result',
                'status': 'failed',
                'message': 'No image data provided'
            }))
            return
            
        # Save candidate reference image
        try:
            # Handle base64 image data
            if ',' in image_data:
                image_bytes = base64.b64decode(image_data.split(',')[1])
            else:
                image_bytes = base64.b64decode(image_data)
                
            reference_path = session.session_dir / "candidate_reference.jpg"
            
            with open(reference_path, 'wb') as f:
                f.write(image_bytes)
                
            logger.info(f"Saved reference image to: {reference_path}")
            
        except Exception as decode_error:
            logger.error(f"Image decoding error: {str(decode_error)}")
            await session.websocket.send_text(json.dumps({
                'type': 'face_enrollment_result',
                'status': 'failed',
                'message': 'Failed to decode image data'
            }))
            return
        
        # Verify face quality and enrollment
        enrollment_result = await process_face_enrollment(str(reference_path))
        
        if enrollment_result.get('success', False):
            session.face_enrolled = True
            session.candidate_reference_image = str(reference_path)
            
            await session.websocket.send_text(json.dumps({
                'type': 'face_enrollment_result',
                'status': 'success',
                'message': 'Face enrollment successful',
                'quality_score': enrollment_result.get('quality_score', 0.0),
                'details': enrollment_result.get('message', '')
            }))
            
            logger.info(f"Face enrollment successful for session {session.session_id}")
            
        else:
            await session.websocket.send_text(json.dumps({
                'type': 'face_enrollment_result',
                'status': 'failed',
                'message': enrollment_result.get('error', 'Face enrollment failed - please try again'),
                'quality_score': enrollment_result.get('quality_score', 0.0)
            }))
            
            logger.warning(f"Face enrollment failed for session {session.session_id}: {enrollment_result.get('error', 'Unknown error')}")
            
    except Exception as e:
        logger.error(f"Face enrollment error: {str(e)}")
        await session.websocket.send_text(json.dumps({
            'type': 'face_enrollment_result',
            'status': 'failed',
            'message': 'Face enrollment process failed due to server error'
        }))

# --- AUDIO DOWNLOAD ENDPOINT ---
@app.get("/api/proctoring/audio/{session_id}/{purpose}")
async def download_audio(session_id: str, purpose: str):
    """Download the last enrolled or verified audio for a session (purpose: 'enrollment' or 'verification')"""
    session_dir = Path("sessions") / session_id
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    files = sorted(session_dir.glob(f"{purpose}_*.wav"), key=os.path.getmtime, reverse=True)
    if not files:
        raise HTTPException(status_code=404, detail="No audio file found for this purpose")
    return FileResponse(str(files[0]), media_type="audio/wav", filename=files[0].name)

# --- ENHANCED VOICE ENROLLMENT ---
async def handle_voice_enrollment(session: ProctoringSession, message: dict):
    """Handle voice enrollment for voice verification, save audio for inspection, and log embedding."""
    try:
        audio_data = message.get('audio_data')
        if audio_data:
            # Decode base64 audio data and save as a temporary WAV file
            audio_bytes = base64.b64decode(audio_data)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
                temp_wav.write(audio_bytes)
                temp_wav_path = temp_wav.name
            logger.info(f"[Session {session.session_id}] Enrollment audio saved to {temp_wav_path}")
            # Save a copy for inspection
            session_dir = Path("sessions") / session.session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            enrolled_path = session_dir / f"enrollment_{int(time.time())}.wav"
            shutil.copy(temp_wav_path, enrolled_path)
            logger.info(f"[Session {session.session_id}] Enrollment audio copied to {enrolled_path}")
            enrollment_result = await process_voice_enrollment(session.candidate_id, temp_wav_path)
            logger.info(f"[Session {session.session_id}] Enrollment embedding: {enrollment_result.get('embedding')}")
            if enrollment_result.get('success', False):
                session.voice_enrolled = True
                await session.websocket.send_text(json.dumps({
                    'type': 'voice_enrollment_result',
                    'status': 'success',
                    'message': 'Voice enrollment successful'
                }))
                logger.info(f"[Session {session.session_id}] Voice enrollment successful for candidate {session.candidate_id}")
            else:
                await session.websocket.send_text(json.dumps({
                    'type': 'voice_enrollment_result',
                    'status': 'failed',
                    'message': 'Voice enrollment failed - please try again'
                }))
                logger.warning(f"[Session {session.session_id}] Voice enrollment failed for candidate {session.candidate_id}")
            os.remove(temp_wav_path)
        else:
            await session.websocket.send_text(json.dumps({
                'type': 'voice_enrollment_result',
                'status': 'failed',
                'message': 'No audio data received'
            }))
    except Exception as e:
        logger.error(f"Voice enrollment error: {str(e)}")
        await session.websocket.send_text(json.dumps({
            'type': 'voice_enrollment_result',
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }))

# --- ENHANCED VOICE VERIFICATION ---
async def process_voice_verification(session: ProctoringSession, message: dict):
    """Voice verification with strict audio format validation, save audio for inspection, and log embedding."""
    try:
        audio_data = message.get('audio_data')
        if not audio_data:
            await session.websocket.send_text(json.dumps({
                'type': 'voice_verification_result',
                'status': 'failed',
                'message': 'No audio data received'
            }))
            return
        # Decode base64 audio data and save as a temporary WAV file
        audio_bytes = base64.b64decode(audio_data)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
            temp_wav.write(audio_bytes)
            temp_wav_path = temp_wav.name
        logger.info(f"[Session {session.session_id}] Verification audio saved to {temp_wav_path}")
        # Save a copy for inspection
        session_dir = Path("sessions") / session.session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        verified_path = session_dir / f"verification_{int(time.time())}.wav"
        shutil.copy(temp_wav_path, verified_path)
        logger.info(f"[Session {session.session_id}] Verification audio copied to {verified_path}")
        result = await process_voice_verification(session, temp_wav_path)
        logger.info(f"[Session {session.session_id}] Verification embedding: {result.get('embedding')}")
        await session.websocket.send_text(json.dumps({
            'type': 'voice_verification_result',
            **result
        }))
        os.remove(temp_wav_path)
    except Exception as e:
        logger.error(f"Voice verification error: {str(e)}")
        await session.websocket.send_text(json.dumps({
            'type': 'voice_verification_result',
            'status': 'error',
            'message': f'Internal server error: {str(e)}'
        }))

async def handle_environment_check(session: ProctoringSession, message: dict):
    """Environment verification with only camera and microphone access checks and debug logging"""
    try:
        # Log the incoming payload for debugging
        logger.info(f"Received environment check payload: {message}")

        # Try to extract camera/microphone from room_scan if present
        camera_access = message.get('camera_access', None)
        microphone_access = message.get('microphone_access', None)
        # If not present, try to parse from room_scan
        if (camera_access is None or microphone_access is None) and 'room_scan' in message:
            try:
                room_scan = message['room_scan']
                if isinstance(room_scan, str):
                    room_scan = json.loads(room_scan)
                camera_access = room_scan.get('camera', False)
                microphone_access = room_scan.get('microphone', False)
            except Exception as e:
                logger.warning(f"Failed to parse room_scan: {e}")
                camera_access = False
                microphone_access = False
        # Fallback to False if still None
        if camera_access is None:
            camera_access = False
        if microphone_access is None:
            microphone_access = False

        # Only check camera and microphone access
        checks = {
            'camera_access': camera_access,
            'microphone_access': microphone_access
        }
        
        violations = []
        recommendations = []
        
        if not checks['camera_access']:
            violations.append('Camera access denied')
            recommendations.append('Please allow camera access and refresh the page')
        
        if not checks['microphone_access']:
            violations.append('Microphone access denied')
            recommendations.append('Please allow microphone access and refresh the page')
        
        environment_suitable = len(violations) == 0
        
        if environment_suitable:
            session.environment_verified = True
            
        # Send detailed feedback, including the raw payload for debugging
        await session.websocket.send_text(json.dumps({
            'type': 'environment_check_result',
            'status': 'approved' if environment_suitable else 'issues_found',
            'message': 'Environment suitable for testing' if environment_suitable else 'Environment issues detected',
            'checks': checks,
            'violations': violations,
            'recommendations': recommendations,
            'progress': session.get_pre_assessment_progress(),
            'debug_payload': message  # Echo back the received payload for debugging
        }))
        
        # Always send environment_check_result for frontend logging
        await session.websocket.send_text(json.dumps({
            'type': 'environment_check_result',
            'status': 'approved' if environment_suitable else 'issues_found',
            'message': 'Environment suitable for testing' if environment_suitable else 'Environment issues detected',
            'checks': checks,
            'violations': violations,
            'recommendations': recommendations,
            'progress': session.get_pre_assessment_progress(),
            'debug_payload': message
        }))
        
        # Check if all pre-assessment steps are complete
        if session.get_pre_assessment_progress()['all_complete']:
            session.is_authenticated = True
            
            await session.websocket.send_text(json.dumps({
                'type': 'pre_assessment_complete',
                'status': 'success',
                'message': 'All pre-assessment checks passed. Ready to start exam.',
                'next_action': 'start_assessment'
            }))
            
    except Exception as e:
        logger.error(f"Environment check error: {str(e)}")
        await session.websocket.send_text(json.dumps({
            'type': 'environment_check_result',
            'status': 'error',
            'message': f'Environment check failed: {str(e)}'
        }))

async def handle_assessment_pause(session: ProctoringSession, message: dict):
    """Pause the assessment and update session status."""
    try:
        session.status = "paused"
        await session.websocket.send_text(json.dumps({
            'type': 'assessment_paused',
            'status': 'paused',
            'message': 'Assessment has been paused.'
        }))
        logger.info(f"Assessment paused for session: {session.session_id}")
    except Exception as e:
        logger.error(f"Error pausing assessment: {str(e)}")
        await session.websocket.send_text(json.dumps({
            'type': 'assessment_pause_error',
            'status': 'error',
            'message': f'Failed to pause assessment: {str(e)}'
        }))

async def handle_assessment_resume(session: ProctoringSession, message: dict):
    """Resume the assessment and update session status."""
    try:
        session.status = "active"
        await session.websocket.send_text(json.dumps({
            'type': 'assessment_resumed',
            'status': 'active',
            'message': 'Assessment has been resumed.'
        }))
        logger.info(f"Assessment resumed for session: {session.session_id}")
    except Exception as e:
        logger.error(f"Error resuming assessment: {str(e)}")
        await session.websocket.send_text(json.dumps({
            'type': 'assessment_resume_error',
            'status': 'error',
            'message': f'Failed to resume assessment: {str(e)}'
        }))

async def handle_assessment_start(session: ProctoringSession, message: dict):
    """Start the assessment phase and initialize monitoring."""
    try:
        session.status = "active"
        session.start_time = datetime.now()
        await session.websocket.send_text(json.dumps({
            'type': 'assessment_started',
            'status': 'active',
            'message': 'Assessment started. Real-time monitoring is now active.'
        }))
        # Optionally, you can initialize/reset monitoring data here if needed
        logger.info(f"Assessment started for session: {session.session_id}")
    except Exception as e:
        logger.error(f"Error starting assessment: {str(e)}")
        await session.websocket.send_text(json.dumps({
            'type': 'assessment_start_error',
            'status': 'error',
            'message': f'Failed to start assessment: {str(e)}'
        }))

async def handle_video_monitoring(session: ProctoringSession, message: dict):
    """Handle real-time video monitoring with detailed logging and send all analysis results to frontend"""
    if session.status != "active":
        return
    try:
        video_data = message.get('frame_data')
        if video_data:
            logger.info(f"[Session {session.session_id}] Received video frame for processing.")
            frame_bytes = base64.b64decode(video_data.split(',')[1])
            logger.info(f"[Session {session.session_id}] Decoded video frame, size: {len(frame_bytes)} bytes.")
            tasks = [
                process_gaze_tracking(session, frame_bytes),
                process_posture_analysis(session, frame_bytes),
                process_object_detection(session, frame_bytes),
                process_face_verification(session, frame_bytes)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # print(f"[Session {session.session_id}] Video frame processed. Results: {results}")
            # Send all results to frontend (not just violations)
            if session.websocket:
                try:
                    await session.websocket.send_text(json.dumps(to_native({
                        'type': 'video_analysis',
                        'timestamp': datetime.now().isoformat(),
                        'results': results
                    })))
                except Exception as e:
                    logger.error(f"Failed to send video analysis results: {str(e)}")
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Video processing error: {str(result)}")
                    continue
                if result and result.get('violation'):
                    await session.update_behavior_metrics(
                        result['violation_type'],
                        result.get('value')
                    )
    except Exception as e:
        logger.error(f"Video monitoring error: {str(e)}")
import math

def replace_nan_with_none(obj):
    if isinstance(obj, float) and math.isnan(obj):
        return None
    elif isinstance(obj, dict):
        return {k: replace_nan_with_none(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_nan_with_none(x) for x in obj]
    else:
        return obj
async def handle_audio_monitoring(session: ProctoringSession, message: dict):
    """Handle real-time audio monitoring with detailed logging and send all analysis results to frontend"""
    print(f"[Session {session.session_id}] Entered handle_audio_monitoring. Message keys: {list(message.keys())}")
    if session.status != "active":
        print(f"[Session {session.session_id}] Audio monitoring skipped: session not active.")
        return
    try:
        audio_data = message.get('audio_data')
        print(f"[Session {session.session_id}] audio_data present: {audio_data is not None}, length: {len(audio_data) if audio_data else 0}")
        if audio_data:
            print(f"[Session {session.session_id}] Received audio data for processing.")
            try:
                audio_bytes = base64.b64decode(audio_data)
                print(f"[Session {session.session_id}] Decoded audio data, size: {len(audio_bytes)} bytes.")
            except Exception as decode_err:
                print(f"[Session {session.session_id}] Audio decode error: {str(decode_err)}")
                return
            tasks = [
                process_noise_detection(session, audio_bytes),
                process_voice_verification(session, audio_bytes)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            # Send all results to frontend (not just violations)
            if session.websocket:
                try:
                    safe_results = replace_nan_with_none(results)
                    print(f"[Session {session.session_id}] Audio data processed. Results: {safe_results}")
                    await session.websocket.send_text(json.dumps(to_native({
                        'type': 'audio_analysis',
                        'timestamp': datetime.now().isoformat(),
                        'results': safe_results
                    })))
                except Exception as e:
                    print(f"[Session {session.session_id}] Failed to send audio analysis results: {str(e)}")
            # Remove dedicated environment_noise_result and voice_verification_result messages
            for result in results:
                if isinstance(result, Exception):
                    print(f"[Session {session.session_id}] Audio processing error: {str(result)}")
                    continue
                if result and result.get('violation'):
                    await session.update_behavior_metrics(
                        result['violation_type'],
                        result.get('value')
                    )
        else:
            print(f"[Session {session.session_id}] No audio data received in message.")
    except Exception as e:
        print(f"[Session {session.session_id}] Audio monitoring error: {str(e)}")
        
async def handle_assessment_end(session: ProctoringSession, message: dict):
    """End assessment and generate comprehensive report"""
    session.status = "completed"
    session.end_time = datetime.now()
    # Generate final proctoring report
    report = await generate_proctoring_report(session)
    logger.info(f"Assessment completed for session: {session.session_id}")
    print("\n===== SESSION REPORT =====\n" + json.dumps(report, indent=2) + "\n========================\n")
    await session.websocket.send_text(json.dumps({
        'type': 'assessment_completed',
        'status': 'completed',
        'duration': str(session.end_time - session.start_time),
        'report': report
    }))

# Store previous landmarks for micro-movement check (in-memory, per challenge)
challenge_prev_landmarks = {}

async def process_liveness_detection(image_path: str, challenge_type: str = "blink", challenge_id: str = None) -> dict:
    """Liveness detection logic matching liveness_detection.py/check_liveness, now strict with anti-spoofing"""
    try:
        # Load image
        frame = cv2.imread(image_path)
        if frame is None:
            return {
                'success': False,
                'challenge_completed': False,
                'message': 'Unable to load image'
            }

        # Detect blink and get landmarks
        blink_detected, landmarks = detect_blink(frame, challenge_id)
        if landmarks is None:
            return {
                'success': False,
                'challenge_completed': False,
                'message': 'No face detected'
            }

        # Perform challenge validation
        if challenge_type == "blink":
            challenge_passed = blink_detected
            if not challenge_passed:
                return {
                    'success': False,
                    'challenge_completed': False,
                    'message': 'Blink not detected. Please blink naturally.'
                }
        elif challenge_type in ["look_left", "look_right"]:
            challenge_passed = validate_challenge(challenge_id, landmarks, challenge_type)
            if not challenge_passed:
                return {
                    'success': False,
                    'challenge_completed': False,
                    'message': f'Head not turned {"left" if challenge_type=="look_left" else "right"}. Please follow the instructions.'
                }
        else:
            return {
                'success': False,
                'challenge_completed': False,
                'message': 'Unknown challenge type.'
            }

        # --- Anti-spoofing checks ---
        # 1. Micro-movement: require some movement between frames for the same challenge
        movement_ok = True
        if challenge_id is not None:
            prev = challenge_prev_landmarks.get(challenge_id)
            if prev is not None:
                movement_ok = check_head_movement(landmarks, prev, threshold=0.02)
            challenge_prev_landmarks[challenge_id] = landmarks
        if not movement_ok:
            return {
                'success': False,
                'challenge_completed': True,
                'message': 'No natural micro-movement detected. Please move your head slightly.'
            }

        # 2. Texture check: use variance of Laplacian (blur detection)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        texture_check_passed = laplacian_var > 50  # Threshold: 50 (tune as needed)
        if not texture_check_passed:
            return {
                'success': False,
                'challenge_completed': True,
                'message': 'Texture/anti-spoofing check failed: image appears too smooth or blurry. Please avoid using photos/screens.'
            }

        liveness_verified = challenge_passed and movement_ok and texture_check_passed

        return {
            "success": liveness_verified,
            "challenge_completed": challenge_passed,
            "message": "Liveness verified" if liveness_verified else "Liveness check failed"
        }
    except Exception as e:
        return {
            'success': False,
            'challenge_completed': False,
            'message': f'Error: {str(e)}'
        }
async def process_face_enrollment(image_path: str):
    """
    Integration with face_verify.py
    Process face enrollment with quality assessment
    """
    try:
        # Use the imported function from face_verify.py
        result = await process_face_enrollment_async(image_path)
        
        # Log the result for debugging
        logger.info(f"Face enrollment result: {result}")
        
        return result
        
    except Exception as e:
        logger.error(f"Face enrollment processing error: {str(e)}")
        return {
            'success': False,
            'error': f'Face enrollment processing failed: {str(e)}',
            'quality_score': 0.0
        }
# temp_file_path = create_wav_file(complete_audio)

async def process_voice_enrollment(candidate_id: str, audio_path: str):
    """
    Integration with voice.py
    Enroll a new voice profile using the provided audio file.
    """
    try:
        result = process_audio_for_enrollment(audio_path, candidate_id)
        return {
            'success': True,
            'voice_print_id': candidate_id,
            'message': 'Voice enrollment successful',
            'embedding': result.get('embedding', None)
        }
    except Exception as e:
        logger.error(f"Voice enrollment error: {str(e)}")
        return {
            'success': False,
            'voice_print_id': candidate_id,
            'message': f'Voice enrollment failed: {str(e)}'
        }
    
async def process_environment_check(image_data: str):
    """Check environment suitability based on frontend-provided info (e.g., camera/mic access)"""
    # The frontend should send a JSON string with keys like 'camera', 'microphone', etc.
    try:
        info = json.loads(image_data)
        violations = []
        if not info.get('camera', False):
            violations.append('Camera access denied')
        if not info.get('microphone', False):
            violations.append('Microphone access denied')
        # Add more checks as needed (e.g., lighting, blur, etc.)
        suitable = len(violations) == 0
        return {'suitable': suitable, 'violations': violations}
    except Exception as e:
        return {'suitable': False, 'violations': [f'Environment check error: {str(e)}']}
async def process_gaze_tracking(session: ProctoringSession, frame_bytes: bytes):
    """
    Integration with gaze_posture.py for gaze tracking
    Decodes the frame bytes and uses analyze_gaze to determine if the user is looking away.
    """
    try:
        # Decode image from bytes
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {'violation': True, 'violation_type': 'gaze_tracking_failure', 'value': 1, 'message': 'Invalid frame'}
        result = analyze_gaze(frame)
        if result.get('looking_away', True):
            return {
                'violation': True,
                'violation_type': 'gaze_away',
                'value': 1,
                'message': 'Candidate is looking away',
                'confidence': result.get('confidence', 0.0)
            }
        else:
            return {
                'violation': False,
                'message': 'Gaze is on screen',
                'confidence': result.get('confidence', 0.0)
            }
    except Exception as e:
        logger.error(f"Gaze tracking error: {str(e)}")
        return {
            'violation': True,
            'violation_type': 'gaze_tracking_failure',
            'value': 1,
            'message': f'Gaze tracking error: {str(e)}'
        }

async def process_posture_analysis(session: ProctoringSession, frame_bytes: bytes):
    """
    Integration with gaze_posture.py for posture analysis
    Decodes the frame bytes and uses analyze_posture to determine if the user has proper posture.
    """
    try:
        # Decode image from bytes
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {'violation': True, 'violation_type': 'posture_analysis_failure', 'value': 1, 'message': 'Invalid frame'}
        result = analyze_posture(frame)
        if not result.get('proper_posture', True):
            return {
                'violation': True,
                'violation_type': 'bad_posture',
                'value': 1,
                'message': 'Improper posture detected',
                'confidence': result.get('confidence', 0.0)
            }
        else:
            return {
                'violation': False,
                'message': 'Proper posture',
                'confidence': result.get('confidence', 0.0)
            }
    except Exception as e:
        logger.error(f"Posture analysis error: {str(e)}")
        return {
            'violation': True,
            'violation_type': 'posture_analysis_failure',
            'value': 1,
            'message': f'Posture analysis error: {str(e)}'
        }
async def process_object_detection(session: ProctoringSession, frame_bytes: bytes):
    """Enhanced object detection with immediate alerts"""
    try:
        np_arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            return {'violation': False, 'message': 'Invalid frame'}
        
        # Get object detection results
        result = detect_objects_from_frame(frame)
        detected_objects = result.get('objects', [])
        
        # Check for prohibited objects
        prohibited_found = []
        for obj in detected_objects:
            obj_name = obj.get('name', '').lower()
            confidence = obj.get('confidence', 0)
            
            # Check against prohibited objects with confidence threshold
            for prohibited in PROCTORING_CONFIG['prohibited_objects']:
                if prohibited.lower() in obj_name and confidence > 0.5:
                    prohibited_found.append({
                        'object': obj_name,
                        'confidence': confidence,
                        'coordinates': obj.get('coordinates', {})
                    })
        
        # Send immediate alerts for prohibited objects
        if prohibited_found:
            for obj_info in prohibited_found:
                await session.send_real_time_alert(
                    'unauthorized_object',
                    'critical',
                    f"Unauthorized object detected: {obj_info['object']}",
                    {
                        'object_name': obj_info['object'],
                        'confidence': obj_info['confidence'],
                        'coordinates': obj_info['coordinates'],
                        'frame_timestamp': datetime.now().isoformat()
                    }
                )
            
            return {
                'violation': True,
                'violation_type': 'unauthorized_object',
                'value': len(prohibited_found),
                'message': f"Detected {len(prohibited_found)} unauthorized objects",
                'objects': prohibited_found
            }
        
        return {
            'violation': False,
            'message': 'No prohibited objects detected',
            'total_objects': len(detected_objects)
        }
        
    except Exception as e:
        logger.error(f"Object detection error: {str(e)}")
        await session.send_real_time_alert(
            'system_error',
            'medium',
            f"Object detection system error: {str(e)}"
        )
        return {
            'violation': False,
            'message': f'Object detection error: {str(e)}'
        
        }
async def process_face_verification(session: ProctoringSession, frame_bytes: bytes) -> dict:
    """Enhanced face verification with multiple face detection"""
    try:
        # Save frame bytes to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_img:
            temp_img.write(frame_bytes)
            temp_img_path = temp_img.name
        
        # Use the candidate's reference image for verification
        reference_image = session.candidate_reference_image
        if not reference_image or not os.path.exists(reference_image):
            await session.send_real_time_alert(
                'system_error',
                'high',
                'Reference image missing - cannot verify identity'
            )
            return {'violation': True, 'violation_type': 'face_verification_failure', 'value': 1}
        
        # Call the face verification function
        result = await verify_faces_async(reference_image, temp_img_path)
        os.remove(temp_img_path)
        
        # Check for multiple faces
        faces_count = result.get('faces_detected', 1)
        if faces_count > 1:
            await session.send_real_time_alert(
                'multiple_faces',
                'critical',
                f"Multiple faces detected: {faces_count} people in frame",
                {
                    'faces_count': faces_count,
                    'frame_timestamp': datetime.now().isoformat()
                }
            )
            return {
                'violation': True,
                'violation_type': 'multiple_faces',
                'value': faces_count,
                'message': f'Multiple faces detected: {faces_count}',
                'faces_count': faces_count
            }
        
        # Check for no face detected
        if faces_count == 0:
            await session.send_real_time_alert(
                'face_not_detected',
                'high',
                'No face detected in frame',
                {'frame_timestamp': datetime.now().isoformat()}
            )
            return {
                'violation': True,
                'violation_type': 'face_not_detected',
                'value': 1,
                'message': 'No face detected'
            }
          # Check identity verification
        if not result.get('verified', False):
            distance = result.get('distance', 1.0)
            logger.warning(f"[Session {session.session_id}] Face verification failed with distance: {distance}")
            if distance > 0.8:  # High distance indicates different person
                logger.error(f"[Session {session.session_id}] High distance detected ({distance}), possible impersonation attempt")
                await session.send_real_time_alert(
                    'identity_mismatch',
                    'critical',
                    'Identity verification failed - different person detected',
                    {
                        'verification_distance': distance,
                        'frame_timestamp': datetime.now().isoformat()
                    }
                )
            
            return {
                'violation': True,
                'violation_type': 'face_verification_failure',
                'value': 1,
                'message': 'Face verification failed',
                'distance': distance
            }
          # Log successful verification
        logger.info(f"[Session {session.session_id}] Face verified successfully with distance: {result.get('distance', 0.0)}")
        return {
            'violation': False,
            'message': 'Face verified successfully',
            'distance': result.get('distance', 0.0),
            'faces_count': faces_count
        }
        
    except Exception as e:
        logger.error(f"Face verification error: {str(e)}")
        await session.send_real_time_alert(
            'system_error',
            'medium',
            f"Face verification system error: {str(e)}"
        )
        return {
            'violation': True,
            'violation_type': 'face_verification_failure',
            'value': 1,
            'message': f'Face verification error: {str(e)}'
        }
async def process_noise_detection(session: ProctoringSession, audio_bytes: bytes):
    """Process audio for noise detection with improved buffer handling"""
    try:
        print(f"[Session {session.session_id}] Entered process_noise_detection. Audio bytes length: {len(audio_bytes)}")
        audio_np, error_msg = validate_audio_buffer(audio_bytes)
        print(f"[Session {session.session_id}] Audio buffer after validation: shape={audio_np.shape}, dtype={audio_np.dtype}, min={audio_np.min() if len(audio_np) else 'n/a'}, max={audio_np.max() if len(audio_np) else 'n/a'}, error_msg={error_msg}")
        if len(audio_np) == 0:
            print(f"[Session {session.session_id}] Noise detection audio validation failed: {error_msg}")
            return {
                'violation': False,
                'message': f'Audio validation failed: {error_msg}'
            }
        rms = np.sqrt(np.mean(audio_np**2))
        print(f"[Session {session.session_id}] Calculated RMS: {rms}")
        threshold = 0.1
        print(f"[Session {session.session_id}] Using noise threshold: {threshold}")
        if rms > threshold:
            print(f"[Session {session.session_id}] High noise level detected: {rms:.3f}")
            await session.send_real_time_alert(
                'high_noise',
                'medium',
                'High background noise detected',
                {
                    'noise_level': float(rms),
                    'threshold': float(threshold),
                    'audio_timestamp': datetime.now().isoformat()
                }
            )
            print(f"[Session {session.session_id}] Returning high noise result: rms={rms}, threshold={threshold}")
            return {
                'violation': True,
                'violation_type': 'noise',
                'value': float(rms),
                'threshold': float(threshold),
                'message': 'High background noise detected'
            }
        print(f"[Session {session.session_id}] Normal noise level: {rms:.3f}, returning normal result.")
        return {
            'violation': False,
            'message': 'Normal noise level',
            'value': float(rms),
            'threshold': float(threshold)
        }
    except Exception as e:
        print(f"[Session {session.session_id}] Noise detection error: {str(e)}")
        return {
            'violation': False,
            'message': f'Noise detection error: {str(e)}'
        }
async def process_voice_verification(session: ProctoringSession, audio_bytes: bytes):
    """Enhanced voice verification with robust buffer handling and detailed logging"""
    try:
        if not audio_bytes or len(audio_bytes) == 0:
            print(f"[Session {session.session_id}] Empty audio buffer received")
            return {
                'violation': False,
                'message': 'No audio data received'
            }
        audio_np, error_msg = validate_audio_buffer(audio_bytes)
        print(f"[Session {session.session_id}] Audio buffer stats: shape={audio_np.shape}, dtype={audio_np.dtype}, min={audio_np.min() if len(audio_np) else 'n/a'}, max={audio_np.max() if len(audio_np) else 'n/a'}")
        if len(audio_np) == 0:
            print(f"[Session {session.session_id}] Audio validation failed: {error_msg}")
            return {
                'violation': False,
                'message': f'Audio validation failed: {error_msg}'
            }
        rms = np.sqrt(np.mean(audio_np**2))
        print(f"[Session {session.session_id}] Audio RMS: {rms}")
        if rms < 0.05:
            print(f"[Session {session.session_id}] Insufficient voice activity (RMS: {rms})")
            return {
                'violation': False,
                'message': 'No significant voice activity detected'
            }
        print(f"[Session {session.session_id}] Starting voice verification for candidate_id={session.candidate_id}")
        temp_audio_path = create_wav_file(audio_np.tobytes())
        try:
            candidate_id = session.candidate_id
            result = process_audio_for_verification(temp_audio_path, candidate_id)
            if hasattr(result, '__await__'):
                result = await result
            print(f"[Session {session.session_id}] Voice verification raw result: {result}")
            similarity = result.get('similarity_score', 0.0)
            threshold = result.get('threshold', 0.65)
            match = result.get('match', False)
            if match:
                print(f"[Session {session.session_id}] Voice verified successfully (similarity: {similarity:.3f}, threshold: {threshold})")
                return {
                    'violation': False,
                    'message': 'Voice verified successfully',
                    'similarity_score': similarity,
                    'threshold': threshold
                }
            else:
                print(f"[Session {session.session_id}] Voice verification failed (similarity: {similarity:.3f}, threshold: {threshold})")
                if similarity < threshold:
                    print(f"[Session {session.session_id}] High voice difference detected (similarity: {similarity:.3f}, threshold: {threshold})")
                    await session.send_real_time_alert(
                        'voice_verification_failed',
                        'high',
                        'Voice verification failed - possible impersonation',
                        {
                            'similarity_score': similarity,
                            'threshold': threshold,
                            'audio_timestamp': datetime.now().isoformat()
                        }
                    )
                return {
                    'violation': True,
                    'violation_type': 'voice_verification_failure',
                    'value': 1,
                    'message': 'Voice verification failed',
                    'similarity_score': similarity,
                    'threshold': threshold
                }
        finally:
            # Clean up temp file
            try:
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)
            except Exception as cleanup_error:
                print(f"Failed to clean up temp file: {cleanup_error}")
    except Exception as e:
        print(f"[Session {session.session_id}] Voice verification error: {str(e)}")
        return {
            'violation': False,
            'message': f'Voice verification error: {str(e)}'
        }
def validate_audio_buffer(audio_bytes: bytes) -> tuple[np.ndarray, str]:
    """
    Validates and converts audio buffer to numpy array with proper error handling
    Returns: (numpy_array, error_message)
    """
    try:        # First try direct conversion
        # Pad buffer if not a multiple of 4 (float32 = 4 bytes)
        float32_size = 4
        if len(audio_bytes) % float32_size != 0:
            pad_len = float32_size - (len(audio_bytes) % float32_size)
            audio_bytes += b'\x00' * pad_len
            logger.warning(f"Audio buffer padded with {pad_len} bytes to match float32 size.")
        audio_np = np.frombuffer(audio_bytes, dtype=np.float32)
        
        # Check if buffer size is valid (should be even for stereo)
        if len(audio_np) % 2 != 0:
            # Pad with zero if odd
            audio_np = np.pad(audio_np, (0, 1), mode='constant')
            logger.debug(f"Padded odd-length buffer to even length: {len(audio_np)}")
        
        # Ensure minimum buffer size
        MIN_BUFFER_SIZE = 512  # Minimum samples needed for processing
        if len(audio_np) < MIN_BUFFER_SIZE:
            return np.array([], dtype=np.float32), f"Buffer too small: {len(audio_np)} samples"
            
        # Handle potential format issues
        if np.max(np.abs(audio_np)) > 1.0:
            # Convert from int16 to float32 if needed
            audio_np = audio_np.astype(np.float32) / 32768.0
            
        # Ensure proper shape for mono audio
        if len(audio_np.shape) > 1:
            audio_np = np.mean(audio_np, axis=1)
        
        return audio_np, ""
        
    except ValueError as ve:
        logger.error(f"Audio buffer validation error: {str(ve)}")
        # Try alternative conversion methods
        try:
            # Try int16 conversion
            int16_size = 2
            if len(audio_bytes) % int16_size != 0:
                pad_len = int16_size - (len(audio_bytes) % int16_size)
                audio_bytes += b'\x00' * pad_len
                logger.warning(f"Audio buffer padded with {pad_len} bytes to match int16 size.")
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_np = audio_np.astype(np.float32) / 32768.0
            return audio_np, ""
        except Exception as ve2:
            return np.array([], dtype=np.float32), f"Invalid buffer format: {str(ve)}; {str(ve2)}"
            
    except Exception as e:
        logger.error(f"Unexpected audio buffer error: {str(e)}")
        return np.array([], dtype=np.float32), f"Unexpected error: {str(e)}"

async def generate_proctoring_report(session: ProctoringSession):
    """Generate comprehensive proctoring report"""
    
    # Calculate monitoring summary metrics
    total_violations = len(session.violations)
    critical_violations = len([v for v in session.violations if v['severity'] == 'critical'])
    overall_assessment = 'PASS' if critical_violations == 0 else 'REVIEW_REQUIRED'
    
    # Generate the report
    report = {
        'session_id': session.session_id,
        'candidate_id': session.candidate_id,
        'exam_id': session.exam_id,
        'duration': str(session.end_time - session.start_time),
        'status': session.status,
        'violations': session.violations,
        'behavior_metrics': session.behavior_metrics,
        'monitoring_summary': {
            'total_violations': total_violations,
            'critical_violations': critical_violations,
            'attention_score': session.behavior_metrics.get('attention_score', 0),
            'integrity_score': session.behavior_metrics.get('integrity_score', 0),
            'overall_assessment': overall_assessment
        },
        'recommendations': generate_recommendations(session.violations, session.behavior_metrics)
    }
    
    # Console logging
    print(f"\n=== PROCTORING REPORT GENERATED ===")
    print(f"Session ID: {session.session_id}")
    print(f"Candidate: {session.candidate_id}")
    print(f"Exam: {session.exam_id}")
    print(f"Duration: {report['duration']}")
    print(f"Status: {session.status}")
    print(f"Total Violations: {total_violations}")
    print(f"Critical Violations: {critical_violations}")
    print(f"Attention Score: {session.behavior_metrics.get('attention_score', 0)}%")
    print(f"Integrity Score: {session.behavior_metrics.get('integrity_score', 0)}%")
    print(f"Overall Assessment: {overall_assessment}")
    
    if session.violations:
        print(f"\nVIOLATIONS DETECTED:")
        for i, violation in enumerate(session.violations, 1):
            print(f"  {i}. {violation.get('type', 'Unknown')} (Severity: {violation.get('severity', 'Unknown')})")
            print(f"     Description: {violation.get('description', 'No description')}")
    
    if report['recommendations']:
        print(f"\nRECOMMENDATIONS:")
        for i, rec in enumerate(report['recommendations'], 1):
            print(f"  {i}. {rec}")
    
    print(f"=====================================\n")
    
    return report

def generate_recommendations(violations: List[dict], metrics: dict) -> List[str]:
    """Generate recommendations based on proctoring results"""
    recommendations = []
    
    critical_violations = [v for v in violations if v['severity'] == 'critical']
    if critical_violations:
        recommendations.append("Manual review required due to critical violations")
    
    if metrics['attention_score'] < 70:
        recommendations.append("Low attention score - candidate frequently looked away")
    
    if metrics['integrity_score'] < 80:
        recommendations.append("Integrity concerns detected - unauthorized objects or identity issues")
    
    if not recommendations:
        recommendations.append("No significant proctoring concerns detected")
    
    return recommendations


# --- Additional endpoints ---
@app.get("/api/proctoring/session/{session_id}/report")
async def get_proctoring_report(session_id: str):
    """Return the final proctoring report for a session."""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = active_sessions[session_id]
    # If the session is not completed, you may want to restrict report access
    if session.status != "completed":
        return {"status": "incomplete", "message": "Assessment not completed yet."}
    report = await generate_proctoring_report(session)
    return report


@app.get("/sessions/{session_id}/report")
async def get_session_report(session_id: str):
    """Return a summary report of the session's proctoring analysis."""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    session = active_sessions[session_id]
    # Compose a summary report
    report = {
        "session_id": session_id,
        "candidate_id": getattr(session, "candidate_id", None),
        "exam_id": getattr(session, "exam_id", None),
        "status": getattr(session, "status", None),
        "start_time": getattr(session, "start_time", None),
        "end_time": getattr(session, "end_time", None),
        "behavior_metrics": getattr(session, "behavior_metrics", {}),
        "violations": getattr(session, "violations", []),
        "real_time_alerts": getattr(session, "real_time_alerts", []),
        "pre_assessment": session.get_pre_assessment_progress() if hasattr(session, "get_pre_assessment_progress") else {},
        # Add more fields as needed
    }
    return report


@app.get("/api/proctoring/sessions/active")
async def get_active_sessions():
    """Get all active proctoring sessions"""
    return {
        "active_sessions": [
            {
                "session_id": sid,
                "candidate_id": session.candidate_id,
                "exam_id": session.exam_id,
                "status": session.status,
                "violations_count": len(session.violations)
            }
            for sid, session in active_sessions.items()
        ],
        "total_count": len(active_sessions)
    }


@app.delete("/api/proctoring/session/{session_id}")
async def end_session(session_id: str):
    """Force end a proctoring session"""
    if session_id in active_sessions:
        session = active_sessions[session_id]
        session.status = "terminated"
        session.end_time = datetime.now()
        del active_sessions[session_id]
        return {"message": "Session terminated"}
    
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/api/health")
async def health_check():
    """System health check"""
    return {
        "status": "healthy",
        "active_sessions": len(active_sessions),
        "system_time": datetime.now().isoformat()
    }


# --- Utility: Convert numpy types to native Python types for JSON serialization ---
def to_native(obj):
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {k: to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_native(v) for v in obj]
    return obj


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")