import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  Camera,
  Mic,
  Play,
  Square,
  Eye,
  User,
  Shield,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Volume2,
  RotateCcw,
} from "lucide-react";
import { Toaster } from "react-hot-toast";
import SessionReportDisplay from "./Report";

// Toast component for notifications
const Toast = ({ message, type, onClose }) => (
  <div
    className={`fixed top-6 right-6 z-50 px-6 py-4 rounded shadow-lg flex items-center gap-3 transition-all duration-300
      ${
        type === "error"
          ? "bg-red-600 text-white"
          : type === "success"
          ? "bg-green-600 text-white"
          : "bg-blue-600 text-white"
      }
    `}
    role="alert"
  >
    {type === "error" && <XCircle className="w-6 h-6" />}
    {type === "success" && <CheckCircle className="w-6 h-6" />}
    {type === "info" && <Shield className="w-6 h-6" />}
    <span className="font-medium">{message}</span>
    <button onClick={onClose} className="ml-4 text-white/80 hover:text-white">
      ✕
    </button>
  </div>
);

// 1. REPLACE: Add your backend URL at the top
const BACKEND_WS_URL = "ws://localhost:8000/ws/proctoring"; // Replace with your FastAPI WebSocket URL
const BACKEND_API_URL = "http://localhost:8000/api/proctoring"; // Replace with your FastAPI API URL

