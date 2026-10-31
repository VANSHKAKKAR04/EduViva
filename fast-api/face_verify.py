from fastapi import FastAPI, WebSocket, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from deepface import DeepFace
import shutil
import cv2
import os
import tempfile
import time
import numpy as np
from fastapi import APIRouter


router=APIRouter()
app = FastAPI()

# Enable CORS (adjust origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REFERENCE_IMG_PATH = "reference.jpg"


def calculate_face_quality_score(image_path: str) -> float:
    """
    Calculate face quality score based on various factors:
    - Face detection confidence
    - Image brightness
    - Image sharpness
    - Face size relative to image
    """
    try:
        # Load image
        img = cv2.imread(image_path)
        if img is None:
            return 0.0
        
        # Convert to grayscale for analysis
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Check for face detection
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        
        if len(faces) == 0:
            return 0.1  # Very low score if no face detected
        
        # Calculate brightness (should be moderate)
        brightness = np.mean(gray)
        brightness_score = 1.0 - abs(brightness - 128) / 128.0
        
        # Calculate sharpness using Laplacian variance
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        sharpness_score = min(laplacian_var / 1000.0, 1.0)  # Normalize
        
        # Calculate face size score
        face_area = faces[0][2] * faces[0][3]  # width * height of first face
        image_area = img.shape[0] * img.shape[1]
        face_ratio = face_area / image_area
        face_size_score = min(face_ratio * 10, 1.0)  # Prefer larger faces
        
        # Combine scores
        overall_score = (brightness_score * 0.3 + 
                        sharpness_score * 0.4 + 
                        face_size_score * 0.3)
        
        return min(max(overall_score, 0.0), 1.0)  # Clamp between 0 and 1
        
    except Exception as e:
        print(f"Error calculating quality score: {e}")
        return 0.0


def verify_faces(reference_path: str, target_path: str) -> dict:
    """
    Verify if two faces match using DeepFace
    Based on the original WebSocket verification logic
    """
    try:
        result = DeepFace.verify(
            img1_path=reference_path,
            img2_path=target_path,
            enforce_detection=False
        )
        
        return {
            'success': True,
            'verified': result.get('verified', False),
            'distance': result.get('distance', None),
            'threshold': result.get('threshold', None),
            'model': result.get('model', 'VGG-Face')
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'verified': False,
            'distance': None
        }


def process_enrollment(image_path: str, enrolled_faces_dir: str = "enrolled_faces") -> dict:
    """
    Process face enrollment with quality assessment
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(enrolled_faces_dir, exist_ok=True)
        
        # Check if image exists
        if not os.path.exists(image_path):
            return {
                'success': False,
                'error': 'Image file not found',
                'quality_score': 0.0
            }
        
        # Load and validate image
        img = cv2.imread(image_path)
        if img is None:
            return {
                'success': False,
                'error': 'Unable to load image',
                'quality_score': 0.0
            }
        
        # Calculate quality score
        quality_score = calculate_face_quality_score(image_path)
        
        # Check if quality meets minimum threshold
        min_quality_threshold = 0.2  # Lower threshold to be more permissive
        if quality_score < min_quality_threshold:
            return {
                'success': False,
                'error': f'Image quality too low (score: {quality_score:.2f}). Please use a clearer image.',
                'quality_score': quality_score
            }
        
        # Test face verification to ensure it works
        try:
            # Create a temporary copy to test verification
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                temp_test_path = tmp_file.name
                shutil.copy2(image_path, temp_test_path)
            
            # Test verification with itself
            test_result = verify_faces(image_path, temp_test_path)
            os.remove(temp_test_path)
            
            if not test_result.get('success', False):
                return {
                    'success': False,
                    'error': 'Face verification test failed - no clear face detected',
                    'quality_score': quality_score
                }
                
        except Exception as test_error:
            return {
                'success': False,
                'error': f'Face detection test failed: {str(test_error)}',
                'quality_score': quality_score
            }
        
        # Save the enrolled image with timestamp
        timestamp = int(time.time())
        enrolled_image_path = os.path.join(enrolled_faces_dir, f"enrolled_{timestamp}.jpg")
        shutil.copy2(image_path, enrolled_image_path)
        
        return {
            'success': True,
            'quality_score': quality_score,
            'enrolled_image_path': enrolled_image_path,
            'message': f'Face enrolled successfully with quality score: {quality_score:.2f}'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': f'Enrollment process failed: {str(e)}',
            'quality_score': 0.0
        }


def save_reference_image(file_content: bytes, reference_path: str) -> dict:
    """
    Save reference image and validate it
    """
    try:
        with open(reference_path, "wb") as buffer:
            buffer.write(file_content)
        
        # Validate the saved image
        enrollment_result = process_enrollment(reference_path)
        
        if enrollment_result.get('success', False):
            return {
                'success': True,
                'message': 'Reference image uploaded and validated successfully',
                'details': enrollment_result
            }
        else:
            # Remove invalid image
            if os.path.exists(reference_path):
                os.remove(reference_path)
            return {
                'success': False,
                'message': f'Reference image validation failed: {enrollment_result.get("error", "Unknown error")}'
            }
            
    except Exception as e:
        return {
            'success': False,
            'message': f'Failed to save reference image: {str(e)}'
        }

# Async wrapper function for integration with main.py
async def process_face_enrollment_async(image_path: str, enrolled_faces_dir: str = "enrolled_faces") -> dict:
    """
    Async wrapper for process_enrollment function
    """
    return process_enrollment(image_path, enrolled_faces_dir)

async def verify_faces_async(reference_path: str, target_path: str) -> dict:
    """
    Async wrapper for verify_faces function
    """
    return verify_faces(reference_path, target_path)


@app.post("/upload-reference/")
async def upload_reference(file: UploadFile = File(...)):
    try:
        with open(REFERENCE_IMG_PATH, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"message": "Reference image uploaded"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save reference image: {str(e)}")


@app.websocket("/ws/verify")
async def verify_websocket(websocket: WebSocket):
    await websocket.accept()

    # Ensure reference image is uploaded
    if not os.path.exists(REFERENCE_IMG_PATH):
        await websocket.send_json({"error": "Reference image not uploaded yet."})
        await websocket.close()
        return

    # Open webcam
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        await websocket.send_json({"error": "Webcam not accessible."})
        await websocket.close()
        return
    else:
        print("✅ Webcam accessed successfully")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                await websocket.send_json({"error": "Failed to read frame from webcam."})
                break

            # Resize for consistency (optional)
            resized = cv2.resize(frame, (640, 480))

            # Save frame temporarily
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp_file:
                temp_path = tmp_file.name
                cv2.imwrite(temp_path, resized)

            try:
                result = DeepFace.verify(
                    img1_path=REFERENCE_IMG_PATH,
                    img2_path=temp_path,
                    enforce_detection=False
                )
                await websocket.send_json({
                    "verified": result.get("verified", False),
                    "distance": result.get("distance", None),
                    "timestamp": time.strftime("%H:%M:%S")
                })
            except Exception as e:
                await websocket.send_json({"error": f"Face verification error: {str(e)}"})
            finally:
                os.remove(temp_path)

            time.sleep(0.5)  # Limit frame rate

    except Exception as e:
        print("❌ WebSocket error:", e)
    finally:
        cap.release()
        print("📷 Webcam released.")
