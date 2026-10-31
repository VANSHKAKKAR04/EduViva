import React, { useRef, useState, useEffect } from "react";

// WebSocket connection settings
const WS_URL = "ws://localhost:8000/ws/audio";
const WS_RETRY_DELAY = 2000; // 2 seconds
const WS_MAX_RETRIES = 3;

const VoiceAuth = ({ candidateId = "user123" }) => {
  const [status, setStatus] = useState("Click to start");
  const [mode, setMode] = useState("enroll"); // "enroll" or "verify"
  const [result, setResult] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [serverStatus, setServerStatus] = useState("unchecked"); // "unchecked", "online", "offline"
  
  const audioContext = useRef(null);
  const audioStream = useRef(null);
  const socket = useRef(null);
  const processor = useRef(null);
  const silenceTimeout = useRef(null);
  const wsRetryCount = useRef(0);

  // Check server connection on component mount
  useEffect(() => {
    checkServerStatus();
  }, []);

  // Check if the server is running
  const checkServerStatus = async () => {
    try {
      const response = await fetch("http://localhost:8000/ping");
      if (response.ok) {
        setServerStatus("online");
      } else {
        setServerStatus("offline");
      }
    } catch (error) {
      console.error("Server check failed:", error);
      setServerStatus("offline");
    }
  };

  // Initialize AudioContext
  useEffect(() => {
    // Create AudioContext only once
    if (!audioContext.current) {
      try {
        audioContext.current = new (window.AudioContext || window.webkitAudioContext)({
          sampleRate: 16000,
        });
      } catch (error) {
        console.error("Failed to initialize AudioContext:", error);
        setStatus("Audio system not available");
      }
    }

    // Cleanup function
    return () => {
      stopRecording();
    };
  }, []);

  const connectWebSocket = () => {
    return new Promise((resolve, reject) => {
      if (serverStatus === "offline") {
        reject(new Error("Server is not available"));
        return;
      }

      if (socket.current && socket.current.readyState === WebSocket.OPEN) {
        resolve(socket.current);
        return;
      }

      // Create new WebSocket connection
      console.log("Attempting to connect to WebSocket...");
      const ws = new WebSocket(WS_URL);
      
      // Set timeout for connection
      const connectionTimeout = setTimeout(() => {
        if (ws.readyState !== WebSocket.OPEN) {
          console.error("WebSocket connection timeout");
          ws.close();
          reject(new Error("Connection timeout"));
        }
      }, 5000);
      
      ws.onopen = () => {
        console.log("WebSocket connected successfully");
        clearTimeout(connectionTimeout);
        socket.current = ws;
        wsRetryCount.current = 0;
        resolve(ws);
      };
      
      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        clearTimeout(connectionTimeout);
        
        // Try to reconnect if not exceeded max retries
        if (wsRetryCount.current < WS_MAX_RETRIES) {
          wsRetryCount.current++;
          console.log(`Retrying connection (${wsRetryCount.current}/${WS_MAX_RETRIES})...`);
          setTimeout(() => {
            connectWebSocket()
              .then(resolve)
              .catch(reject);
          }, WS_RETRY_DELAY);
        } else {
          setServerStatus("offline");
          reject(new Error("Failed to connect after multiple attempts"));
        }
      };
      
      ws.onclose = () => {
        console.log("WebSocket connection closed");
      };
    });
  };

  const startMicrophone = async () => {
    try {
      // Get microphone stream
      audioStream.current = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      
      setStatus("Recording... (speak now)");
      setIsRecording(true);
      
      // Create audio source from microphone
      const source = audioContext.current.createMediaStreamSource(audioStream.current);
      
      // Create script processor for audio processing
      processor.current = audioContext.current.createScriptProcessor(4096, 1, 1);
      
      // Process audio data
      processor.current.onaudioprocess = (e) => {
        if (socket.current && socket.current.readyState === WebSocket.OPEN) {
          // Get audio data
          const inputData = e.inputBuffer.getChannelData(0);
          
          // Convert to 16-bit PCM
          const pcmData = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            pcmData[i] = inputData[i] * 0x7FFF;
          }
          
          // Send audio chunk to server
          const blob = new Blob([pcmData], { type: 'audio/pcm' });
          
          // Convert blob to base64
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64data = reader.result.split(',')[1];
            socket.current.send(JSON.stringify({
              audio: base64data
            }));
          };
          reader.readAsDataURL(blob);
        }
      };
      
      // Connect audio processing pipeline
      source.connect(processor.current);
      processor.current.connect(audioContext.current.destination);
    } catch (err) {
      setStatus(`❌ Microphone access denied: ${err.message}`);
    }
  };

  const stopRecording = () => {
    setIsRecording(false);
    
    // Stop microphone stream if it exists
    if (audioStream.current) {
      audioStream.current.getTracks().forEach(track => track.stop());
      audioStream.current = null;
    }
    
    // Disconnect processor if it exists
    if (processor.current) {
      processor.current.disconnect();
      processor.current = null;
    }
    
    // Close WebSocket if it exists
    if (socket.current && socket.current.readyState === WebSocket.OPEN) {
      socket.current.close();
      socket.current = null;
    }
    
    if (silenceTimeout.current) {
      clearTimeout(silenceTimeout.current);
      silenceTimeout.current = null;
    }
  };

  const handleToggleRecording = () => {
    if (isRecording) {
      stopRecording();
      setStatus("Recording stopped");
    } else {
      setResult(null);
      startRecording();
    }
  };

  const handleModeChange = (newMode) => {
    if (!isRecording) {
      setMode(newMode);
      setResult(null);
      setStatus("Click to start");
    }
  };

  return (
    <div className="bg-gray-100 p-6 rounded-lg shadow-md max-w-md mx-auto">
      <h2 className="text-2xl font-bold mb-4">🎙️ Voice Authentication</h2>
      
      {/* Server Status Indicator */}
      <div className={`px-3 py-2 mb-4 rounded text-sm ${
        serverStatus === "online" 
          ? "bg-green-100 text-green-800" 
          : serverStatus === "offline" 
            ? "bg-red-100 text-red-800"
            : "bg-yellow-100 text-yellow-800"
      }`}>
        <div className="flex items-center">
          <div className={`w-3 h-3 rounded-full mr-2 ${
            serverStatus === "online" 
              ? "bg-green-500" 
              : serverStatus === "offline" 
                ? "bg-red-500"
                : "bg-yellow-500"
          }`}></div>
          <span>
            {serverStatus === "online" 
              ? "Server Online" 
              : serverStatus === "offline" 
                ? "Server Offline - Check server status" 
                : "Checking server status..."}
          </span>
        </div>
      </div>
      
      <div className="flex space-x-4 mb-4">
        <label className="flex items-center space-x-2">
          <input
            type="radio"
            name="mode"
            value="enroll"
            checked={mode === "enroll"}
            onChange={() => handleModeChange("enroll")}
            disabled={isRecording || serverStatus === "offline"}
            className="form-radio h-4 w-4 text-blue-600"
          />
          <span>Enroll</span>
        </label>
        
        <label className="flex items-center space-x-2">
          <input
            type="radio"
            name="mode"
            value="verify"
            checked={mode === "verify"}
            onChange={() => handleModeChange("verify")}
            disabled={isRecording || serverStatus === "offline"}
            className="form-radio h-4 w-4 text-blue-600"
          />
          <span>Verify</span>
        </label>
      </div>
      
      <div className="mb-4">
        <p className="text-sm text-gray-600 mb-2">
          {mode === "enroll" 
            ? "Record your voice to create a voice profile" 
            : "Speak to verify your identity against your stored voice profile"}
        </p>
        <div className="font-medium">Candidate ID: {candidateId}</div>
      </div>
      
      <button
        onClick={handleToggleRecording}
        disabled={serverStatus === "offline" || serverStatus === "unchecked"}
        className={`w-full py-3 px-4 text-white font-medium rounded-md transition-colors duration-300 ${
          isRecording
            ? "bg-red-500 hover:bg-red-600"
            : serverStatus === "offline" 
              ? "bg-gray-400 cursor-not-allowed"
              : "bg-blue-500 hover:bg-blue-600"
        }`}
      >
        {isRecording ? "Stop Recording" : status}
      </button>
      
      {result && (
        <div className={`mt-4 p-3 rounded-md ${result.match ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}>
          <div className="font-bold">
            {result.match ? "✅ Voice Verified" : "❌ Voice Verification Failed"}
          </div>
          <div className="text-sm mt-1">
            Similarity Score: {result.score.toFixed(3)}
          </div>
        </div>
      )}
      
      <div className="mt-6 text-xs text-gray-500">
        <p>Voice authentication using WebSockets for real-time processing.</p>
        <p>Speak clearly and naturally for best results.</p>
      </div>
      
      {/* Debug button to manually check server status */}
      <button 
        onClick={checkServerStatus}
        className="mt-4 text-xs text-blue-500 hover:text-blue-700"
      >
        Check server connection
      </button>
    </div>
  );
};

export default VoiceAuth;