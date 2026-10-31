// Voice and audio streaming utilities for Proctor.jsx
// These functions require you to pass all necessary refs, state, and callbacks as arguments.

import { floatTo16BitPCM, encodeWav } from "./audioUtils";

export const startVoiceRecording = async ({
  audioStream,
  mediaStream,
  setIsRecordingVoice,
  setProcessingSteps,
  audioBufferRef,
  audioContextRef,
  processorRef,
  addLog,
  notify,
  stopVoiceRecording,
}) => {
  if (!audioStream && !mediaStream) {
    notify("No audio stream available for voice recording", "error");
    return;
  }
  setIsRecordingVoice(true);
  setProcessingSteps((prev) => ({ ...prev, voice_enrollment: true }));
  audioBufferRef.current = [];
  try {
    const streamToUse = audioStream || mediaStream;
    const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
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

export const stopVoiceRecording = ({
  setIsRecordingVoice,
  processorRef,
  audioContextRef,
  audioBufferRef,
  notify,
  setProcessingSteps,
  websocket,
  websocketReady,
  addLog,
  purpose = "voice_enrollment",
}) => {
  setIsRecordingVoice(false);
  if (processorRef.current) processorRef.current.disconnect();
  if (audioContextRef.current) audioContextRef.current.close();
  // Concatenate buffers
  let float32 = null;
  if (audioBufferRef.current.length > 0) {
    const length = audioBufferRef.current.reduce((acc, arr) => acc + arr.length, 0);
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

export const startRealTimeMonitoring = ({
  streamIntervalRef,
  videoRef,
  canvasRef,
  websocket,
  websocketReady,
  addLog,
  captureFrame,
  audioStream,
  mediaStream,
  floatTo16BitPCM,
  encodeWav,
}) => {
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
        `[Frame] Video frame NOT sent (${reason.length ? reason.join(", ") : "no frame"})`,
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
    let audioBuffer = [];
    try {
      const streamToUse = audioStream || mediaStream;
      const audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const source = audioContext.createMediaStreamSource(streamToUse);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processor.onaudioprocess = (e) => {
        const input = e.inputBuffer.getChannelData(0);
        audioBuffer.push(new Float32Array(input));
      };
      source.connect(processor);
      processor.connect(audioContext.destination);
      setTimeout(() => {
        processor.disconnect();
        audioContext.close();
        let float32 = null;
        if (audioBuffer.length > 0) {
          const length = audioBuffer.reduce((acc, arr) => acc + arr.length, 0);
          float32 = new Float32Array(length);
          let offset = 0;
          for (const arr of audioBuffer) {
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
            addLog("[Audio] Audio chunk sent to backend for processing", "info");
            console.log("[AUDIO][STREAM] Audio chunk sent to backend for processing");
          } else {
            addLog("[Audio] Audio chunk NOT sent (WebSocket not ready)", "warning");
            console.log("[AUDIO][STREAM] Audio chunk NOT sent (WebSocket not ready)");
          }
        };
        reader.onerror = () => {
          addLog("[Audio] Failed to read audio blob for streaming", "error");
          console.log("[AUDIO][STREAM] Failed to read audio blob for streaming");
        };
        reader.readAsDataURL(wavBlob);
      }, 1000); // Record 1s chunk
    } catch (err) {
      addLog(`[Audio] Error during audio streaming: ${err.message}`, "error");
    }
  }, 2000);
  streamIntervalRef.current = { videoInterval, audioInterval };
};