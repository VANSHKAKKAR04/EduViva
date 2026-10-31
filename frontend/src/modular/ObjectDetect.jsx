import React, { useRef, useState, useEffect } from "react";
import Webcam from "react-webcam";

const ObjectDetect = () => {
  const webcamRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [uploadMessage, setUploadMessage] = useState("");
  const [violations, setViolations] = useState([]);
  const [ws, setWs] = useState(null);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [timestamp, setTimestamp] = useState("");
  const [alert, setAlert] = useState(false);

  const captureAndUpload = async () => {
    if (!isWebcamReady) {
      alert("Camera is not ready yet. Please wait...");
      return;
    }

    setUploadMessage("Capturing candidate image...");
    setIsUploaded(false);
    
    try {
      const blob = await captureFrame();
      if (!blob) {
        throw new Error("Failed to capture frame");
      }

      const formData = new FormData();
      formData.append('file', blob, 'candidate.jpg');

      setUploadMessage("Processing candidate image...");
      
      const response = await fetch(`${API_BASE_URL}/capture-candidate`, {
        method: 'POST',
        body: formData,
      });
      const data = await response.json();
      setUploadMessage(data.message);
      console.log("Upload Response:", data);
    } catch (error) {
      console.error("Upload failed:", error);
      setUploadMessage(`❌ Upload failed: ${error.message}`);
    }
  };

  const performDetection = async () => {
    if (!isWebcamReady || !isUploaded) return;

    try {
      const blob = await captureFrame();
      if (!blob) return;

      const formData = new FormData();
      formData.append('file', blob, 'frame.jpg');

      const response = await fetch(`${API_BASE_URL}/detect-objects`, {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        setDetectionResult(result);
      }
    } catch (error) {
      console.error("Detection failed:", error);
    }
  };

  const startWebSocket = () => {
    const socket = new WebSocket("ws://localhost:8000/ws/monitor");
    setWs(socket);
    setIsMonitoring(true);

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.error) {
        alert(data.error);
        stopWebSocket();
      } else {
        setViolations(data.violations);
        setTimestamp(data.timestamp);
        setAlert(data.alert);
      }
    };

    socket.onclose = () => {
      console.log("WebSocket closed");
      setIsMonitoring(false);
    };

    socket.onerror = (err) => {
      console.error("WebSocket error", err);
      alert("WebSocket error occurred.");
      stopWebSocket();
    };
  };

  const stopWebSocket = () => {
    if (ws) {
      ws.close();
    }
    setIsMonitoring(false);
    setWs(null);
    setViolations([]);
    setTimestamp("");
    setAlert(false);
  };

  useEffect(() => {
    return () => {
      if (ws) ws.close();
    };
  }, [ws]);

  return (
    <div
      style={{
        padding: "20px",
        maxWidth: "600px",
        margin: "auto",
        textAlign: "center",
      }}
    >
      <Webcam
        ref={webcamRef}
        screenshotFormat="image/jpeg"
        width={480}
        height={360}
      />

      <div style={{ marginTop: "20px" }}>
        <button
          onClick={captureAndUpload}
          style={{
            padding: "10px 20px",
            backgroundColor: "#007bff",
            color: "white",
            marginRight: "10px",
            border: "none",
            borderRadius: "5px",
            cursor: "pointer",
          }}
        >
          Capture & Upload
        </button>

        {!isMonitoring ? (
          <button
            onClick={startWebSocket}
            style={{
              padding: "10px 20px",
              backgroundColor: "#28a745",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: "pointer",
            }}
          >
            Start Monitoring
          </button>
        ) : (
          <button
            onClick={stopWebSocket}
            style={{
              padding: "10px 20px",
              backgroundColor: "#dc3545",
              color: "white",
              border: "none",
              borderRadius: "5px",
              cursor: "pointer",
            }}
          >
            Stop Monitoring
          </button>
        )}
      </div>

      {uploadMessage && (
        <p style={{ marginTop: "15px", color: "#555" }}>{uploadMessage}</p>
      )}

      {isMonitoring && (
        <p style={{ color: "orange", marginTop: "15px" }}>
          Monitoring in progress... ({timestamp})
        </p>
      )}

      {alert && (
        <div style={{ textAlign: "left", marginTop: "20px" }}>
          <h4 style={{ color: "red" }}>ALERT: Violations Detected!</h4>
          <ul>
            {violations.map((v, idx) => (
              <li key={idx}>{v}</li>
            ))}
          </ul>
          <p>Last Checked: {timestamp}</p>
        </div>
      )}
    </div>
  );
};

export default ObjectDetect;