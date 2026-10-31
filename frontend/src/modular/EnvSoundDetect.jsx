import React, { useEffect, useRef, useState } from "react";

const EnvSoundDetect = () => {
  const [recording, setRecording] = useState(false);
  const [prediction, setPrediction] = useState(null);
  const socketRef = useRef(null);
  const audioContextRef = useRef(null);
  const processorRef = useRef(null);
  const sourceRef = useRef(null);

  useEffect(() => {
    const socket = new WebSocket("ws://localhost:8004/ws/audio");
    socket.onopen = () => console.log("WebSocket connected.");
    socket.onclose = () => console.log("WebSocket disconnected.");
    socket.onerror = (err) => console.error("WebSocket error:", err);
    socket.onmessage = (msg) => {
      const data = JSON.parse(msg.data);
      setPrediction(data);
    };
    socketRef.current = socket;

    return () => socket.close();
  }, []);

  const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

    audioContextRef.current = new (window.AudioContext ||
      window.webkitAudioContext)({ sampleRate: 16000 });

    sourceRef.current = audioContextRef.current.createMediaStreamSource(stream);

    const processor = audioContextRef.current.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      const float32Array = new Float32Array(input.length);
      float32Array.set(input);

      if (socketRef.current?.readyState === WebSocket.OPEN) {
        socketRef.current.send(float32Array.buffer);
      }
    };

    processorRef.current = processor;

    sourceRef.current.connect(processor);
    processor.connect(audioContextRef.current.destination);

    setRecording(true);
  };

  const stopRecording = () => {
    processorRef.current?.disconnect();
    sourceRef.current?.disconnect();
    audioContextRef.current?.close();

    setRecording(false);
  };

  return (
    <div className="p-4 max-w-md mx-auto text-center border rounded-lg shadow-md">
      <h1 className="text-xl font-bold mb-2">Real-Time Audio Detector</h1>

      {recording ? (
        <button
          onClick={stopRecording}
          className="bg-red-500 text-white px-4 py-2 rounded"
        >
          Stop Recording
        </button>
      ) : (
        <button
          onClick={startRecording}
          className="bg-green-500 text-white px-4 py-2 rounded"
        >
          Start Recording
        </button>
      )}

      {prediction && (
        <div className="mt-4 p-2 border rounded">
          <p>
            <strong>Label:</strong> {prediction.label}
          </p>
          <p>
            <strong>Confidence:</strong>{" "}
            {(prediction.confidence * 100).toFixed(2)}%
          </p>
          <p>
            <strong>Alert:</strong>{" "}
            {prediction.alert ? (
              <span className="text-red-600 font-bold">YES</span>
            ) : (
              <span className="text-green-600">No</span>
            )}
          </p>
        </div>
      )}
    </div>
  );
};

export default EnvSoundDetect;
