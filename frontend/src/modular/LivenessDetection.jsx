import React, { useState, useEffect, useRef } from 'react';
import './LivenessDetection.css'; // Import your CSS file for styling
/**
 * LivenessDetection Component
 * 
 * A React component that handles facial liveness detection using webcam
 * and server API integration. It performs challenge-based verification
 * and provides user feedback throughout the process.
 */

export default function LivenessDetection() {
  let [status, setStatus] = useState('challenge');
  const [message, setMessage] = useState('Click Start to begin liveness verification');
  const [sessionId, setSessionId] = useState(null);
  const [challengeId, setChallengeId] = useState(null);
  const [challengeType, setChallengeType] = useState(null);
  const [challengeText, setChallengeText] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [checkCount, setCheckCount] = useState(0);
  const [showDebug, setShowDebug] = useState(false);
  const [debugInfo, setDebugInfo] = useState({});
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const checkIntervalRef = useRef(null);
  const intervalRef = useRef(null);
  
  // Start the liveness detection process
  // Start the liveness detection process

// Fixed startLivenessCheck function
// Fixed startLivenessCheck function based on new error
// Fixed startLivenessCheck function with proper state handling
const startLivenessCheck = async () => {
  try {
    setStatus('starting');
    setMessage('Starting camera...');
    
    // Access the webcam
    const stream = await navigator.mediaDevices.getUserMedia({ 
      video: { facingMode: 'user', width: 640, height: 480 } 
    });
    
    // Store stream reference to stop it later
    streamRef.current = stream;
    
    // Show video feed
    if (videoRef.current) {
      videoRef.current.srcObject = stream;
    }
    
    // Start assessment session
    setMessage('Starting assessment session...');
    const sessionResponse = await fetch('http://localhost:8001/session/start?assessment_id=assessment-001', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
          user_id: 'test-user-123',
          name: 'Test User',
          email: 'test@example.com'
      })
    });
    
    if (!sessionResponse.ok) {
      const errorText = await sessionResponse.text();
      console.error(`API Error: ${sessionResponse.status}`, errorText);
      throw new Error(`Failed to start assessment session: ${sessionResponse.status}`);
    }
    
    const session = await sessionResponse.json();
    setSessionId(session.session_id);
    console.log("Session started with ID:", session.session_id);
    
    // Request a challenge
    setMessage('Requesting liveness challenge...');
    const challengeResponse = await fetch('http://localhost:8001/auth/request-challenge', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ 
        user_id: 'test-user-123'
      })
    });
    
    if (!challengeResponse.ok) {
      const errorText = await challengeResponse.text();
      console.error(`API Error: ${challengeResponse.status}`, errorText);
      throw new Error('Failed to get challenge');
    }
    
    const challenge = await challengeResponse.json();
    console.log("Challenge received:", challenge);
    
    // First set challenge data
    setChallengeId(challenge.challenge_id);
    setChallengeType(challenge.challenge_type);
    setChallengeText(challenge.instructions);
    setCountdown(30);
    
    // Wait for state updates to propagate
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // Then change status to challenge
    setStatus('challenge');
    console.log("Status set to challenge, challengeId:", challenge.challenge_id);
    
    // Start countdown
    intervalRef.current = setInterval(() => {
      setCountdown(prev => {
        if (prev <= 1) {
          clearInterval(intervalRef.current);
          setStatus('timeout');
          setMessage('Challenge timed out. Please try again.');
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    
    // Start continuous checking after ensuring state is updated
    setTimeout(() => {
      console.log("Starting continuous checks with:", {
        status: 'challenge',
        challengeId: challenge.challenge_id,
        challengeType: challenge.challenge_type
      });
      startContinuousCheck(challenge.challenge_id);
    }, 500);
    
  } catch (error) {
    console.error('Error starting liveness check:', error);
    setStatus('error');
    setMessage(`Error: ${error.message}`);
    stopEverything();
  }
};

// Modified startContinuousCheck to accept challengeId parameter
const startContinuousCheck = (challengeIdParam) => {
  if (checkIntervalRef.current) {
    clearInterval(checkIntervalRef.current);
  }
  
  checkIntervalRef.current = setInterval(async () => {
    // Use direct parameter first, then fall back to state
    const activeChallengeId = challengeIdParam || challengeId;
    status='challenge'
    const currentStatus = status;
    
    console.log("Check iteration with:", {
      status: currentStatus,
      challengeId: activeChallengeId,
      videoRefExists: !!videoRef.current
    });
    
    if (currentStatus !== 'challenge' || !videoRef.current || !activeChallengeId) {
      console.log("Skipping check - prerequisites not met:", { 
        statusIsChallenge: currentStatus === 'challenge',
        videoRefExists: !!videoRef.current,
        challengeIdExists: !!activeChallengeId
      });
      return;
    }
    
    try {
      // Ensure video is playing and has dimensions
      if (!videoRef.current.videoWidth || !videoRef.current.videoHeight) {
        console.log("Video not ready yet, dimensions:", videoRef.current.videoWidth, "x", videoRef.current.videoHeight);
        return;
      }
      
      // Capture a frame from the video
      const canvas = document.createElement('canvas');
      canvas.width = videoRef.current.videoWidth;
      canvas.height = videoRef.current.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
      
      console.log("Frame captured, dimensions:", canvas.width, "x", canvas.height);
      
      // Convert to blob for sending
      const blob = await new Promise(resolve => {
        canvas.toBlob(resolve, 'image/jpeg', 0.95); // Higher quality
      });
      
      if (!blob || blob.size < 1000) {
        console.error("Generated blob is invalid or too small:", blob?.size, "bytes");
        return;
      }
      
      console.log("Image blob created, size:", blob.size, "bytes");
      
      // Create form data to send
      const formData = new FormData();
      formData.append('challenge_id', activeChallengeId);
      formData.append('video_frame', blob, 'frame.jpg');
      
      // Log what we're sending
      console.log("Sending liveness check with challenge_id:", activeChallengeId);
      
      // Send to API for liveness check
      const response = await fetch('http://localhost:8001/auth/check-liveness', {
        method: 'POST',
        body: formData
      });
      
      console.log("Liveness check API response status:", response.status);
      
      if (!response.ok) {
        const errorText = await response.text();
        console.error(`Liveness check API error: ${response.status}`, errorText);
        throw new Error(`Server error: ${response.status}`);
      }
      
      const result = await response.json();
      console.log("Liveness check result:", result);
      setDebugInfo(result);
      
      // Always update the check count when we get a response
      setCheckCount(prevCount => prevCount + 1);
      
      // Update status message based on result
      if (result.success) {
        // Challenge was completed successfully
        clearInterval(intervalRef.current);
        clearInterval(checkIntervalRef.current);
        setStatus('verified');
        setMessage(result.message || "Liveness verified successfully!");
        
        // Record successful liveness check to session if a sessionId exists
        if (sessionId) {
          try {
            await fetch(`http://localhost:8001/proctor/record-liveness-check`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                session_id: sessionId,
                result: {
                  success: true,
                  challenge_completed: true,
                  message: "Liveness verification passed"
                }
              })
            });
          } catch (error) {
            console.error("Failed to record liveness result:", error);
          }
        }
        
        // Auto stop after success
        setTimeout(stopEverything, 2000);
      } else if (result.message && result.message.toLowerCase().includes("no face detected")) {
        setMessage('No face detected. Please position your face in the frame.');
      } else if (result.challenge_completed) {
        setMessage(`Challenge completed! Verifying liveness...`);
      } else {
        // Challenge still in progress
        setMessage(`${challengeText} - ${countdown}s remaining`);
      }
    } catch (error) {
      console.error('Error during liveness check:', error);
      setMessage(`Error checking liveness: ${error.message}`);
    }
  }, 500); // Check more frequently (twice per second)
};
  // Continuously check liveness
  // Improved startContinuousCheck function with better debugging

  
  // Clean up resources and end the session
  const stopEverything = async () => {
    // Stop video stream
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(track => track.stop());
      streamRef.current = null;
    }
    
    // Clear all intervals
    if (checkIntervalRef.current) {
      clearInterval(checkIntervalRef.current);
    }
    
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
    
    // Clear video source
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    
    // End the assessment session if one was started
    if (sessionId && status !== 'idle') {
      try {
        await fetch(`http://localhost:8001/session/end`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            session_id: sessionId
          })
        });
      } catch (error) {
        console.error("Failed to end session:", error);
      }
    }
  };
  
  // Retry the process
  const handleRetry = async () => {
    // Clean up everything first
    await stopEverything();
    
    // Reset all state variables
    setStatus('idle');
    setMessage('Click Start to begin liveness verification');
    setCheckCount(0);
    setDebugInfo({});
    setChallengeId(null);
    setChallengeType(null);
    setChallengeText('');
    setCountdown(0);
    setSessionId(null);
  };
  
  // Clean up on component unmount
  useEffect(() => {
    return stopEverything;
  }, []);
  
  return (
    <div className="w-full max-w-md mx-auto p-4 bg-white rounded shadow">
      <h2 className="text-xl font-bold mb-4">Liveness Detection</h2>
      
      {/* Video feed container */}
      <div className="relative mb-4 bg-gray-100 rounded overflow-hidden">
        {status !== 'idle' && (
          <video 
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-64 object-cover"
          />
        )}
        
        {status === 'idle' && (
          <div className="w-full h-64 flex items-center justify-center bg-gray-200">
            <span className="text-gray-500">Camera off</span>
          </div>
        )}
        
        {/* Challenge overlay */}
        {status === 'challenge' && (
          <div className="absolute inset-0 bg-black bg-opacity-20 flex flex-col items-center justify-center text-white p-4">
            <div className="bg-black bg-opacity-70 p-3 rounded text-center">
              <div className="text-xl mb-2">{challengeText}</div>
              <div className="text-sm">Time remaining: {countdown}s</div>
            </div>
          </div>
        )}
        
        {/* Status indicator overlay */}
        {status === 'challenge' && (
          <div className="absolute top-2 right-2 bg-black bg-opacity-50 text-white p-2 rounded">
            Checks: {checkCount}
          </div>
        )}
      </div>
      
      {/* Status message */}
      <div className={`mb-4 p-3 rounded text-center ${
        status === 'verified' || status === 'success' ? 'bg-green-100 text-green-800' :
        status === 'error' || status === 'timeout' ? 'bg-red-100 text-red-800' :
        'bg-blue-100 text-blue-800'
      }`}>
        {message}
      </div>
      
      {/* Controls */}
      <div className="flex justify-center gap-4 mb-4">
        {status === 'idle' && (
          <button 
            onClick={startLivenessCheck}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Start
          </button>
        )}
        
        {status !== 'idle' && (
          <button 
            onClick={handleRetry}
            className="px-4 py-2 bg-gray-500 text-white rounded hover:bg-gray-600"
          >
            {(status === 'verified' || status === 'success' || status === 'error' || status === 'timeout') ? 
              'Try Again' : 'Reset'}
          </button>
        )}
        
        <button 
          onClick={() => setShowDebug(!showDebug)}
          className="px-4 py-2 bg-gray-200 text-gray-800 rounded hover:bg-gray-300"
        >
          {showDebug ? 'Hide Details' : 'Show Details'}
        </button>
      </div>
      
      {/* Debug information */}
      {showDebug && Object.keys(debugInfo).length > 0 && (
        <div className="mt-4 p-3 bg-gray-100 rounded text-xs">
          <h3 className="font-bold mb-2">Debug Information:</h3>
          <pre className="whitespace-pre-wrap">
            {JSON.stringify(debugInfo, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}