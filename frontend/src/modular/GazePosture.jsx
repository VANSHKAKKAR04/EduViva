import React, { useState, useEffect, useRef } from 'react';
import './GazePosture.css';

function GazePosture() {
  const [connected, setConnected] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const [isTracking, setIsTracking] = useState(false);
  const [results, setResults] = useState({
    gaze: { status: 'Not tracking', looking_away: false, confidence: 0 },
    posture: { status: 'Not tracking', proper_posture: false, confidence: 0 }
  });
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [selectedView, setSelectedView] = useState('live');
  const [cameraPermission, setCameraPermission] = useState(false);
  const [connectionAttempts, setConnectionAttempts] = useState(0);
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const wsRef = useRef(null);
  const streamRef = useRef(null);
  const requestAnimationRef = useRef(null);
  
  // Generate a random session ID if not already set
  useEffect(() => {
    if (!sessionId) {
      const newSessionId = `session_${Math.random().toString(36).substring(2, 9)}`;
      setSessionId(newSessionId);
      console.log('[SessionID] Generated new session ID:', newSessionId);
    }
  }, [sessionId]);
  
  // Enhanced logging for debugging
  useEffect(() => {
    console.log('[DEBUG] Current state:', {
      connected,
      sessionId,
      isTracking,
      cameraPermission,
      wsReadyState: wsRef.current ? wsRef.current.readyState : 'not initialized',
      connectionAttempts
    });
  }, [connected, sessionId, isTracking, cameraPermission, connectionAttempts]);
  
  // Initialize WebSocket connection
  const connectWebSocket = () => {
    if (wsRef.current) {
      console.log('[WebSocket] Closing existing connection');
      wsRef.current.close();
    }
    
    const wsUrl = `ws://localhost:8000/ws/${sessionId}`;
    console.log('[WebSocket] Attempting to connect to:', wsUrl);
    
    try {
      wsRef.current = new WebSocket(wsUrl);
      setConnectionAttempts(prev => prev + 1);
      console.log('[WebSocket] Connection object created, waiting for open event');
      
      wsRef.current.onopen = () => {
        console.log('[WebSocket] Connection established successfully');
        setConnected(true);
        setError('');
        // Send a test message to verify connection
        wsRef.current.send(JSON.stringify({ type: 'ping', message: 'Connection test' }));
        console.log('[WebSocket] Test message sent');
      };
      
      wsRef.current.onmessage = (event) => {
        console.log('[WebSocket] Message received:', event.data.substring(0, 200) + (event.data.length > 200 ? '...' : ''));
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'analysis_result') {
            console.log('[WebSocket] Analysis result received:', {
              gaze: data.gaze ? {
                status: data.gaze.status,
                looking_away: data.gaze.looking_away,
                confidence: data.gaze.confidence
              } : 'No gaze data',
              posture: data.posture ? {
                status: data.posture.status,
                proper_posture: data.posture.proper_posture,
                confidence: data.posture.confidence
              } : 'No posture data'
            });
            setResults({
              gaze: data.gaze || results.gaze,
              posture: data.posture || results.posture
            });
          } else if (data.type === 'summary') {
            console.log('[WebSocket] Summary received:', data);
            setSummary(data.data);
            setSelectedView('summary');
          } else if (data.type === 'error') {
            console.error('[WebSocket] Error from server:', data.message);
            setError(data.message);
          } else if (data.type === 'pong') {
            console.log('[WebSocket] Pong received from server');
          } else if (data.type === 'connection_established') {
            console.log('[WebSocket] Connection confirmation from server:', data);
          } else {
            console.log('[WebSocket] Unknown message type received:', data.type);
          }
        } catch (parseError) {
          console.error('[WebSocket] Error parsing message:', parseError, event.data.substring(0, 100));
        }
      };
      
      wsRef.current.onerror = (error) => {
        console.error('[WebSocket] Error occurred:', error);
        setError(`WebSocket connection error: ${error.message || 'Unknown error'}`);
        setConnected(false);
      };
      
      wsRef.current.onclose = (event) => {
        console.log('[WebSocket] Connection closed', event.code, event.reason);
        setConnected(false);
        if (event.code !== 1000) {
          // Not a normal closure
          setError(`WebSocket connection closed: ${event.code} - ${event.reason || 'No reason provided'}`);
          
          // Try to reconnect after a delay if tracking is still active
          if (isTracking) {
            console.log('[WebSocket] Will attempt to reconnect in 3 seconds...');
            setTimeout(() => {
              console.log('[WebSocket] Attempting to reconnect...');
              connectWebSocket();
            }, 3000);
          }
        }
      };
    } catch (err) {
      console.error('[WebSocket] Failed to create WebSocket:', err);
      setError(`Failed to create WebSocket: ${err.message}`);
      setConnected(false);
    }
  };
  
  // Start camera stream
  const startCamera = async () => {
    console.log('[Camera] Requesting camera access...');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480 }
      });
      console.log('[Camera] Access granted, stream created');
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        streamRef.current = stream;
        setCameraPermission(true);
        setError('');
        console.log('[Camera] Video element configured with stream');
      } else {
        console.error('[Camera] Video reference not available');
      }
    } catch (err) {
      console.error('[Camera] Error accessing camera:', err);
      setError(`Camera access denied: ${err.message}. Please enable camera permissions.`);
      setCameraPermission(false);
    }
  };
  
  // Start tracking - simplified version using refs
  const startTracking = () => {
    console.log('[Tracking] Starting tracking session');
    if (!connected) {
      console.log('[Tracking] Not connected to WebSocket, initiating connection');
      connectWebSocket();
    } else {
      console.log('[Tracking] Already connected to WebSocket');
    }
    
    // Update both state and ref
    setIsTracking(true);
    isTrackingRef.current = true;
    
    console.log('[Tracking] Starting frame capture directly');
    captureFrames();
  };
  
  // Create a ref to track the isTracking state
  const isTrackingRef = useRef(false);
  
  // Stop tracking
  const stopTracking = () => {
    console.log('[Tracking] Stopping tracking session');
    setIsTracking(false);
    isTrackingRef.current = false; // Update ref
    if (requestAnimationRef.current) {
      cancelAnimationFrame(requestAnimationRef.current);
      console.log('[Tracking] Animation frame cancelled');
    }
  };
  
  // Get session summary
  const getSummary = () => {
    console.log('[Summary] Requesting session summary');
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      console.log('[Summary] Sending summary request via WebSocket');
      wsRef.current.send(JSON.stringify({ command: 'get_summary' }));
    } else {
      console.error('[Summary] WebSocket not ready, cannot request summary');
      setError('Cannot request summary - WebSocket connection is not open');
    }
  };
  
  // Capture frames from webcam using ref for tracking state
  const captureFrames = () => {
    // Check tracking state using ref instead of state to avoid closure issues
    console.log('[Frames] captureFrames called, isTrackingRef state:', isTrackingRef.current);
    
    if (!isTrackingRef.current) {
      console.log('[Frames] Not tracking (ref), frame capture stopped');
      return;
    }
    
    console.log('[Frames] Starting frame capture loop');
    
    const captureFrame = () => {
      // Double-check tracking state is still active using ref
      if (!isTrackingRef.current) {
        console.log('[Frames] Tracking stopped during capture loop (ref check)');
        return;
      }
      
      const video = videoRef.current;
      const canvas = canvasRef.current;
      
      if (video && canvas && video.readyState === 4) {
        const ctx = canvas.getContext('2d');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        // Convert canvas to base64 image
        const imageData = canvas.toDataURL('image/jpeg', 0.7);
        const imageSize = Math.round(imageData.length / 1024);
        // console.log(`[Frames] Frame captured, size: ${imageSize}KB`);
        
        // Send image to server via WebSocket if connected
        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
          // console.log('[Frames] Sending frame to server');
          try {
            wsRef.current.send(JSON.stringify({
              type: 'both',
              image: imageData
            }));
            // console.log('[Frames] Frame sent successfully');
          } catch (err) {
            // console.error('[Frames] Error sending frame:', err);
          }
        } else {
          console.warn('[Frames] WebSocket not ready, frame not sent', 
                      wsRef.current ? `State: ${wsRef.current.readyState}` : 'No WebSocket');
          
          // Try to reconnect if socket is closed
          if (wsRef.current && wsRef.current.readyState === WebSocket.CLOSED) {
            console.log('[Frames] WebSocket closed, attempting to reconnect');
            connectWebSocket();
          }
        }
      } else {
        console.warn('[Frames] Video or canvas not ready', 
                     video ? `Video state: ${video.readyState}` : 'No video ref',
                     canvas ? 'Canvas ready' : 'No canvas ref');
      }
      
      // Schedule next frame with requestAnimationFrame using ref check
      if (isTrackingRef.current) {
        requestAnimationRef.current = requestAnimationFrame(captureFrame);
      } else {
        console.log('[Frames] Tracking stopped (ref check), ending capture loop');
      }
    };
    
    // Start the capture loop
    captureFrame();
  };
  
  // Cleanup on component unmount
  useEffect(() => {
    return () => {
      console.log('[Cleanup] Component unmounting, cleaning up resources');
      if (requestAnimationRef.current) {
        cancelAnimationFrame(requestAnimationRef.current);
        console.log('[Cleanup] Animation frame cancelled');
      }
      
      if (wsRef.current) {
        wsRef.current.close();
        console.log('[Cleanup] WebSocket connection closed');
      }
      
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => {
          track.stop();
          console.log('[Cleanup] Camera track stopped');
        });
      }
    };
  }, []);
  
  // Reset session
  const resetSession = () => {
    console.log('[Reset] Resetting session');
    stopTracking();
    setSummary(null);
    setResults({
      gaze: { status: 'Not tracking', looking_away: false, confidence: 0 },
      posture: { status: 'Not tracking', proper_posture: false, confidence: 0 }
    });
    const newSessionId = `session_${Math.random().toString(36).substring(2, 9)}`;
    console.log('[Reset] New session ID:', newSessionId);
    setSessionId(newSessionId);
    setSelectedView('live');
    setConnected(false);
    setConnectionAttempts(0);
    isTrackingRef.current = false; // Reset tracking ref
  };
  
  // Check server connection manually
  const checkServerConnection = () => {
    console.log('[Connection] Checking server connection manually');
    try {
      // Try a simple fetch to check if server is responding
      fetch('http://localhost:8000/health')
        .then(response => {
          console.log('[Connection] Server response:', response.status);
          if (response.ok) {
            console.log('[Connection] Server is responding');
            setError('');
            connectWebSocket();
          } else {
            console.error('[Connection] Server responded with error:', response.status);
            setError(`Server check failed with status: ${response.status}`);
          }
        })
        .catch(err => {
          console.error('[Connection] Failed to reach server:', err);
          setError(`Failed to reach server: ${err.message}. Make sure the backend is running.`);
        });
    } catch (err) {
      console.error('[Connection] Error checking server:', err);
    }
  };
  
  // Format value as percentage
  const formatPercent = (value) => {
    return value ? `${Math.round(value)}%` : '0%';
  };
  
  // WebSocket status display
  const getConnectionStatus = () => {
    if (!wsRef.current) return 'Not initialized';
    
    switch (wsRef.current.readyState) {
      case WebSocket.CONNECTING:
        return 'Connecting...';
      case WebSocket.OPEN:
        return 'Connected';
      case WebSocket.CLOSING:
        return 'Closing...';
      case WebSocket.CLOSED:
        return 'Disconnected';
      default:
        return 'Unknown';
    }
  };
  
  return (
    <div className="app">
      <header className="header">
        <h1>Posture & Attention Monitor</h1>
        <div className="nav-tabs">
          <button 
            className={selectedView === 'live' ? 'active' : ''} 
            onClick={() => setSelectedView('live')}
          >
            Live Tracking
          </button>
          <button 
            className={selectedView === 'summary' ? 'active' : ''} 
            onClick={() => {
              if (isTracking) {
                getSummary();
              } else {
                setSelectedView('summary');
              }
            }}
          >
            Session Summary
          </button>
        </div>
      </header>
      
      <main className="main">
        {error && <div className="error-message">{error}</div>}
        
        {selectedView === 'live' && (
          <div className="live-view">
            <div className="connection-status">
              <span>WebSocket: </span>
              <span className={connected ? 'status-connected' : 'status-disconnected'}>
                {getConnectionStatus()}
              </span>
              <span> | Session ID: {sessionId}</span>
              <button 
                className="small-button" 
                onClick={checkServerConnection}
                title="Check if server is running"
              >
                Check Server
              </button>
              <button 
                className="small-button" 
                onClick={connectWebSocket}
                title="Try to reconnect WebSocket"
              >
                Reconnect
              </button>
            </div>
            
            <div className="camera-container">
              <video 
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="camera-feed"
                onCanPlay={() => {
                  console.log('[Camera] Video can play now');
                  videoRef.current.play();
                }}
              />
              <canvas ref={canvasRef} style={{ display: 'none' }} />
              
              {!cameraPermission && (
                <div className="camera-placeholder">
                  <p>Camera access required</p>
                  <button className="primary-button" onClick={startCamera}>
                    Enable Camera
                  </button>
                </div>
              )}
              
              {cameraPermission && !isTracking && (
                <div className="camera-overlay">
                  <p>Ready to start tracking</p>
                </div>
              )}
            </div>
            
            <div className="controls">
              {!cameraPermission ? (
                <button className="primary-button" onClick={startCamera}>
                  Enable Camera
                </button>
              ) : isTracking ? (
                <div className="tracking-controls">
                  <button className="secondary-button" onClick={stopTracking}>
                    Stop Tracking
                  </button>
                  <button className="primary-button" onClick={getSummary}>
                    View Results
                  </button>
                </div>
              ) : (
                <button className="primary-button" onClick={startTracking}>
                  Start Tracking
                </button>
              )}
            </div>
            
            <div className="results-panel">
              <div className={`result-card ${results.gaze.looking_away ? 'alert' : ''}`}>
                <h3>Gaze Tracking</h3>
                <div className="status">{results.gaze.status}</div>
                <div className="confidence">
                  Confidence: {Math.round(results.gaze.confidence * 100)}%
                </div>
              </div>
              
              <div className={`result-card ${!results.posture.proper_posture ? 'alert' : ''}`}>
                <h3>Posture Analysis</h3>
                <div className="status">{results.posture.status}</div>
                <div className="confidence">
                  Confidence: {Math.round(results.posture.confidence * 100)}%
                </div>
              </div>
            </div>
            
            <div className="debug-info">
              <h4>Debug Information</h4>
              <ul>
                <li>Connection attempts: {connectionAttempts}</li>
                <li>WebSocket status: {getConnectionStatus()}</li>
                <li>Tracking: {isTracking ? 'Active' : 'Inactive'}</li>
                <li>Camera: {cameraPermission ? 'Enabled' : 'Disabled'}</li>
              </ul>
            </div>
          </div>
        )}
        
        {selectedView === 'summary' && (
          <div className="summary-view">
            {summary ? (
              <>
                <div className="summary-header">
                  <h2>Session Summary</h2>
                  <div className="session-info">
                    <p>Session ID: {sessionId}</p>
                    <p>Duration: {Math.round(summary.duration_seconds)} seconds</p>
                  </div>
                </div>
                
                <div className="summary-cards">
                  <div className="summary-card">
                    <h3>Attention Score</h3>
                    <div className="score-circle">
                      <span>{Math.round(summary.gaze.attention_score)}</span>
                    </div>
                    <div className="summary-details">
                      <p>Looking away: {formatPercent(summary.gaze.looking_away_percent)}</p>
                      <p>Total frames analyzed: {summary.gaze.total_frames}</p>
                    </div>
                  </div>
                  
                  <div className="summary-card">
                    <h3>Posture Score</h3>
                    <div className="score-circle">
                      <span>{Math.round(summary.posture.posture_score)}</span>
                    </div>
                    <div className="summary-details">
                      <p>Bad posture: {formatPercent(summary.posture.bad_posture_percent)}</p>
                      <p>Total frames analyzed: {summary.posture.total_frames}</p>
                    </div>
                  </div>
                  
                  <div className="summary-card overall">
                    <h3>Overall Score</h3>
                    <div className="score-circle large">
                      <span>{Math.round(summary.overall_score)}</span>
                    </div>
                    <div className="feedback">
                      {summary.overall_score >= 90 ? "Excellent!" : 
                       summary.overall_score >= 75 ? "Good job!" : 
                       summary.overall_score >= 60 ? "Room for improvement" : 
                       "Needs significant improvement"}
                    </div>
                  </div>
                </div>
                
                <div className="summary-actions">
                  <button className="primary-button" onClick={resetSession}>
                    Start New Session
                  </button>
                </div>
              </>
            ) : (
              <div className="no-summary">
                <p>No session data available yet.</p>
                <p>Start tracking to collect data.</p>
                <button className="primary-button" onClick={() => setSelectedView('live')}>
                  Go to Tracking
                </button>
              </div>
            )}
          </div>
        )}
      </main>
      
      <footer className="footer">
        <p>Posture & Attention Monitor &copy; {new Date().getFullYear()}</p>
      </footer>
    </div>
  );
}

export default GazePosture;