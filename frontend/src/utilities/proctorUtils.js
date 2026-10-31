// Utility functions for Proctor.jsx
// Accept all required state and callbacks as arguments for modularity

export const connectWebSocket = ({
  sessionId,
  setIsConnected,
  setWebsocket,
  setWebsocketReady,
  notify,
  addLog,
  handleWebSocketMessage,
  reconnect = true,
}) => {
  if (!sessionId) return;
  try {
    const ws = new WebSocket(`ws://localhost:8000/ws/proctoring/${sessionId}`);
    ws.onopen = () => {
      setIsConnected(true);
      setWebsocket(ws);
      setWebsocketReady(true);
      notify("WebSocket connected to backend", "success");
      addLog("Real WebSocket connection established");
    };
    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        handleWebSocketMessage(message);
      } catch (error) {
        addLog(`Error parsing WebSocket message: ${error.message}`, "error");
      }
    };
    ws.onclose = (event) => {
      setIsConnected(false);
      setWebsocket(null);
      setWebsocketReady(false);
      addLog(`WebSocket closed: ${event.code} - ${event.reason}`, "warning");
      if (event.code !== 1000 && reconnect) {
        setTimeout(() => {
          addLog("Attempting to reconnect...", "info");
          connectWebSocket({
            sessionId,
            setIsConnected,
            setWebsocket,
            setWebsocketReady,
            notify,
            addLog,
            handleWebSocketMessage,
            reconnect,
          });
        }, 3000);
      }
    };
    ws.onerror = (error) => {
      setWebsocketReady(false);
      addLog(`WebSocket error: ${error}`, "error");
      notify("WebSocket connection error", "error");
    };
  } catch (error) {
    setWebsocketReady(false);
    addLog(`Failed to create WebSocket: ${error.message}`, "error");
    notify("Failed to connect to backend", "error");
  }
};

export const fetchSessionReport = async ({
  sessionId,
  setSessionReport,
  addLog,
  notify,
}) => {
  if (!sessionId) return null;
  try {
    const response = await fetch(
      `http://localhost:8000/api/proctoring/session/${sessionId}/report`
    );
    if (response.ok) {
      const report = await response.json();
      if (report.status === "incomplete") {
        addLog(`Session not completed yet: ${report.message}`, "warning");
        notify("Assessment not completed yet", "warning");
        return null;
      }
      setSessionReport(report);
      addLog(`Session report received for ${report.session_id}`, "success");
      addLog(
        `Assessment: ${report.monitoring_summary?.overall_assessment}`,
        "info"
      );
      addLog(
        `Total violations: ${report.monitoring_summary?.total_violations || 0}`,
        "info"
      );
      addLog(
        `Critical violations: ${report.monitoring_summary?.critical_violations || 0}`,
        "info"
      );
      addLog(
        `Attention score: ${report.monitoring_summary?.attention_score || 0}%`,
        "info"
      );
      addLog(
        `Integrity score: ${report.monitoring_summary?.integrity_score || 0}%`,
        "info"
      );
      const assessment = report.monitoring_summary?.overall_assessment;
      if (assessment === "PASS") {
        notify("Session analysis complete - Assessment PASSED", "success");
      } else if (assessment === "REVIEW_REQUIRED") {
        notify("Session analysis complete - Review Required", "warning");
      } else {
        notify("Session analysis complete", "info");
      }
      if (report.violations && report.violations.length > 0) {
        addLog(`${report.violations.length} violations detected:`, "warning");
        report.violations.forEach((violation, index) => {
          addLog(
            `  ${index + 1}. ${violation.type || "Unknown"} (${
              violation.severity || "Unknown"
            })`,
            "warning"
          );
        });
      }
      if (report.recommendations && report.recommendations.length > 0) {
        addLog(
          `${report.recommendations.length} recommendations generated`,
          "info"
        );
        report.recommendations.forEach((rec, index) => {
          addLog(`  ${index + 1}. ${rec}`, "info");
        });
      }
      return report;
    } else {
      if (response.status === 404) {
        addLog("Session not found", "error");
        notify("Session not found", "error");
      } else {
        addLog(
          `Failed to fetch report: ${response.status} ${response.statusText}`,
          "error"
        );
        notify("Failed to fetch session report", "error");
      }
      return null;
    }
  } catch (error) {
    addLog(`Error fetching report: ${error.message}`, "error");
    notify("Error fetching session report", "error");
    return null;
  }
};

export const initializeMedia = async ({
  videoRef,
  canvasRef,
  setIsVideoEnabled,
  setIsAudioEnabled,
  setMediaStream,
  setAudioStream,
  addLog,
  notify,
}) => {
  addLog("Initializing media devices...", "info");
  try {
    const videoConstraints = {
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
        facingMode: "user",
      },
    };
    const audioConstraints = {
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 44100,
      },
    };
    try {
      const videoStream = await navigator.mediaDevices.getUserMedia(
        videoConstraints
      );
      setIsVideoEnabled(true);
      if (videoRef.current) {
        videoRef.current.srcObject = videoStream;
      }
      addLog("Video initialized successfully", "success");
      try {
        const audioStream = await navigator.mediaDevices.getUserMedia(
          audioConstraints
        );
        setAudioStream(audioStream);
        setIsAudioEnabled(true);
        addLog("Audio initialized successfully", "success");
        const combinedStream = new MediaStream([
          ...videoStream.getVideoTracks(),
          ...audioStream.getAudioTracks(),
        ]);
        setMediaStream(combinedStream);
      } catch (audioError) {
        addLog(
          "Audio initialization failed: " + audioError.message,
          "warning"
        );
        setMediaStream(videoStream);
        notify(
          "Camera access granted, but microphone access denied. Voice features will be limited.",
          "warning"
        );
      }
    } catch (videoError) {
      addLog("Video initialization failed: " + videoError.message, "error");
      try {
        const audioStream = await navigator.mediaDevices.getUserMedia(
          audioConstraints
        );
        setAudioStream(audioStream);
        setMediaStream(audioStream);
        setIsAudioEnabled(true);
        addLog("Audio-only mode initialized", "success");
        notify(
          "Camera access denied, but microphone access granted. Video features will be limited.",
          "warning"
        );
      } catch (audioError) {
        addLog("Both video and audio initialization failed", "error");
        notify(
          "Please allow camera and microphone access to continue",
          "error"
        );
      }
    }
  } catch (error) {
    addLog("Error accessing media devices: " + error.message, "error");
    notify("Media device access failed: " + error.message, "error");
  }
};

// handleWebSocketMessage is best left as a callback in the main component due to its deep state dependencies.
// If you want to move it, you must pass all state/setters it needs as arguments.
