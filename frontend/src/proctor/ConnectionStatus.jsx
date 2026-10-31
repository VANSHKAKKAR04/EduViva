import React from "react";

const ConnectionStatus = ({ sessionId, sessionStatus, isConnected }) => (
  <div className="bg-gray-100 rounded-lg p-4 mb-6">
    <div className="flex items-center justify-between">
      <div>
        <h3 className="font-semibold">Session Status</h3>
        <p className="text-sm text-gray-600">Session ID: {sessionId}</p>
        <p className="text-sm text-gray-600">Status: {sessionStatus}</p>
      </div>
      <div className="flex items-center gap-2">
        <div
          className={`w-3 h-3 rounded-full ${isConnected ? "bg-green-500" : "bg-red-500"}`}
        ></div>
        <span className="text-sm">
          {isConnected ? "Connected" : "Disconnected"}
        </span>
      </div>
    </div>
  </div>
);

export default ConnectionStatus;
