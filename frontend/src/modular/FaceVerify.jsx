import React, { useRef, useState, useEffect } from "react";

const FaceVerification = () => {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const [referenceCaptured, setReferenceCaptured] = useState(false);
  const [verified, setVerified] = useState(null);
  const [distance, setDistance] = useState(null);
  const [verifying, setVerifying] = useState(false);

  // Start webcam on mount
  useEffect(() => {
    async function startWebcam() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: true,
        });
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
        }
      } catch (err) {
        alert("Error accessing webcam: " + err.message);
      }
    }
    startWebcam();
  }, []);

  // Capture reference image from webcam
  const captureReference = () => {
    if (!videoRef.current || !canvasRef.current) return;
    const context = canvasRef.current.getContext("2d");
    canvasRef.current.width = videoRef.current.videoWidth;
    canvasRef.current.height = videoRef.current.videoHeight;
    context.drawImage(videoRef.current, 0, 0);

    canvasRef.current.toBlob(async (blob) => {
      // Upload reference image blob to backend
      const formData = new FormData();
      formData.append("file", blob, "reference.jpg");

      try {
        const res = await fetch("http://localhost:8000/upload-reference/", {
          method: "POST",
          body: formData,
        });
        if (res.ok) {
          setReferenceCaptured(true);
          alert("Reference face captured successfully!");
          startVerificationLoop();
        } else {
          alert("Failed to upload reference image");
        }
      } catch (error) {
        alert("Error uploading reference: " + error.message);
      }
    }, "image/jpeg");
  };

  // Verification loop: send frames every second for a fixed period (e.g. 10 sec)
  const startVerificationLoop = () => {
    if (verifying) return; // Prevent multiple loops
    setVerifying(true);
    let count = 0;
    const maxChecks = 10; // 10 seconds total (1 per second)
    const intervalId = setInterval(async () => {
      if (!videoRef.current || !canvasRef.current) return;

      const context = canvasRef.current.getContext("2d");
      canvasRef.current.width = videoRef.current.videoWidth;
      canvasRef.current.height = videoRef.current.videoHeight;
      context.drawImage(videoRef.current, 0, 0);

      canvasRef.current.toBlob(async (blob) => {
        const formData = new FormData();
        formData.append("file", blob, "frame.jpg");

        try {
          const res = await fetch("http://localhost:8000/verify-frame/", {
            method: "POST",
            body: formData,
          });
          if (res.ok) {
            const data = await res.json();
            setVerified(data.verified);
            setDistance(data.distance);
          } else {
            console.error("Verification failed");
          }
        } catch (error) {
          console.error("Error verifying frame:", error);
        }
      }, "image/jpeg");

      count++;
      if (count >= maxChecks) {
        clearInterval(intervalId);
        setVerifying(false);
      }
    }, 1000);
  };

  return (
    <div style={{ textAlign: "center" }}>
      <h2>Face Verification</h2>
      <video
        ref={videoRef}
        autoPlay
        muted
        style={{ width: 320, height: 240, border: "1px solid black" }}
      />
      <br />
      <button onClick={captureReference} disabled={referenceCaptured}>
        {referenceCaptured ? "Reference Captured" : "Capture Reference Face"}
      </button>
      <br />
      {verifying && <p>Verifying... Please look at the camera</p>}
      {verified !== null && (
        <p>
          Verified: <strong>{verified ? "✅ Yes" : "❌ No"}</strong> | Distance:{" "}
          {distance.toFixed(4)}
        </p>
      )}
      <canvas ref={canvasRef} style={{ display: "none" }} />
    </div>
  );
};

export default FaceVerification;
