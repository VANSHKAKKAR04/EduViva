from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import cv2
import mediapipe as mp
import base64
from PIL import Image
import io
import json
import time
import logging
from typing import List, Dict, Any
import uuid
import traceback
from fastapi import APIRouter


router=APIRouter()
# Set up more detailed logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO to DEBUG for more detailed logs
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Suppress MediaPipe warnings
logging.getLogger('mediapipe').setLevel(logging.ERROR)  # Only show errors from MediaPipe

app = FastAPI()

# Enhanced CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MediaPipe models
mp_face_mesh = mp.solutions.face_mesh
mp_pose = mp.solutions.pose

# Constants for gaze tracking
EYE_LANDMARKS = {
    'left_eye': [33, 159, 145, 153],  # Left eye landmarks
    'right_eye': [263, 386, 374, 380],  # Right eye landmarks
    'nose_tip': 1,
    'left_ear': 234,
    'right_ear': 454
}

# Constants for posture tracking
POSTURE_LANDMARKS = {
    'left_shoulder': mp_pose.PoseLandmark.LEFT_SHOULDER.value,
    'right_shoulder': mp_pose.PoseLandmark.RIGHT_SHOULDER.value,
    'nose': mp_pose.PoseLandmark.NOSE.value,
    'left_hip': mp_pose.PoseLandmark.LEFT_HIP.value,
    'right_hip': mp_pose.PoseLandmark.RIGHT_HIP.value
}

# Initialize models with configuration for better performance
# We include important parameters to address the NORM_RECT warning
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    # Adding refine_landmarks=True improves accuracy
    refine_landmarks=True
)

pose = mp_pose.Pose(
    static_image_mode=False,
    model_complexity=1,  # 0=Lite, 1=Full, 2=Heavy
    min_detection_confidence=0.5,
    min_tracking_confidence=0.5,
    # Setting enable_segmentation=False can help with performance
    enable_segmentation=False
)

# Frame processing counters for debugging
frame_processing_stats = {
    "total_frames_received": 0,
    "successful_gaze_analyses": 0,
    "successful_posture_analyses": 0,
    "frame_decode_failures": 0,
    "processing_errors": 0,
    "websocket_messages_sent": 0
}

class ConnectionManager:
    """Enhanced Manager for WebSocket connections"""
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_ids = {}  # Store unique IDs for connections for better logging

    async def connect(self, websocket: WebSocket):
        try:
            await websocket.accept()
            conn_id = str(uuid.uuid4())[:8]  # Short unique ID for this connection
            self.connection_ids[websocket] = conn_id
            self.active_connections.append(websocket)
            logger.info(f"WebSocket connected [ID: {conn_id}]. Active connections: {len(self.active_connections)}")
            return conn_id
        except Exception as e:
            logger.error(f"Failed to accept WebSocket connection: {e}")
            raise

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            conn_id = self.connection_ids.get(websocket, "unknown")
            self.active_connections.remove(websocket)
            if websocket in self.connection_ids:
                del self.connection_ids[websocket]
            logger.info(f"WebSocket disconnected [ID: {conn_id}]. Remaining connections: {len(self.active_connections)}")
    
    async def send_json(self, websocket: WebSocket, data: dict):
        try:
            conn_id = self.connection_ids.get(websocket, "unknown")
            await websocket.send_json(data)
            frame_processing_stats["websocket_messages_sent"] += 1
            logger.debug(f"Sent message to client [ID: {conn_id}], type: {data.get('type')}")
            return True
        except Exception as e:
            conn_id = self.connection_ids.get(websocket, "unknown")
            logger.error(f"Error sending JSON via WebSocket [ID: {conn_id}]: {e}")
            self.disconnect(websocket)
            return False

# Create connection manager instance
manager = ConnectionManager()

def decode_base64_image(base64_string):
    """Decode base64 string to image with enhanced error handling"""
    try:
        # Handle potential 'data:image/jpeg;base64,' prefix
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
        
        img_data = base64.b64decode(base64_string)
        img = Image.open(io.BytesIO(img_data))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    except Exception as e:
        frame_processing_stats["frame_decode_failures"] += 1
        logger.error(f"Error decoding image: {e}")
        return None


