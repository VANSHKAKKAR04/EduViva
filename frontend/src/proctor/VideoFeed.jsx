import React from "react";
import { Camera, Mic } from "lucide-react";

const VideoFeed = React.forwardRef(({ isVideoEnabled, isAudioEnabled, videoRef, canvasRef }, ref) => (
  <div className="bg-black rounded-lg overflow-hidden">
    <video
      ref={videoRef}
      autoPlay
      muted
      className="w-full h-64 object-cover"
    />
    <canvas ref={canvasRef} style={{ display: "none" }} />
    <div className="flex items-center gap-4 p-2 bg-gray-900 bg-opacity-60 absolute top-0 left-0">
      <div className="flex items-center gap-2">
        <Camera className={`w-5 h-5 ${isVideoEnabled ? "text-green-500" : "text-red-500"}`} />
        <span className="text-sm text-white">
          Camera: {isVideoEnabled ? "On" : "Off"}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <Mic className={`w-5 h-5 ${isAudioEnabled ? "text-green-500" : "text-red-500"}`} />
        <span className="text-sm text-white">
          Microphone: {isAudioEnabled ? "On" : "Off"}
        </span>
      </div>
    </div>
  </div>
));

export default VideoFeed;