const ProctoringTestInterface = () => {
  // Session state
  const [sessionId, setSessionId] = useState(null);
  const [sessionStatus, setSessionStatus] = useState("idle");
  const [websocket, setWebsocket] = useState(null);
  const [isConnected, setIsConnected] = useState(false);
  const [websocketReady, setWebsocketReady] = useState(false);
  const [sessionReport, setSessionReport] = useState(null);
  const [showReport, setShowReport] = useState(false);
  // Pre-assessment state
  const [preAssessmentSteps, setPreAssessmentSteps] = useState({
    liveness_check: { status: "pending", message: "", retryCount: 0 },
    face_enrollment: { status: "pending", message: "", retryCount: 0 },
    voice_enrollment: { status: "pending", message: "", retryCount: 0 },
    environment_check: { status: "pending", message: "", retryCount: 0 },
  });

  // Media state
  const [isVideoEnabled, setIsVideoEnabled] = useState(false);
  const [isAudioEnabled, setIsAudioEnabled] = useState(false);
  const [mediaStream, setMediaStream] = useState(null);
  const [isRecordingVoice, setIsRecordingVoice] = useState(false);
  const [audioStream, setAudioStream] = useState(null);

  // Processing state for individual steps
  const [processingSteps, setProcessingSteps] = useState({
    liveness_check: false,
    face_enrollment: false,
    voice_enrollment: false,
    environment_check: false,
  });

  // Monitoring state
  const [violations, setViolations] = useState([]);
  const [behaviorMetrics, setBehaviorMetrics] = useState({
    attention_score: 100,
    integrity_score: 100,
    total_gaze_away_time: 0,
    noise_incidents: 0,
    unauthorized_objects_detected: 0,
    face_verification_failures: 0,
  });

  // Logging
  const [logs, setLogs] = useState([]);
  const logRef = useRef(null);

  // Toast notifications
  const [toast, setToast] = useState(null);
  const showToast = (message, type = "info", duration = 4000) => {
    setToast({ message, type });
    setTimeout(() => setToast(null), duration);
  };

  // Refs
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const streamIntervalRef = useRef(null);
  const audioIntervalRef = useRef(null);
  const logsEndRef = useRef(null);

  // Form data
  const [candidateId, setCandidateId] = useState("test-candidate-001");
  const [examId, setExamId] = useState("exam-001");

  // Constants
  const MAX_RETRY_ATTEMPTS = 3;

  // Utility: Add log entry
  const addLog = useCallback((msg, type = "info") => {
    setLogs((prev) => [
      ...prev,
      {
        message: msg,
        type,
        timestamp: new Date().toLocaleTimeString(),
      },
    ]);
  }, []);

  // Toast and log helpers
  const notify = useCallback(
    (msg, type = "info") => {
      showToast(msg, type);
      addLog(msg, type);
    },
    [addLog]
  );

  // 2. REPLACE: The entire connectWebSocket function
  const connectWebSocket = useCallback(() => {
    if (!sessionId) return;
    try {
      // Real WebSocket connection instead of mock
      const ws = new WebSocket(`${BACKEND_WS_URL}/${sessionId}`);
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
        // Auto-reconnect logic (optional)
        if (event.code !== 1000) {
          setTimeout(() => {
            addLog("Attempting to reconnect...", "info");
            connectWebSocket();
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
  }, [sessionId, addLog, notify]);

  // 3. REPLACE: The createSession function to call real API
  const createSession = async () => {
    try {
      const response = await fetch(`${BACKEND_API_URL}/session/create`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          candidate_id: candidateId,
          exam_id: examId,
          timestamp: new Date().toISOString(),
        }),
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setSessionId(data.session_id);
      setSessionStatus("created");
      notify(`Session created: ${data.session_id}`, "success");
    } catch (error) {
      notify(`Error creating session: ${error.message}`, "error");
    }
  };

  // 5. REPLACE: Update startRealTimeMonitoring to remove mock violations
  // (Removed duplicate startRealTimeMonitoring function to fix redeclaration error)

  // 6. REPLACE: Update stopRealTimeMonitoring
  const stopRealTimeMonitoring = () => {
    if (streamIntervalRef.current) {
      if (streamIntervalRef.current.videoInterval) {
        clearInterval(streamIntervalRef.current.videoInterval);
      }
      if (streamIntervalRef.current.audioInterval) {
        clearInterval(streamIntervalRef.current.audioInterval);
      }
      streamIntervalRef.current = null;
      addLog("Stopped real-time monitoring");
    }
  };

  // 7. ADD: New function to fetch session report after completion

  const fetchSessionReport = async () => {
    if (!sessionId) return;

    try {
      const response = await fetch(
        `${BACKEND_API_URL}/session/${sessionId}/report`
      );

      if (response.ok) {
        const report = await response.json();

        // Handle incomplete session status
        if (report.status === "incomplete") {
          addLog(`Session not completed yet: ${report.message}`, "warning");
          notify("Assessment not completed yet", "warning");
          return null;
        }

        // Store report in state
        setSessionReport(report);
        setShowReport(true);
        // Show appropriate notification based on assessment
        const assessment = report.monitoring_summary?.overall_assessment;
        if (assessment === "PASS") {
          notify("Session analysis complete - Assessment PASSED", "success");
        } else if (assessment === "REVIEW_REQUIRED") {
          notify("Session analysis complete - Review Required", "warning");
        } else {
          notify("Session analysis complete", "info");
        }

        // Log violations if any
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

        // Log recommendations if any
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
        // Handle different HTTP error codes
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

  // Add state for liveness challenge
  const [livenessChallenge, setLivenessChallenge] = useState(null);
  const [livenessChallengeActive, setLivenessChallengeActive] = useState(false);
  const [livenessChallengeResult, setLivenessChallengeResult] = useState(null);
  const [livenessChallengeLoading, setLivenessChallengeLoading] =
    useState(false);

  // Liveness challenge timer and auto-frame sending
  const livenessTimerRef = useRef(null);
  const livenessFrameIntervalRef = useRef(null);
  const [livenessCountdown, setLivenessCountdown] = useState(10); // Will be set dynamically
  const [livenessTimeout, setLivenessTimeout] = useState(30); // Default 30s, updated from backend

  // When a liveness challenge is active, start timer and auto-send frames
  useEffect(() => {
    if (livenessChallengeActive && livenessChallenge) {
      console.log("[LIVENESS] Starting timer:", livenessTimeout, "seconds");
      setLivenessCountdown(livenessTimeout);
      // Start countdown (do not reset here, only in message handler)
      livenessTimerRef.current = setInterval(() => {
        setLivenessCountdown((prev) => {
          console.log("[LIVENESS] Countdown tick:", prev - 1);
          if (prev <= 1) {
            console.log("[LIVENESS] Timer expired, stopping intervals");
            clearInterval(livenessTimerRef.current);
            clearInterval(livenessFrameIntervalRef.current);
            setLivenessChallengeActive(false);
            setLivenessChallengeLoading(false);
            setLivenessChallengeResult({
              status: "failed",
              message: "Liveness challenge timed out. Please try again.",
            });
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      // Start sending frames every 500ms
      livenessFrameIntervalRef.current = setInterval(() => {
        const imageData = captureFrame();
        if (imageData && websocket && websocketReady) {
          console.log(
            "[LIVENESS] Sending frame for challenge",
            livenessChallenge.challenge_type,
            livenessChallenge.challenge_id
          );
          websocket.send(
            JSON.stringify({
              type: "liveness_check",
              image_data: imageData,
              challenge_type: livenessChallenge.challenge_type,
              challenge_id: livenessChallenge.challenge_id,
            })
          );
          setLivenessChallengeLoading(true);
        } else {
          console.log(
            "[LIVENESS] Skipped sending frame: missing imageData or websocket"
          );
        }
      }, 500);
    } else {
      console.log(
        "[LIVENESS] Timer not started: livenessChallengeActive:",
        livenessChallengeActive,
        "livenessChallenge:",
        livenessChallenge
      );
    }
    // Cleanup on challenge end
    return () => {
      console.log("[LIVENESS] Cleaning up intervals");
      clearInterval(livenessTimerRef.current);
      clearInterval(livenessFrameIntervalRef.current);
    };
  }, [
    livenessChallengeActive,
    livenessChallenge,
    websocket,
    websocketReady,
    livenessTimeout,
  ]);

  // When a liveness_challenge message is received, set timeout/countdown from backend

  // --- Real-time Metrics State ---
  const [realTimeMetrics, setRealTimeMetrics] = useState({
    gaze: null,
    posture: null,
    voice_verification: null,
    face_verification: null,
    object_detection: null,
    environment_noise: null,
  });

  // --- Update metrics on backend message ---
  const handleWebSocketMessage = (message) => {
    console.log("[WS] Received message:", message);
    addLog(`Received: ${JSON.stringify(message)}`);
    // --- Always log analysis messages for debugging ---
    if (
      message.type === "video_analysis" ||
      message.type === "audio_analysis"
    ) {
      // Log the analysis results to the browser console
      addLog(
        `[${message.type.toUpperCase()}] Raw Results: ${JSON.stringify(
          message.results
        )}`
      );
      if (!Array.isArray(message.results)) {
        addLog(
          `[${message.type.toUpperCase()}] WARNING: results is not an array! Type: ${typeof message.results}`,
          "warning"
        );
        console.warn(
          `[${message.type.toUpperCase()}] WARNING: results is not an array!`,
          message.results
        );
      }
      if (Array.isArray(message.results)) {
        let newMetrics = { ...realTimeMetrics };
        if (message.type === "video_analysis") {
          console.log(
            "[VIDEO_ANALYSIS] Received video_analysis message:",
            message
          );
          newMetrics.gaze = message.results[0] || null;
          newMetrics.posture = message.results[1] || null;
          newMetrics.object_detection = message.results[2] || null;
          newMetrics.face_verification = message.results[3] || null;
          console.log("[VIDEO_ANALYSIS] Setting metrics:", newMetrics);
        } else if (message.type === "audio_analysis") {
          console.log(
            "[AUDIO_ANALYSIS] Received audio_analysis message:",
            message
          );
          newMetrics.environment_noise = message.results[0] || null;
          newMetrics.voice_verification = message.results[1] || null;
          console.log("[AUDIO_ANALYSIS] Setting metrics:", newMetrics);
        }
        setRealTimeMetrics(newMetrics);
      }
    }
    switch (message.type) {
      case "pre_assessment_started":
        setSessionStatus("pre_assessment");
        notify("Pre-assessment started", "info");
        break;
      case "liveness_challenge":
        console.log("[WS] liveness_challenge received:", message);
        setLivenessChallenge({
          challenge_type: message.challenge_type,
          challenge_id: message.challenge_id,
          instructions: message.instructions,
        });
        setLivenessTimeout(message.timeout || 30); // Use backend-provided timeout
        setLivenessCountdown(message.timeout || 30); // Reset timer ONLY here
        setLivenessChallengeActive(true);
        setLivenessChallengeResult(null);
        setLivenessChallengeLoading(false);
        notify(`Liveness challenge: ${message.instructions}`, "info");
        break;
      case "liveness_check_result":
        console.log("[WS] liveness_check_result received:", message);
        if (message.challenge_type === "blink") {
          console.log("[LIVENESS][DEBUG] Blink result:", {
            status: message.status,
            msg: message.message,
            challenge_type: message.challenge_type,
            backend: message,
            local: {
              livenessChallengeActive,
              livenessChallenge,
              livenessCountdown,
              livenessTimeout,
              livenessChallengeResult,
              livenessChallengeLoading,
            },
          });
        }
        setProcessingSteps((prev) => ({ ...prev, liveness_check: false }));
        setPreAssessmentSteps((prev) => ({
          ...prev,
          liveness_check: {
            ...prev.liveness_check,
            status:
              message.status === "passed"
                ? "completed"
                : message.status === "failed"
                ? "failed"
                : "pending",
            message: message.message,
            retryCount:
              message.status === "failed"
                ? prev.liveness_check.retryCount
                : prev.liveness_check.retryCount,
          },
        }));
        setLivenessChallengeResult({
          status: message.status,
          message: message.message,
          challenge_type: message.challenge_type,
        });
        setLivenessChallengeLoading(false);
        if (message.status === "passed" || message.status === "failed") {
          setLivenessChallengeActive(false);
          console.log(
            "[LIVENESS] Challenge ended with status:",
            message.status
          );
        } else {
          // For 'pending', keep challenge active and timer running
          console.log("[LIVENESS] Challenge still pending, timer continues");
        }
        notify(
          `Liveness check ${
            message.status === "passed"
              ? "passed"
              : message.status === "failed"
              ? "failed"
              : "pending"
          }: ${message.message}`,
          message.status === "passed"
            ? "success"
            : message.status === "failed"
            ? "error"
            : "info"
        );
        break;
      case "face_enrollment_result":
        setProcessingSteps((prev) => ({ ...prev, face_enrollment: false }));
        setPreAssessmentSteps((prev) => ({
          ...prev,
          face_enrollment: {
            ...prev.face_enrollment,
            status: message.status === "success" ? "completed" : "failed",
            message: message.message,
            retryCount:
              message.status === "failed"
                ? prev.face_enrollment.retryCount
                : prev.face_enrollment.retryCount,
          },
        }));
        notify(
          `Face enrollment ${
            message.status === "success" ? "successful" : "failed"
          }: ${message.message}`,
          message.status === "success" ? "success" : "error"
        );
        break;
      case "voice_enrollment_result":
        setProcessingSteps((prev) => ({ ...prev, voice_enrollment: false }));
        setPreAssessmentSteps((prev) => ({
          ...prev,
          voice_enrollment: {
            ...prev.voice_enrollment,
            status: message.status === "success" ? "completed" : "failed",
            message: message.message,
            retryCount:
              message.status === "failed"
                ? prev.voice_enrollment.retryCount
                : prev.voice_enrollment.retryCount,
          },
        }));
        console.log(
          "[AUDIO][VOICE VERIFICATION]",
          message.status,
          message.message
        );
        notify(
          `Voice enrollment ${
            message.status === "success" ? "successful" : "failed"
          }: ${message.message}`,
          message.status === "success" ? "success" : "error"
        );
        break;
      case "environment_check_result":
        setProcessingSteps((prev) => ({ ...prev, environment_check: false }));
        setPreAssessmentSteps((prev) => ({
          ...prev,
          environment_check: {
            ...prev.environment_check,
            status: message.status === "approved" ? "completed" : "failed",
            message: message.message,
            retryCount:
              message.status === "failed"
                ? prev.environment_check.retryCount
                : prev.environment_check.retryCount,
          },
        }));
        console.log(
          "[AUDIO][ENVIRONMENT NOISE]",
          message.status,
          message.message
        );
        notify(
          `Environment check ${
            message.status === "approved" ? "approved" : "failed"
          }: ${message.message}`,
          message.status === "approved" ? "success" : "error"
        );
        break;
      case "pre_assessment_complete":
        setSessionStatus("authenticated");
        notify(
          "Pre-assessment complete. Ready to start assessment.",
          "success"
        );
        break;
      case "assessment_started":
        setSessionStatus("active");
        notify("Assessment started. Real-time monitoring active.", "info");
        startRealTimeMonitoring();
        break;
      case "violation_alert":
        // Remove identity violation messages from frontend
        if (
          message.violation &&
          message.violation.violation_type === "identity"
        ) {
          // Do not show or log identity violation
          return;
        }
        setViolations((prev) => [...prev, message.violation]);
        notify(
          `Violation: ${message.violation.violation_type} - ${message.violation.description}`,
          "error"
        );
        break;
      case "assessment_completed":
        setSessionStatus("completed");
        notify("Assessment completed.", "success");
        stopRealTimeMonitoring();
        // Fetch the analysis report
        setTimeout(() => {
          fetchSessionReport();
        }, 2000);
        break;

      default:
        addLog(`Unhandled message type: ${message.type}`, "warning");
    }
  };

  // Initialize media devices with better error handling
  const initializeMedia = async () => {
    addLog("Initializing media devices...", "info");
    try {
      // Request video and audio separately for better error handling
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

      // Get video stream
      try {
        const videoStream = await navigator.mediaDevices.getUserMedia(
          videoConstraints
        );
        setIsVideoEnabled(true);
        if (videoRef.current) {
          videoRef.current.srcObject = videoStream;
        }
        addLog("Video initialized successfully", "success");

        // Get audio stream separately
        try {
          const audioStream = await navigator.mediaDevices.getUserMedia(
            audioConstraints
          );
          setAudioStream(audioStream);
          setIsAudioEnabled(true);
          addLog("Audio initialized successfully", "success");

          // Combine streams
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
          setMediaStream(videoStream); // Use video-only stream
          notify(
            "Camera access granted, but microphone access denied. Voice features will be limited.",
            "warning"
          );
        }
      } catch (videoError) {
        addLog("Video initialization failed: " + videoError.message, "error");

        // Try audio-only if video fails
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

  // Start pre-assessment
  const startPreAssessment = () => {
    if (websocket && websocket.readyState === 1) {
      websocket.send(JSON.stringify({ type: "start_pre_assessment" }));
      addLog("Pre-assessment initiated", "info");
    }
  };

  // Capture frame for various checks
  const captureFrame = () => {
    if (!videoRef.current || !canvasRef.current) return null;
    const canvas = canvasRef.current;
    const video = videoRef.current;
    const context = canvas.getContext("2d");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    context.drawImage(video, 0, 0);
    return canvas.toDataURL("image/jpeg", 0.8);
  };

  // Perform liveness check
  const performLivenessCheck = () => {
    setProcessingSteps((prev) => ({ ...prev, liveness_check: true }));
    const imageData = captureFrame();
    if (imageData && websocket && websocketReady) {
      websocket.send(
        JSON.stringify({
          type: "liveness_check",
          image_data: imageData,
        })
      );
      addLog("Liveness check frame sent", "info");
    } else {
      setProcessingSteps((prev) => ({ ...prev, liveness_check: false }));
      notify("Unable to capture video frame for liveness check", "error");
    }
  };

  // Perform face enrollment
  const performFaceEnrollment = () => {
    setProcessingSteps((prev) => ({ ...prev, face_enrollment: true }));
    const imageData = captureFrame();
    if (imageData && websocket && websocketReady) {
      websocket.send(
        JSON.stringify({
          type: "face_enrollment",
          image_data: imageData,
        })
      );
      addLog("Face enrollment frame sent", "info");
    } else {
      setProcessingSteps((prev) => ({ ...prev, face_enrollment: false }));
      notify("Unable to capture video frame for face enrollment", "error");
    }
  };

  // Perform environment check
  const performEnvironmentCheck = () => {
    setProcessingSteps((prev) => ({ ...prev, environment_check: true }));
    if (websocket && websocketReady) {
      websocket.send(
        JSON.stringify({
          type: "environment_check",
          camera_access: isVideoEnabled,
          microphone_access: isAudioEnabled,
        })
      );
      addLog("Environment check request sent", "info");
    } else {
      setProcessingSteps((prev) => ({ ...prev, environment_check: false }));
      notify(
        "Unable to perform environment check: WebSocket not ready",
        "error"
      );
    }
  };

  // --- Audio Processing Utilities ---
  // Convert Float32Array PCM to 16-bit PCM (Int16)
  function floatTo16BitPCM(float32Array) {
    const int16Array = new Int16Array(float32Array.length);
    for (let i = 0; i < float32Array.length; i++) {
      let s = Math.max(-1, Math.min(1, float32Array[i]));
      int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return int16Array;
  }

  function writeString(view, offset, string) {
    for (let i = 0; i < string.length; i++) {
      view.setUint8(offset + i, string.charCodeAt(i));
    }
  }

  function encodeWav(int16Array, sampleRate = 16000) {
    const buffer = new ArrayBuffer(44 + int16Array.length * 2);
    const view = new DataView(buffer);
    writeString(view, 0, "RIFF");
    view.setUint32(4, 36 + int16Array.length * 2, true);
    writeString(view, 8, "WAVE");
    writeString(view, 12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(view, 36, "data");
    view.setUint32(40, int16Array.length * 2, true);
    for (let i = 0; i < int16Array.length; i++) {
      view.setInt16(44 + i * 2, int16Array[i], true);
    }
    return buffer;
  }

  // --- Voice Recording (Mono, 16kHz PCM, WAV) ---
  const audioBufferRef = useRef([]);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);

  const startVoiceRecording = async () => {
    if (!audioStream && !mediaStream) {
      notify("No audio stream available for voice recording", "error");
      return;
    }
    setIsRecordingVoice(true);
    setProcessingSteps((prev) => ({ ...prev, voice_enrollment: true }));
    audioBufferRef.current = [];
    try {
      const streamToUse = audioStream || mediaStream;
      const audioContext = new (window.AudioContext ||
        window.webkitAudioContext)({ sampleRate: 16000 });
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(streamToUse);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        audioBufferRef.current.push(new Float32Array(input));
      };
      source.connect(processor);
      processor.connect(audioContext.destination);
      processorRef.current = processor;
      addLog("Voice recording started (mono, 16kHz PCM)");
      // Stop after 5 seconds
      setTimeout(() => stopVoiceRecording("voice_enrollment"), 5000);
    } catch (error) {
      addLog(`Voice recording error: ${error.message}`, "error");
      notify(`Voice recording failed: ${error.message}`, "error");
      setIsRecordingVoice(false);
      setProcessingSteps((prev) => ({ ...prev, voice_enrollment: false }));
    }
  };

  const stopVoiceRecording = (purpose = "voice_enrollment") => {
    setIsRecordingVoice(false);
    if (processorRef.current) processorRef.current.disconnect();
    if (audioContextRef.current) audioContextRef.current.close();
    // Concatenate buffers
    let float32 = null;
    if (audioBufferRef.current.length > 0) {
      const length = audioBufferRef.current.reduce(
        (acc, arr) => acc + arr.length,
        0
      );
      float32 = new Float32Array(length);
      let offset = 0;
      for (const arr of audioBufferRef.current) {
        float32.set(arr, offset);
        offset += arr.length;
      }
    }
    if (!float32 || float32.length === 0) {
      notify("No audio captured.", "error");
      setProcessingSteps((prev) => ({ ...prev, voice_enrollment: false }));
      return;
    }
    const int16 = floatTo16BitPCM(float32);
    const wavBuffer = encodeWav(int16, 16000);
    const wavBlob = new Blob([wavBuffer], { type: "audio/wav" });
    const reader = new FileReader();
    reader.onloadend = () => {
      const base64data = reader.result.split(",")[1];
      if (websocket && websocketReady && websocket.readyState === 1) {
        websocket.send(
          JSON.stringify({
            type: purpose,
            audio_data: base64data,
            format: "wav",
            sample_rate: 16000,
            channels: 1,
            bit_depth: 16,
          })
        );
        addLog("Voice audio sent to backend (" + purpose + ")", "info");
      } else {
        addLog("WebSocket not available to send audio data", "error");
        setProcessingSteps((prev) => ({ ...prev, voice_enrollment: false }));
      }
    };
    reader.onerror = () => {
      addLog("Failed to read audio blob", "error");
      setProcessingSteps((prev) => ({ ...prev, voice_enrollment: false }));
    };
    reader.readAsDataURL(wavBlob);
  };

  // --- Real-time Audio Streaming (every 2s, mono 16kHz PCM, WAV) ---
  const startRealTimeMonitoring = () => {
    // Clear any previous intervals
    if (streamIntervalRef.current) {
      if (streamIntervalRef.current.videoInterval) {
        clearInterval(streamIntervalRef.current.videoInterval);
      }
      if (streamIntervalRef.current.audioInterval) {
        clearInterval(streamIntervalRef.current.audioInterval);
      }
      streamIntervalRef.current = null;
    }
    // Video frames every 2s
    const videoInterval = setInterval(() => {
      let reason = [];
      if (!videoRef.current) reason.push("videoRef missing");
      if (!canvasRef.current) reason.push("canvasRef missing");
      if (!websocketReady) reason.push("WebSocket not ready");
      const frameData = captureFrame();
      if (frameData && websocket && websocketReady) {
        websocket.send(
          JSON.stringify({
            type: "video_stream",
            frame_data: frameData,
            timestamp: new Date().toISOString(),
          })
        );
        addLog("[Frame] Video frame sent to backend for processing", "info");
      } else {
        addLog(
          `[Frame] Video frame NOT sent (${
            reason.length ? reason.join(", ") : "no frame"
          })`,
          "warning"
        );
      }
    }, 2000);
    // Audio streaming every 2s (if audio is enabled)
    const audioInterval = setInterval(() => {
      if (!audioStream && !mediaStream) {
        addLog("[Audio] Audio chunk NOT sent (no audio stream)", "warning");
        return;
      }
      audioBufferRef.current = [];
      try {
        const streamToUse = audioStream || mediaStream;
        const audioContext = new (window.AudioContext ||
          window.webkitAudioContext)({ sampleRate: 16000 });
        const source = audioContext.createMediaStreamSource(streamToUse);
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        processor.onaudioprocess = (e) => {
          const input = e.inputBuffer.getChannelData(0);
          audioBufferRef.current.push(new Float32Array(input));
        };
        source.connect(processor);
        processor.connect(audioContext.destination);
        setTimeout(() => {
          processor.disconnect();
          audioContext.close();
          let float32 = null;
          if (audioBufferRef.current.length > 0) {
            const length = audioBufferRef.current.reduce(
              (acc, arr) => acc + arr.length,
              0
            );
            float32 = new Float32Array(length);
            let offset = 0;
            for (const arr of audioBufferRef.current) {
              float32.set(arr, offset);
              offset += arr.length;
            }
          }
          if (!float32 || float32.length === 0) {
            addLog("[Audio] No audio captured for streaming", "warning");
            return;
          }
          const int16 = floatTo16BitPCM(float32);
          const wavBuffer = encodeWav(int16, 16000);
          const wavBlob = new Blob([wavBuffer], { type: "audio/wav" });
          const reader = new FileReader();
          reader.onloadend = () => {
            const base64data = reader.result.split(",")[1];
            if (websocket && websocketReady && websocket.readyState === 1) {
              websocket.send(
                JSON.stringify({
                  type: "audio_stream",
                  audio_data: base64data,
                  format: "wav",
                  sample_rate: 16000,
                  channels: 1,
                  bit_depth: 16,
                  timestamp: new Date().toISOString(),
                })
              );
              addLog(
                "[Audio] Audio chunk sent to backend for processing",
                "info"
              );
              console.log(
                "[AUDIO][STREAM] Audio chunk sent to backend for processing"
              );
            } else {
              addLog(
                "[Audio] Audio chunk NOT sent (WebSocket not ready)",
                "warning"
              );
              console.log(
                "[AUDIO][STREAM] Audio chunk NOT sent (WebSocket not ready)"
              );
            }
          };
          reader.onerror = () => {
            addLog("[Audio] Failed to read audio blob for streaming", "error");
            console.log(
              "[AUDIO][STREAM] Failed to read audio blob for streaming"
            );
          };
          reader.readAsDataURL(wavBlob);
        }, 1000); // Record 1s chunk
      } catch (err) {
        addLog(`[Audio] Error during audio streaming: ${err.message}`, "error");
      }
    }, 2000);
    streamIntervalRef.current = { videoInterval, audioInterval };
  };

  // Start the assessment after pre-assessment is complete
  const startAssessment = () => {
    if (websocket && websocketReady) {
      websocket.send(
        JSON.stringify({
          type: "start_assessment",
        })
      );
      addLog("Assessment start request sent", "info");
    } else {
      notify("Unable to start assessment: WebSocket not ready", "error");
    }
  };

  // End the assessment and stop monitoring
  const endAssessment = () => {
    if (websocket && websocketReady) {
      websocket.send(
        JSON.stringify({
          type: "end_assessment",
        })
      );
      addLog("Assessment end request sent", "info");
    } else {
      notify("Unable to end assessment: WebSocket not ready", "error");
    }
  };

  // Start monitoring only when sessionStatus is 'active' and websocketReady is true
  useEffect(() => {
    if (sessionStatus === "active" && websocketReady) {
      startRealTimeMonitoring();
    }
    // Clean up intervals if session deactivates
    return () => {
      if (streamIntervalRef.current) {
        if (streamIntervalRef.current.videoInterval) {
          clearInterval(streamIntervalRef.current.videoInterval);
        }
        if (streamIntervalRef.current.audioInterval) {
          clearInterval(streamIntervalRef.current.audioInterval);
        }
        streamIntervalRef.current = null;
      }
    };
  }, [sessionStatus, websocketReady]);

  // Connect WebSocket when session is created
  useEffect(() => {
    if (sessionId && !websocket) {
      connectWebSocket();
    }
  }, [sessionId, websocket, connectWebSocket]);

  // Initialize media on component mount
  useEffect(() => {
    initializeMedia();
    return () => {
      if (mediaStream) {
        mediaStream.getTracks().forEach((track) => track.stop());
      }
      if (audioStream) {
        audioStream.getTracks().forEach((track) => track.stop());
      }
      if (streamIntervalRef.current) {
        clearInterval(streamIntervalRef.current);
      }
      if (audioIntervalRef.current) {
        clearInterval(audioIntervalRef.current);
      }
    };
  }, []);

  // Auto-proceed to authenticated status when all steps are completed
  useEffect(() => {
    if (sessionStatus === "pre_assessment" && areAllStepsCompleted()) {
      setTimeout(() => {
        setSessionStatus("authenticated");
        addLog("All pre-assessment steps completed", "success");
      }, 1000);
    }
  }, [preAssessmentSteps, sessionStatus]);

  // Auto-scroll logs
  useEffect(() => {
    if (logsEndRef.current)
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // Move getStatusIcon above the return statement and before any usage in render
  const getStatusIcon = (status, isProcessing = false) => {
    if (isProcessing) {
      return (
        <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      );
    }
    switch (status) {
      case "completed":
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case "failed":
        return <XCircle className="w-5 h-5 text-red-500" />;
      case "pending":
        return (
          <div className="w-5 h-5 border-2 border-gray-300 rounded-full" />
        );
      default:
        return null;
    }
  };

  // Auto-complete liveness check without actual detection
  const requestLivenessChallenge = () => {
    // Directly set the step as completed
    setProcessingSteps((prev) => ({ ...prev, liveness_check: false }));
    setPreAssessmentSteps((prev) => ({
      ...prev,
      liveness_check: {
        ...prev.liveness_check,
        status: "completed",
        message: "Liveness check automatically passed",
      },
    }));
    notify("Liveness check marked as completed", "success");
  };

  // Retry logic for failed pre-assessment steps
  function retryAssessmentStep(step) {
    setPreAssessmentSteps((prev) => ({
      ...prev,
      [step]: {
        ...prev[step],
        status: "pending",
        message: "",
        retryCount: prev[step].retryCount + 1,
      },
    }));
    setProcessingSteps((prev) => ({ ...prev, [step]: false }));
    // Optionally, you can auto-trigger the step here if desired
  }

  // Returns true if any pre-assessment step failed and can still be retried
  function hasRetryableFailures() {
    return Object.values(preAssessmentSteps).some(
      (step) => step.status === "failed" && step.retryCount < MAX_RETRY_ATTEMPTS
    );
  }

  // Returns true if all pre-assessment steps are completed
  function areAllStepsCompleted() {
    return Object.values(preAssessmentSteps).every(
      (step) => step.status === "completed"
    );
  }

  // --- Real-time Metrics Dashboard UI ---
  const renderMetric = (label, metric) => {
    if (!metric) return <span style={{ color: "#aaa" }}>No data</span>;
    if (metric.violation) {
      return (
        <span style={{ color: "red" }}>
          {metric.message || "Violation detected"}
        </span>
      );
    }
    return <span style={{ color: "green" }}>{metric.message || "OK"}</span>;
  };

  // --- Session Report UI ---
  const renderSessionReport = () => {
    if (!sessionReport) return null;
    return (
      <div className="bg-white rounded shadow p-4 mt-6">
        <h2 className="text-lg font-bold mb-2">Session Analysis Report</h2>
        <pre className="text-xs bg-gray-100 rounded p-2 overflow-x-auto">
          {JSON.stringify(sessionReport, null, 2)}
        </pre>
      </div>
    );
  };

  // --- Main Render ---
  return (
    <div className="proctoring-interface">
      <Toaster position="top-right" />
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
      <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
        <h1 className="text-3xl font-bold text-gray-800 mb-6 flex items-center gap-3">
          <Shield className="w-8 h-8 text-blue-600" />
          AI Proctoring System Test Interface
        </h1>
        {/* Session Setup */}
        {!sessionId && (
          <div className="bg-blue-50 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">Session Setup</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Candidate ID
                </label>
                <input
                  type="text"
                  value={candidateId}
                  onChange={(e) => setCandidateId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">
                  Exam ID
                </label>
                <input
                  type="text"
                  value={examId}
                  onChange={(e) => setExamId(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <button
              onClick={createSession}
              className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 transition-colors"
            >
              Create Proctoring Session
            </button>
          </div>
        )}
        {/* Connection Status */}
        {sessionId && (
          <div className="bg-gray-100 rounded-lg p-4 mb-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold">Session Status</h3>
                <p className="text-sm text-gray-600">Session ID: {sessionId}</p>
                <p className="text-sm text-gray-600">Status: {sessionStatus}</p>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className={`w-3 h-3 rounded-full ${
                    isConnected ? "bg-green-500" : "bg-red-500"
                  }`}
                ></div>
                <span className="text-sm">
                  {isConnected ? "Connected" : "Disconnected"}
                </span>
              </div>
            </div>
          </div>
        )}
        {/* Video Feed */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
          <div className="bg-black rounded-lg overflow-hidden">
            <video
              ref={videoRef}
              autoPlay
              muted
              className="w-full h-64 object-cover"
            />
            <canvas ref={canvasRef} style={{ display: "none" }} />
          </div>

          {/* Media Controls */}
          <div className="space-y-4">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Camera
                  className={`w-5 h-5 ${
                    isVideoEnabled ? "text-green-500" : "text-red-500"
                  }`}
                />
                <span className="text-sm">
                  Camera: {isVideoEnabled ? "On" : "Off"}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Mic
                  className={`w-5 h-5 ${
                    isAudioEnabled ? "text-green-500" : "text-red-500"
                  }`}
                />
                <span className="text-sm">
                  Microphone: {isAudioEnabled ? "On" : "Off"}
                </span>
              </div>
            </div>

            {/* Behavior Metrics */}
            <div className="bg-gray-50 rounded-lg p-4">
              <h3 className="font-semibold mb-3">Behavior Metrics</h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span>Attention Score:</span>
                  <span
                    className={`font-medium ${
                      behaviorMetrics.attention_score >= 80
                        ? "text-green-600"
                        : behaviorMetrics.attention_score >= 60
                        ? "text-yellow-600"
                        : "text-red-600"
                    }`}
                  >
                    {behaviorMetrics.attention_score}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Integrity Score:</span>
                  <span
                    className={`font-medium ${
                      behaviorMetrics.integrity_score >= 80
                        ? "text-green-600"
                        : behaviorMetrics.integrity_score >= 60
                        ? "text-yellow-600"
                        : "text-red-600"
                    }`}
                  >
                    {behaviorMetrics.integrity_score}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Gaze Away Time:</span>
                  <span>{behaviorMetrics.total_gaze_away_time}s</span>
                </div>
                <div className="flex justify-between">
                  <span>Violations:</span>
                  <span className="text-red-600">{violations.length}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
        {/* Pre-Assessment Steps */}
        {sessionStatus === "created" && (
          <div className="bg-yellow-50 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">Pre-Assessment Setup</h2>
            <button
              onClick={startPreAssessment}
              className="bg-yellow-600 text-white px-6 py-2 rounded-md hover:bg-yellow-700 transition-colors mb-4"
            >
              Start Pre-Assessment
            </button>
          </div>
        )}
        {sessionStatus === "pre_assessment" && (
          <div className="bg-blue-50 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">Pre-Assessment Steps</h2>

            {/* Progress Summary */}
            <div className="mb-6 p-4 bg-white rounded-lg border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Overall Progress</span>
                <span className="text-sm text-gray-600">
                  {
                    Object.values(preAssessmentSteps).filter(
                      (step) => step.status === "completed"
                    ).length
                  }{" "}
                  / {Object.keys(preAssessmentSteps).length} completed
                </span>
              </div>
              <div className="w-full bg-gray-200 rounded-full h-2">
                <div
                  className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                  style={{
                    width: `${
                      (Object.values(preAssessmentSteps).filter(
                        (step) => step.status === "completed"
                      ).length /
                        Object.keys(preAssessmentSteps).length) *
                      100
                    }%`,
                  }}
                ></div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {Object.entries(preAssessmentSteps).map(([step, data]) => (
                <div key={step} className="bg-white rounded-lg p-4 border">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="font-medium capitalize">
                      {step.replace("_", " ")}
                    </h3>
                    {getStatusIcon(data.status, processingSteps[step])}
                  </div>

                  <p className="text-sm text-gray-600 mb-3">
                    {data.message || "Ready to begin"}
                  </p>

                  {data.retryCount > 0 && (
                    <p className="text-xs text-orange-600 mb-3">
                      Attempt {data.retryCount + 1} of {MAX_RETRY_ATTEMPTS + 1}
                    </p>
                  )}

                  <div className="flex gap-2">
                    {/* Initial attempt or retry button */}
                    {step === "liveness_check" &&
                      (data.status === "pending" || data.status === "failed") &&
                      (livenessChallengeActive ? (
                        <div className="flex flex-col gap-2 w-full">
                          <div className="p-3 bg-blue-100 border border-blue-300 rounded text-blue-900 text-sm mb-2">
                            <strong>Liveness Challenge:</strong>{" "}
                            {livenessChallenge?.instructions ||
                              "Follow the instructions shown."}
                            <div className="mt-1 text-xs text-blue-700">
                              Time remaining: {livenessCountdown}s
                            </div>
                          </div>
                          {livenessChallengeLoading && (
                            <div className="flex items-center gap-2 text-blue-700 text-xs">
                              <RotateCcw className="w-4 h-4 animate-spin" />
                              Analyzing... Please perform the challenge.
                            </div>
                          )}
                          {livenessChallengeResult && (
                            <div
                              className={`mt-2 p-2 rounded text-xs ${
                                livenessChallengeResult.status === "passed"
                                  ? "bg-green-100 text-green-800"
                                  : "bg-red-100 text-red-800"
                              }`}
                            >
                              {livenessChallengeResult.message}
                            </div>
                          )}
                        </div>
                      ) : (
                        <button
                          onClick={() => requestLivenessChallenge()}
                          disabled={processingSteps[step]}
                          className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          <Eye className="w-4 h-4" />
                          Start Liveness Challenge
                        </button>
                      ))}

                    {step === "face_enrollment" &&
                      (data.status === "pending" ||
                        data.status === "failed") && (
                        <button
                          onClick={
                            data.status === "failed"
                              ? () => retryAssessmentStep(step)
                              : performFaceEnrollment
                          }
                          disabled={
                            processingSteps[step] ||
                            (data.status === "failed" &&
                              data.retryCount >= MAX_RETRY_ATTEMPTS)
                          }
                          className="bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          {data.status === "failed" ? (
                            <>
                              <RotateCcw className="w-4 h-4" />
                              Retry Face Enrollment
                            </>
                          ) : (
                            <>
                              <User className="w-4 h-4" />
                              Enroll Face
                            </>
                          )}
                        </button>
                      )}

                    {step === "voice_enrollment" &&
                      (data.status === "pending" ||
                        data.status === "failed") && (
                        <button
                          onClick={
                            data.status === "failed"
                              ? () => retryAssessmentStep(step)
                              : startVoiceRecording
                          }
                          disabled={
                            processingSteps[step] ||
                            isRecordingVoice ||
                            (data.status === "failed" &&
                              data.retryCount >= MAX_RETRY_ATTEMPTS)
                          }
                          className="bg-purple-600 text-white px-4 py-2 rounded text-sm hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          {data.status === "failed" ? (
                            <>
                              <RotateCcw className="w-4 h-4" />
                              Retry Voice Enrollment
                            </>
                          ) : (
                            <>
                              <Volume2 className="w-4 h-4" />
                              {isRecordingVoice
                                ? "Recording..."
                                : "Record Voice"}
                            </>
                          )}
                        </button>
                      )}

                    {step === "environment_check" &&
                      (data.status === "pending" ||
                        data.status === "failed") && (
                        <button
                          onClick={
                            data.status === "failed"
                              ? () => retryAssessmentStep(step)
                              : performEnvironmentCheck
                          }
                          disabled={
                            processingSteps[step] ||
                            (data.status === "failed" &&
                              data.retryCount >= MAX_RETRY_ATTEMPTS)
                          }
                          className="bg-orange-600 text-white px-4 py-2 rounded text-sm hover:bg-orange-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                        >
                          {data.status === "failed" ? (
                            <>
                              <RotateCcw className="w-4 h-4" />
                              Retry Environment Check
                            </>
                          ) : (
                            <>
                              <Shield className="w-4 h-4" />
                              Check Environment
                            </>
                          )}
                        </button>
                      )}
                  </div>

                  {/* Max attempts reached message */}
                  {data.status === "failed" &&
                    data.retryCount >= MAX_RETRY_ATTEMPTS && (
                      <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
                        Maximum retry attempts reached. Please contact support
                        for assistance.
                      </div>
                    )}
                </div>
              ))}
            </div>

            {/* Retry All Failed Steps Button */}
            {hasRetryableFailures() && (
              <div className="mt-6 p-4 bg-orange-50 border border-orange-200 rounded-lg">
                <h3 className="font-medium text-orange-800 mb-2">
                  Some steps failed
                </h3>
                <p className="text-sm text-orange-700 mb-3">
                  You can retry failed steps individually using the retry
                  buttons above, or contact support if you continue to
                  experience issues.
                </p>
              </div>
            )}
          </div>
        )}
        {/* Assessment Controls */}
        {sessionStatus === "authenticated" && (
          <div className="bg-green-50 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">
              Ready to Start Assessment
            </h2>
            <p className="text-gray-600 mb-4">
              All pre-assessment checks have passed. You can now start the
              proctored assessment.
            </p>
            <button
              onClick={startAssessment}
              className="bg-green-600 text-white px-6 py-2 rounded-md hover:bg-green-700 transition-colors"
            >
              <Play className="w-5 h-5 inline mr-2" />
              Start Assessment
            </button>
          </div>
        )}
        {sessionStatus === "active" && (
          <div className="bg-red-50 rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">Assessment Active</h2>
            <p className="text-gray-600 mb-4">
              The assessment is now running with active proctoring monitoring.
            </p>
            <button
              onClick={endAssessment}
              className="bg-red-600 text-white px-6 py-2 rounded-md hover:bg-red-700 transition-colors"
            >
              <Square className="w-5 h-5 inline mr-2" />
              End Assessment
            </button>
          </div>
        )}

        {sessionStatus === "completed" && sessionReport && (
          <div className="mt-4">
            <button
              onClick={() => setShowReport(!showReport)}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
            >
              {showReport ? "Hide Assessment Report" : "View Assessment Report"}
            </button>

            {showReport && (
              <div className="mt-4">
                <SessionReportDisplay report={sessionReport} />
              </div>
            )}
          </div>
        )}

        <div
          style={{
            margin: "20px 0",
            padding: "16px",
            border: "1px solid #eee",
            borderRadius: 8,
            background: "#fafbfc",
          }}
        >
          <h3 style={{ marginBottom: 8 }}>Real-Time Proctoring Metrics</h3>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <tbody>
              <tr>
                <td style={{ fontWeight: "bold" }}>Gaze</td>
                <td>{renderMetric("Gaze", realTimeMetrics.gaze)}</td>
              </tr>
              <tr>
                <td style={{ fontWeight: "bold" }}>Posture</td>
                <td>{renderMetric("Posture", realTimeMetrics.posture)}</td>
              </tr>
              <tr>
                <td style={{ fontWeight: "bold" }}>Voice Verification</td>
                <td>
                  {renderMetric(
                    "Voice Verification",
                    realTimeMetrics.voice_verification
                  )}
                </td>
              </tr>
              <tr>
                <td style={{ fontWeight: "bold" }}>Facial Verification</td>
                <td>
                  {renderMetric(
                    "Facial Verification",
                    realTimeMetrics.face_verification
                  )}
                </td>
              </tr>
              <tr>
                <td style={{ fontWeight: "bold" }}>Object Detection</td>
                <td>
                  {renderMetric(
                    "Object Detection",
                    realTimeMetrics.object_detection
                  )}
                </td>
              </tr>
              <tr>
                <td style={{ fontWeight: "bold" }}>Environmental Noise</td>
                <td>
                  {renderMetric(
                    "Environmental Noise",
                    realTimeMetrics.environment_noise
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ProctoringTestInterface;