def analyze_gaze(image):
    """
    Enhanced gaze analysis with improved accuracy and performance.
    Detects whether a person is looking away from the screen using face mesh landmarks.
    
    Args:
        image: OpenCV/numpy image in BGR format
        
    Returns:
        Dictionary with gaze analysis results
    """
    logger.debug("Starting gaze analysis")
    start_time = time.time()
    
    try:
        # Convert to RGB for MediaPipe
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w = image.shape[:2]
        
        # Process with Face Mesh
        results = face_mesh.process(image_rgb)
        
        if not results.multi_face_landmarks or len(results.multi_face_landmarks) == 0:
            logger.debug("No face detected for gaze analysis")
            return {"looking_away": True, "status": "no_face_detected", "confidence": 0.0}
        
        # Get the first detected face
        face_landmarks = results.multi_face_landmarks[0].landmark
        
        # Enhanced eye landmark selection for better gaze tracking
        # Using more precise iris landmarks which are available with refine_landmarks=True
        EYE_IRIS_LANDMARKS = {
            'left_iris': [468, 469, 470, 471, 472],  # Left iris landmarks
            'right_iris': [473, 474, 475, 476, 477],  # Right iris landmarks
            'left_eye_contour': [33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7],
            'right_eye_contour': [263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249],
            'nose_tip': 1,
            'left_ear': 234,
            'right_ear': 454,
            'face_oval': [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377, 152]
        }
        
        # Extract all necessary landmark coordinates
        landmark_coords = {}
        for region, landmarks in EYE_IRIS_LANDMARKS.items():
            if isinstance(landmarks, list):
                points = []
                for lm_id in landmarks:
                    # Handle potential index errors gracefully
                    if lm_id < len(face_landmarks):
                        lm = face_landmarks[lm_id]
                        x, y = int(lm.x * w), int(lm.y * h)
                        points.append((x, y))
                if points:  # Only add if we got some points
                    landmark_coords[region] = points
            else:
                if landmarks < len(face_landmarks):
                    lm = face_landmarks[landmarks]
                    x, y = int(lm.x * w), int(lm.y * h)
                    landmark_coords[region] = (x, y)
        
        # Multiple techniques for more robust gaze detection
        gaze_metrics = {}
        confidence_scores = []
        
        # 1. Face orientation using nose and ears (as in original code, but improved)
        if all(k in landmark_coords for k in ['nose_tip', 'left_ear', 'right_ear']):
            nose_tip = landmark_coords['nose_tip']
            left_ear = landmark_coords['left_ear']
            right_ear = landmark_coords['right_ear']
            
            dist_left = np.sqrt((nose_tip[0] - left_ear[0])**2 + (nose_tip[1] - left_ear[1])**2)
            dist_right = np.sqrt((nose_tip[0] - right_ear[0])**2 + (nose_tip[1] - right_ear[1])**2)
            
            # Avoid division by zero
            ratio = min(dist_left, dist_right) / max(dist_left, dist_right) if max(dist_left, dist_right) > 0 else 1
            
            # Scale from 0.5-1.0 to 0-1.0 for better sensitivity
            normalized_ratio = (ratio - 0.5) * 2 if ratio > 0.5 else 0
            normalized_ratio = max(0, min(1, normalized_ratio))  # Clamp between 0 and 1
            
            gaze_metrics['face_orientation'] = normalized_ratio
            confidence_scores.append((normalized_ratio, 0.7))  # Weight of 0.7
        
        # 2. Iris position relative to eye contour
        if all(k in landmark_coords for k in ['left_iris', 'left_eye_contour', 'right_iris', 'right_eye_contour']):
            # Process left eye
            left_iris_center = np.mean(landmark_coords['left_iris'], axis=0)
            left_eye_contour = landmark_coords['left_eye_contour']
            left_eye_center = np.mean(left_eye_contour, axis=0)
            left_eye_width = max(np.max(np.array(left_eye_contour)[:, 0]) - np.min(np.array(left_eye_contour)[:, 0]), 1)
            
            # Normalized horizontal distance from iris to eye center
            left_iris_offset = abs(left_iris_center[0] - left_eye_center[0]) / left_eye_width
            
            # Process right eye
            right_iris_center = np.mean(landmark_coords['right_iris'], axis=0)
            right_eye_contour = landmark_coords['right_eye_contour']
            right_eye_center = np.mean(right_eye_contour, axis=0)
            right_eye_width = max(np.max(np.array(right_eye_contour)[:, 0]) - np.min(np.array(right_eye_contour)[:, 0]), 1)
            
            right_iris_offset = abs(right_iris_center[0] - right_eye_center[0]) / right_eye_width
            
            # Average offset of both eyes, normalized to 0-1 (0 = centered, 1 = far off center)
            avg_iris_offset = (left_iris_offset + right_iris_offset) / 2
            iris_position_score = 1 - min(1, avg_iris_offset * 3)  # Scale for sensitivity
            
            gaze_metrics['iris_position'] = iris_position_score
            confidence_scores.append((iris_position_score, 0.8))  # Weight of 0.8
        
        # 3. Face visibility factor
        if 'face_oval' in landmark_coords:
            # Check if face is fully in frame
            face_points = np.array(landmark_coords['face_oval'])
            in_frame_x = np.logical_and(face_points[:, 0] >= 0, face_points[:, 0] < w)
            in_frame_y = np.logical_and(face_points[:, 1] >= 0, face_points[:, 1] < h)
            in_frame = np.logical_and(in_frame_x, in_frame_y)
            face_visibility = np.mean(in_frame.astype(float))
            
            gaze_metrics['face_visibility'] = face_visibility
            confidence_scores.append((face_visibility, 0.5))  # Weight of 0.5
        
        # Calculate weighted average confidence
        if confidence_scores:
            total_weight = sum(weight for _, weight in confidence_scores)
            if total_weight > 0:
                weighted_score = sum(score * weight for score, weight in confidence_scores) / total_weight
                
                # Final decision with adaptive threshold
                # Less strict if we only have one metric
                threshold = 0.7 if len(confidence_scores) > 1 else 0.6
                looking_away = weighted_score < threshold
                
                frame_processing_stats["successful_gaze_analyses"] += 1
                processing_time = time.time() - start_time
                logger.debug(f"Gaze analysis complete. Looking away: {looking_away}, "
                           f"Score: {weighted_score:.2f}, Time: {processing_time:.3f}s")
                
                return {
                    "looking_away": looking_away,
                    "status": "success",
                    "confidence": weighted_score,
                    "metrics": gaze_metrics
                }
        
        # Fallback if metrics couldn't be calculated
        logger.debug("Insufficient data for confident gaze tracking")
        return {"looking_away": True, "status": "insufficient_data", "confidence": 0.3}
    
    except Exception as e:
        frame_processing_stats["processing_errors"] += 1
        logger.error(f"Error in gaze analysis: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {"looking_away": True, "status": f"error: {str(e)}", "confidence": 0.0}

def analyze_posture(image):
    """
    Balanced posture analysis with calibrated thresholds to accurately detect
    both good and bad posture without excessive false positives or negatives.
    """
    logger.debug("Starting posture analysis")
    start_time = time.time()
    
    try:
        # Convert to RGB for MediaPipe
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w = image.shape[:2]
        
        # Process with Pose detection
        results = pose.process(image_rgb)
        
        if not results.pose_landmarks:
            logger.debug("No pose detected for posture analysis")
            return {"proper_posture": False, "status": "no_pose_detected", "confidence": 0.0}
        
        landmarks = results.pose_landmarks.landmark
        
        # Enhanced landmark selection - focusing on upper body for posture analysis
        POSTURE_LANDMARKS = {
            'nose': mp_pose.PoseLandmark.NOSE.value,
            'left_ear': mp_pose.PoseLandmark.LEFT_EAR.value,
            'right_ear': mp_pose.PoseLandmark.RIGHT_EAR.value,
            'left_eye': mp_pose.PoseLandmark.LEFT_EYE.value,
            'right_eye': mp_pose.PoseLandmark.RIGHT_EYE.value,
            'left_shoulder': mp_pose.PoseLandmark.LEFT_SHOULDER.value,
            'right_shoulder': mp_pose.PoseLandmark.RIGHT_SHOULDER.value,
            'left_hip': mp_pose.PoseLandmark.LEFT_HIP.value,
            'right_hip': mp_pose.PoseLandmark.RIGHT_HIP.value
        }
        
        # Extract coordinates and visibility scores
        landmark_data = {}
        for name, idx in POSTURE_LANDMARKS.items():
            lm = landmarks[idx]
            landmark_data[name] = {
                'x': lm.x * w,
                'y': lm.y * h,
                'z': lm.z * w,
                'visibility': lm.visibility
            }
        
        # Moderate visibility threshold - balanced approach
        visibility_threshold = 0.25
        
        # Check core landmarks for sufficient visibility
        core_landmarks = ['nose', 'left_shoulder', 'right_shoulder']
        core_visibility_ok = all(landmark_data[lm_name]['visibility'] >= visibility_threshold 
                                for lm_name in core_landmarks)
        
        # Initialize posture details with None (unknown) to start with neutral stance
        posture_details = {
            "shoulder_level": None,
            "back_straight": None,
            "head_alignment": None,
            "forward_head": None
        }
        
        # If core visibility is poor, return low confidence result
        if not core_visibility_ok:
            logger.debug("Low landmark visibility for posture assessment")
            # Initialize with indeterminate rather than assuming bad
            posture_details = {
                "shoulder_level": None,
                "back_straight": None,
                "head_alignment": None,
                "forward_head": None
            }
            return {
                "proper_posture": False,
                "status": "low_visibility",
                "confidence": 0.3,
                "details": posture_details
            }
        
        # Calculate metrics with balanced thresholds
        metrics = {}
        confidence_scores = []
        
        # 1. Shoulder levelness - calibrated threshold
        left_shoulder = landmark_data['left_shoulder']
        right_shoulder = landmark_data['right_shoulder']
        shoulder_height_diff = abs(left_shoulder['y'] - right_shoulder['y'])
        shoulder_width = abs(left_shoulder['x'] - right_shoulder['x'])
        
        if shoulder_width > 0:
            # Normalize by shoulder width
            shoulder_slope = shoulder_height_diff / shoulder_width
            # Balanced threshold - not too strict or lenient
            shoulder_levelness = max(0, 1 - (shoulder_slope * 4))
            metrics['shoulder_levelness'] = shoulder_levelness
            confidence_scores.append(shoulder_levelness)
            # Calibrated threshold based on real-world testing (your shoulders are good)
            posture_details["shoulder_level"] = shoulder_levelness > 0.45
        
        # 2. Back straightness assessment - calibrated for real-world conditions
        if all(landmark_data[lm]['visibility'] >= visibility_threshold 
              for lm in ['left_shoulder', 'right_shoulder', 'left_hip', 'right_hip']):
            
            mid_shoulder_x = (left_shoulder['x'] + right_shoulder['x']) / 2
            mid_shoulder_y = (left_shoulder['y'] + right_shoulder['y']) / 2
            mid_hip_x = (landmark_data['left_hip']['x'] + landmark_data['right_hip']['x']) / 2
            mid_hip_y = (landmark_data['left_hip']['y'] + landmark_data['right_hip']['y']) / 2
            
            # Calculate back straightness
            spine_length = abs(mid_shoulder_y - mid_hip_y)
            
            if spine_length > 0:
                back_deviation = abs(mid_shoulder_x - mid_hip_x) / spine_length
                # Calibrated threshold based on real-world testing (more lenient since this was flagging too much)
                spine_straightness = max(0, 1 - back_deviation * 1.8)
                metrics['spine_straightness'] = spine_straightness
                confidence_scores.append(spine_straightness)
                # Adjusted threshold based on your results
                posture_details["back_straight"] = spine_straightness > 0.45
        
        # 3. Head alignment - calibrated for real-world conditions
        face_landmarks = ['nose', 'left_eye', 'right_eye', 'left_ear', 'right_ear']
        face_visibility = sum(landmark_data[lm]['visibility'] for lm in face_landmarks) / len(face_landmarks)
        
        if face_visibility >= visibility_threshold:
            ear_mid_y = (landmark_data['left_ear']['y'] + landmark_data['right_ear']['y']) / 2
            mid_shoulder_y = (left_shoulder['y'] + right_shoulder['y']) / 2
            
            if 'left_hip' in landmark_data and 'right_hip' in landmark_data and \
               landmark_data['left_hip']['visibility'] >= visibility_threshold and \
               landmark_data['right_hip']['visibility'] >= visibility_threshold:
                mid_hip_y = (landmark_data['left_hip']['y'] + landmark_data['right_hip']['y']) / 2
                spine_length = abs(mid_shoulder_y - mid_hip_y)
            else:
                # Fallback if hips aren't detected well
                spine_length = shoulder_width * 1.5
            
            if spine_length > 0:
                head_projection = abs(ear_mid_y - mid_shoulder_y) / spine_length
                # Calibrated threshold based on real-world testing
                head_alignment = max(0, 1 - head_projection * 2)
                metrics['head_alignment'] = head_alignment
                confidence_scores.append(head_alignment)
                # Adjusted threshold based on your results
                posture_details["head_alignment"] = head_alignment > 0.45
        
        # 4. Forward head posture - calibrated threshold
        if all(landmark_data[lm]['visibility'] >= visibility_threshold 
              for lm in ['left_ear', 'right_ear', 'left_shoulder', 'right_shoulder']):
            
            ear_mid_x = (landmark_data['left_ear']['x'] + landmark_data['right_ear']['x']) / 2
            shoulder_mid_x = (left_shoulder['x'] + right_shoulder['x']) / 2
            # Use the greater of actual shoulder width or a minimum threshold
            effective_shoulder_width = max(shoulder_width, w * 0.1)
            
            forward_head_ratio = abs(ear_mid_x - shoulder_mid_x) / effective_shoulder_width
            
            # Calibrated multiplier based on real-world testing
            forward_head_score = max(0, 1 - forward_head_ratio * 2.2)
            metrics['forward_head'] = forward_head_score
            confidence_scores.append(forward_head_score)
            # Adjusted threshold based on your results (your forward head is good)
            posture_details["forward_head"] = forward_head_score > 0.45
        
        # For unassessed metrics, set to None rather than assuming False
        for key in posture_details:
            if posture_details[key] is None:
                posture_details[key] = False  # Still assume bad for unassessed to be conservative
        
        # Calculate overall posture score
        if confidence_scores:
            avg_confidence = sum(confidence_scores) / len(confidence_scores)
            
            # Count how many individual metrics pass
            valid_metrics = [val for val in posture_details.values() if val is not None]
            passed_metrics = sum(1 for val in valid_metrics if val)
            total_metrics = len(valid_metrics)
            
            # Avoid division by zero
            posture_score = passed_metrics / total_metrics if total_metrics > 0 else 0
            
            # Balanced threshold for overall posture assessment
            # Require at least 50% of metrics to pass for overall good posture
            # This is a more balanced approach based on your feedback
            proper_posture = posture_score >= 0.5
            
            logger.debug(f"Posture analysis complete. Proper posture: {proper_posture}, "
                       f"Score: {avg_confidence:.2f}, Metrics passed: {passed_metrics}/{total_metrics}")
            
            return {
                "proper_posture": proper_posture,
                "status": "success",
                "confidence": avg_confidence,
                "posture_score": posture_score,
                "details": posture_details,
                "metrics": metrics
            }
        
        # If we can't calculate metrics, return with moderate confidence
        logger.debug("Limited data for posture assessment")
        return {
            "proper_posture": False,
            "status": "limited_data", 
            "confidence": 0.4,
            "posture_score": 0.4,
            "details": posture_details
        }
    
    except Exception as e:
        logger.error(f"Error in posture analysis: {str(e)}")
        traceback.print_exc()
        # Default to indeterminate posture on errors
        return {
            "proper_posture": False,
            "status": f"error: {str(e)}", 
            "confidence": 0.3,
            "posture_score": 0.4,
            "details": posture_details
        }
class AssessmentSession:
    """Class to track assessment session data"""
    def __init__(self, session_id):
        self.session_id = session_id
        self.start_time = time.time()
        self.gaze_records = []
        self.posture_records = []
        self.looking_away_count = 0
        self.bad_posture_count = 0
        self.total_gaze_frames = 0
        self.total_posture_frames = 0
        self.last_activity = time.time()
        self.frames_processed = 0
        logger.info(f"New session created: {session_id}")

    def update_gaze(self, result):
        self.total_gaze_frames += 1
        self.frames_processed += 1
        self.gaze_records.append({
            "timestamp": time.time() - self.start_time,
            "looking_away": result["looking_away"],
            "status": result["status"]
        })
        if result["looking_away"]:
            self.looking_away_count += 1
        self.last_activity = time.time()
        
        # Log every 30 frames to avoid log spam
        if self.frames_processed % 30 == 0:
            logger.info(f"Session {self.session_id}: Processed {self.frames_processed} frames. "
                       f"Looking away count: {self.looking_away_count}, "
                       f"Bad posture count: {self.bad_posture_count}")

    def update_posture(self, result):
        self.total_posture_frames += 1
        self.frames_processed += 1
        self.posture_records.append({
            "timestamp": time.time() - self.start_time,
            "proper_posture": result["proper_posture"],
            "status": result["status"]
        })
        if not result["proper_posture"]:
            self.bad_posture_count += 1
        self.last_activity = time.time()
    
    def get_summary(self):
        duration = time.time() - self.start_time
        
        gaze_summary = {
            "looking_away_percent": self.looking_away_count / max(1, self.total_gaze_frames) * 100,
            "total_frames": self.total_gaze_frames,
            "looking_away_count": self.looking_away_count,
            "attention_score": 100 - (self.looking_away_count / max(1, self.total_gaze_frames) * 100)
        }
        
        posture_summary = {
            "bad_posture_percent": self.bad_posture_count / max(1, self.total_posture_frames) * 100,
            "total_frames": self.total_posture_frames,
            "bad_posture_count": self.bad_posture_count,
            "posture_score": 100 - (self.bad_posture_count / max(1, self.total_posture_frames) * 100)
        }
        
        summary = {
            "session_id": self.session_id,
            "duration_seconds": duration,
            "gaze": gaze_summary,
            "posture": posture_summary,
            "overall_score": (gaze_summary["attention_score"] + posture_summary["posture_score"]) / 2,
            "frames_processed": self.frames_processed
        }
        
        logger.info(f"Session {self.session_id} summary: "
                   f"Duration: {duration:.1f}s, "
                   f"Frames: {self.frames_processed}, "
                   f"Attention score: {gaze_summary['attention_score']:.1f}, "
                   f"Posture score: {posture_summary['posture_score']:.1f}")
                   
        return summary
class EnhancedAssessmentSession(AssessmentSession):
    """Enhanced Assessment Session with advanced analytics"""
    
    def __init__(self, session_id):
        super().__init__(session_id)
        # Additional tracking for time-weighted metrics
        self.gaze_weighted_records = []
        self.posture_weighted_records = []
        self.last_gaze_check = 0
        self.last_posture_check = 0
        self.attention_spans = []  # Tracks continuous attention spans
        self.current_attention_span = 0
        self.posture_spans = []  # Tracks good posture spans
        self.current_posture_span = 0
    
    def update_gaze(self, result):
        super().update_gaze(result)
        current_time = time.time() - self.start_time
        
        # Track attention spans
        if not result["looking_away"]:
            if self.current_attention_span == 0:
                # Starting a new attention span
                self.current_attention_span = current_time
        else:
            if self.current_attention_span > 0:
                # End of attention span
                span_duration = current_time - self.current_attention_span
                if span_duration > 1.0:  # Only record spans longer than 1 second
                    self.attention_spans.append({
                        'start': self.current_attention_span,
                        'end': current_time,
                        'duration': span_duration
                    })
                self.current_attention_span = 0
        
        # Store confidence-weighted record
        self.gaze_weighted_records.append({
            "timestamp": current_time,
            "looking_away": result["looking_away"],
            "confidence": result.get("confidence", 0.5)
        })
        
        self.last_gaze_check = current_time
    
    def update_posture(self, result):
        super().update_posture(result)
        current_time = time.time() - self.start_time
        
        # Track posture spans
        if result["proper_posture"]:
            if self.current_posture_span == 0:
                # Starting a new good posture span
                self.current_posture_span = current_time
        else:
            if self.current_posture_span > 0:
                # End of good posture span
                span_duration = current_time - self.current_posture_span
                if span_duration > 2.0:  # Only record spans longer than 2 seconds
                    self.posture_spans.append({
                        'start': self.current_posture_span,
                        'end': current_time,
                        'duration': span_duration
                    })
                self.current_posture_span = 0
        
        # Store confidence-weighted record
        self.posture_weighted_records.append({
            "timestamp": current_time,
            "proper_posture": result["proper_posture"],
            "confidence": result.get("confidence", 0.5),
            "details": result.get("details", {})
        })
        
        self.last_posture_check = current_time
    
    def get_summary(self):
        """Get enhanced summary with time-weighted metrics and additional analytics"""
        basic_summary = super().get_summary()
        
        # Close any open spans
        current_time = time.time() - self.start_time
        if self.current_attention_span > 0:
            span_duration = current_time - self.current_attention_span
            self.attention_spans.append({
                'start': self.current_attention_span,
                'end': current_time,
                'duration': span_duration
            })
        
        if self.current_posture_span > 0:
            span_duration = current_time - self.current_posture_span
            self.posture_spans.append({
                'start': self.current_posture_span,
                'end': current_time,
                'duration': span_duration
            })
        
        # Enhanced gaze metrics
        gaze_summary = basic_summary['gaze']
        if self.gaze_weighted_records:
            # Calculate confidence-weighted metrics
            weighted_looking_away = sum(
                r["looking_away"] * r["confidence"] for r in self.gaze_weighted_records
            )
            total_confidence = sum(r["confidence"] for r in self.gaze_weighted_records)
            if total_confidence > 0:
                weighted_looking_away_ratio = weighted_looking_away / total_confidence
                gaze_summary["weighted_looking_away_percent"] = weighted_looking_away_ratio * 100
                gaze_summary["weighted_attention_score"] = 100 - (weighted_looking_away_ratio * 100)
            
            # Attention span statistics
            if self.attention_spans:
                gaze_summary["max_attention_span"] = max(span["duration"] for span in self.attention_spans)
                gaze_summary["avg_attention_span"] = sum(span["duration"] for span in self.attention_spans) / len(self.attention_spans)
                gaze_summary["attention_span_count"] = len(self.attention_spans)
        
        # Enhanced posture metrics
        posture_summary = basic_summary['posture']
        if self.posture_weighted_records:
            # Calculate confidence-weighted metrics
            weighted_bad_posture = sum(
                (not r["proper_posture"]) * r["confidence"] for r in self.posture_weighted_records
            )
            total_confidence = sum(r["confidence"] for r in self.posture_weighted_records)
            if total_confidence > 0:
                weighted_bad_posture_ratio = weighted_bad_posture / total_confidence
                posture_summary["weighted_bad_posture_percent"] = weighted_bad_posture_ratio * 100
                posture_summary["weighted_posture_score"] = 100 - (weighted_bad_posture_ratio * 100)
            
            # Posture span statistics
            if self.posture_spans:
                posture_summary["max_good_posture_span"] = max(span["duration"] for span in self.posture_spans)
                posture_summary["avg_good_posture_span"] = sum(span["duration"] for span in self.posture_spans) / len(self.posture_spans)
                posture_summary["good_posture_span_count"] = len(self.posture_spans)
            
            # Detailed posture issues breakdown
            posture_issues = {"shoulder_level": 0, "back_straight": 0, "head_alignment": 0, "forward_head": 0}
            for record in self.posture_weighted_records:
                if not record["proper_posture"] and "details" in record:
                    for issue, has_issue in record["details"].items():
                        if not has_issue:
                            posture_issues[issue] += 1
            
            total_frames = len(self.posture_weighted_records)
            if total_frames > 0:
                posture_summary["issue_breakdown"] = {
                    issue: {"count": count, "percent": (count / total_frames) * 100}
                    for issue, count in posture_issues.items()
                }
        
        # Update the basic summary with enhanced metrics
        enhanced_summary = basic_summary.copy()
        enhanced_summary["gaze"] = gaze_summary
        enhanced_summary["posture"] = posture_summary
        
        # Calculate overall wellness score with weighted components
        enhanced_summary["overall_score"] = (
            gaze_summary.get("weighted_attention_score", gaze_summary["attention_score"]) * 0.6 +
            posture_summary.get("weighted_posture_score", posture_summary["posture_score"]) * 0.4
        )
        
        return enhanced_summary
# Global dictionary to store active sessions
active_sessions = {}

# Add a session cleanup function
async def cleanup_inactive_sessions():
    """Remove sessions that have been inactive for more than 30 minutes"""
    current_time = time.time()
    inactive_threshold = 1800  # 30 minutes in seconds
    
    to_remove = []
    for session_id, session in active_sessions.items():
        if current_time - session.last_activity > inactive_threshold:
            to_remove.append(session_id)
    
    for session_id in to_remove:
        del active_sessions[session_id]
        logger.info(f"Removed inactive session: {session_id}")

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint with enhanced error handling and debugging"""
    logger.info(f"WebSocket connection attempt for session: {session_id}")
    
    try:
        conn_id = await manager.connect(websocket)
        
        # Initialize or get session
        if session_id not in active_sessions:
            active_sessions[session_id] = EnhancedAssessmentSession(session_id)
        
        session = active_sessions[session_id]
        
        # Send confirmation that connection is established
        await manager.send_json(websocket, {
            "type": "connection_established",
            "session_id": session_id,
            "message": "WebSocket connection established",
            "timestamp": time.time()
        })
        
        logger.info(f"WebSocket connection established for session: {session_id} [Connection ID: {conn_id}]")
        
        # Initialize frame counters for this connection
        frame_count = 0
        last_frame_time = time.time()
        last_stats_log_time = time.time()
        
        # Suppress MediaPipe warnings about NORM_RECT
        import os
        os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Suppress TensorFlow warnings
        logging.getLogger('mediapipe').setLevel(logging.ERROR)  # Only show errors from MediaPipe
        
        while True:
            # Receive image data as JSON
            try:
                data_start_time = time.time()
                data = await websocket.receive_json()
                receive_time = time.time() - data_start_time
                frame_count += 1
                frame_processing_stats["total_frames_received"] += 1
                
                # Log frame rate every 5 seconds
                current_time = time.time()
                if current_time - last_stats_log_time > 5:
                    fps = frame_count / (current_time - last_stats_log_time)
                    logger.info(f"Session {session_id} [Conn {conn_id}]: "
                               f"Frame rate: {fps:.2f} FPS over last {current_time - last_stats_log_time:.1f}s. "
                               f"Receive time: {receive_time:.3f}s")
                    frame_count = 0
                    last_stats_log_time = current_time
                
                logger.debug(f"Received data type: {data.get('type', 'not specified')}")
            except json.JSONDecodeError:
                # Try to receive as text in case it's not proper JSON
                raw_data = await websocket.receive_text()
                logger.warning(f"Received non-JSON data: {raw_data[:100]}...")
                try:
                    data = json.loads(raw_data)
                except:
                    await manager.send_json(websocket, {
                        "type": "error",
                        "message": "Invalid JSON data received",
                        "timestamp": time.time()
                    })
                    continue
            
            # Handle ping message (keep-alive)
            if data.get("type") == "ping":
                await manager.send_json(websocket, {
                    "type": "pong",
                    "timestamp": time.time()
                })
                logger.debug(f"Ping-pong for session {session_id}")
                continue
            
            # Handle summary request
            if data.get("command") == "get_summary":
                # Return session summary
                summary = session.get_summary()
                await manager.send_json(websocket, {
                    "type": "summary",
                    "data": summary,
                    "timestamp": time.time()
                })
                logger.info(f"Sent summary for session {session_id}")
                continue
                
            # Get analysis type (gaze, posture, or both)
            analysis_type = data.get("type", "both")
            
            # Check if image data is provided
            if "image" not in data:
                await manager.send_json(websocket, {
                    "type": "error",
                    "message": "No image data provided",
                    "timestamp": time.time()
                })
                continue
            
            # Log the length of the image data for debugging
            image_data_length = len(data["image"])
            logger.debug(f"Received image data length: {image_data_length} bytes")
                
            # Decode image
            decode_start = time.time()
            image = decode_base64_image(data["image"])
            decode_time = time.time() - decode_start
            
            logger.debug(f"Image decode time: {decode_time:.3f}s")
            
            if image is None:
                await manager.send_json(websocket, {
                    "type": "error",
                    "message": "Invalid image data",
                    "timestamp": time.time()
                })
                continue
            
            process_start = time.time()
            results = {"type": "analysis_result", "timestamp": time.time()}
            
            # Perform requested analyses
            if analysis_type in ["gaze", "both"]:
                gaze_start = time.time()
                gaze_result = analyze_gaze(image)
                gaze_time = time.time() - gaze_start
                logger.debug(f"Gaze analysis time: {gaze_time:.3f}s")
                results["gaze"] = gaze_result
                session.update_gaze(gaze_result)
            
            if analysis_type in ["posture", "both"]:
                posture_start = time.time()
                posture_result = analyze_posture(image)
                posture_time = time.time() - posture_start
                logger.debug(f"Posture analysis time: {posture_time:.3f}s")
                results["posture"] = posture_result
                session.update_posture(posture_result)
            
            total_process_time = time.time() - process_start
            logger.debug(f"Total processing time: {total_process_time:.3f}s")
            
            # Add processing time to results
            results["processing_time"] = total_process_time
                
            # Send results back to the client
            send_start = time.time()
            send_success = await manager.send_json(websocket, results)
            send_time = time.time() - send_start
            logger.debug(f"Send time: {send_time:.3f}s, Success: {send_success}")
            
            # Calculate full frame turnaround time
            frame_time = time.time() - data_start_time
            last_frame_time = time.time()
            
            # Log detailed timing every 10th frame to avoid log spam
            if frame_count % 10 == 0:
                logger.debug(f"Frame timing - Total: {frame_time:.3f}s, "
                           f"Decode: {decode_time:.3f}s, Process: {total_process_time:.3f}s, "
                           f"Send: {send_time:.3f}s")
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for session: {session_id}")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error in session {session_id}: {str(e)}")
        try:
            manager.disconnect(websocket)
        except:
            pass

@app.get("/session/{session_id}/summary")
async def get_session_summary(session_id: str):
    """Get summary for a specific session"""
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return active_sessions[session_id].get_summary()

@app.get("/debug/stats")
async def get_processing_stats():
    """Debug endpoint to get frame processing statistics"""
    return {
        "timestamp": time.time(),
        "stats": frame_processing_stats
    }

@app.get("/debug/sessions")
async def list_active_sessions():
    """Debug endpoint to list all active sessions"""
    session_info = {}
    for session_id, session in active_sessions.items():
        session_info[session_id] = {
            "start_time": session.start_time,
            "last_activity": session.last_activity,
            "total_gaze_frames": session.total_gaze_frames,
            "total_posture_frames": session.total_posture_frames,
            "frames_processed": session.frames_processed,
            "duration": time.time() - session.start_time
        }
    
    return {
        "active_connections": len(manager.active_connections),
        "active_sessions": len(active_sessions),
        "sessions": session_info
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting server with enhanced debugging...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="debug")