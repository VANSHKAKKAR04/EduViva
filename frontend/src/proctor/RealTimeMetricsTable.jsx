import React from "react";

const RealTimeMetricsTable = ({ realTimeMetrics, renderMetric }) => (
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
          <td>{renderMetric("Voice Verification", realTimeMetrics.voice_verification)}</td>
        </tr>
        <tr>
          <td style={{ fontWeight: "bold" }}>Facial Verification</td>
          <td>{renderMetric("Facial Verification", realTimeMetrics.face_verification)}</td>
        </tr>
        <tr>
          <td style={{ fontWeight: "bold" }}>Object Detection</td>
          <td>{renderMetric("Object Detection", realTimeMetrics.object_detection)}</td>
        </tr>
        <tr>
          <td style={{ fontWeight: "bold" }}>Environmental Noise</td>
          <td>{renderMetric("Environmental Noise", realTimeMetrics.environment_noise)}</td>
        </tr>
      </tbody>
    </table>
  </div>
);

export default RealTimeMetricsTable;
