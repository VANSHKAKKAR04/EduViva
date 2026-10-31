// Audio processing utilities for PCM/WAV conversion

export function floatTo16BitPCM(float32Array) {
  const int16Array = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return int16Array;
}

export function writeString(view, offset, string) {
  for (let i = 0; i < string.length; i++) {
    view.setUint8(offset + i, string.charCodeAt(i));
  }
}

export function encodeWav(int16Array, sampleRate = 16000) {
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

// In audioUtils.js
export function createAudioInterval({
  audioStream,
  mediaStream,
  audioBufferRef,
  websocket,
  websocketReady,
  addLog,
  floatTo16BitPCM,
  encodeWav,
}) {
  return setInterval(() => {
    if (!audioStream && !mediaStream) {
      addLog("[Audio] Audio chunk NOT sent (no audio stream)", "warning");
      return;
    }
    audioBufferRef.current = [];
    try {
      const streamToUse = audioStream || mediaStream;
      const audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: 16000,
      });
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
          const length = audioBufferRef.current.reduce((acc, arr) => acc + arr.length, 0);
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
      addLog(`[Audio] Error during audio streaming: ${err.message}", "error`);
    }
  }, 2000);
}
