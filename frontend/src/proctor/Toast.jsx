import React from "react";

const Toast = ({ message, type = "info", onClose }) => {
  let bgColor = "bg-blue-100 text-blue-800 border-blue-300";
  if (type === "success") bgColor = "bg-green-100 text-green-800 border-green-300";
  if (type === "error") bgColor = "bg-red-100 text-red-800 border-red-300";
  if (type === "warning") bgColor = "bg-yellow-100 text-yellow-800 border-yellow-300";

  return (
    <div
      className={`fixed top-6 right-6 z-50 px-4 py-3 rounded shadow border ${bgColor}`}
      style={{ minWidth: 240 }}
      role="alert"
      onClick={onClose}
    >
      <span className="block font-semibold mb-1">{type.charAt(0).toUpperCase() + type.slice(1)}</span>
      <span className="block">{message}</span>
      <button
        className="absolute top-1 right-2 text-lg font-bold text-gray-500 hover:text-gray-800"
        onClick={onClose}
        aria-label="Close"
        style={{ background: "none", border: "none", cursor: "pointer" }}
      >
        ×
      </button>
    </div>
  );
};

export default Toast;
