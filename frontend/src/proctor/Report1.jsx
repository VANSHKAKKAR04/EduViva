import React from "react";

const SessionReportDisplay = ({ report }) => {
  if (!report) {
    return (
      <div className="p-4 text-gray-500 italic text-center">
        No report data available. Please fetch the report.
      </div>
    );
  }

  const {
    session_id,
    status,
    monitoring_summary = {},
    violations = [],
    recommendations = [],
  } = report;

  return (
    <div className="bg-white shadow-xl rounded-xl p-6 space-y-6 border border-gray-200">
      <div className="text-2xl font-bold text-gray-800 border-b pb-2">
        Session Report: <span className="text-blue-600">{session_id}</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-gray-700">
        <div>
          <p className="mb-1">
            <strong>Status:</strong>{" "}
            <span
              className={`font-semibold capitalize ${
                status === "complete" ? "text-green-600" : "text-yellow-600"
              }`}
            >
              {status}
            </span>
          </p>
          <p className="mb-1">
            <strong>Assessment:</strong>{" "}
            <span className="text-gray-800">
              {monitoring_summary.overall_assessment || "N/A"}
            </span>
          </p>
        </div>

        <div>
          <p className="mb-1">
            <strong>Attention Score:</strong>{" "}
            <span className="text-gray-800">
              {monitoring_summary.attention_score ?? 0}%
            </span>
          </p>
          <p className="mb-1">
            <strong>Integrity Score:</strong>{" "}
            <span className="text-gray-800">
              {monitoring_summary.integrity_score ?? 0}%
            </span>
          </p>
        </div>

        <div>
          <p className="mb-1">
            <strong>Total Violations:</strong>{" "}
            <span className="text-gray-800">
              {monitoring_summary.total_violations ?? 0}
            </span>
          </p>
          <p className="mb-1">
            <strong>Critical Violations:</strong>{" "}
            <span className="text-gray-800">
              {monitoring_summary.critical_violations ?? 0}
            </span>
          </p>
        </div>
      </div>

      {violations.length > 0 && (
        <div className="pt-4">
          <h3 className="text-lg font-semibold text-red-600 mb-2">
            Violations Detected
          </h3>
          <ul className="list-disc pl-6 text-sm text-red-700 space-y-1">
            {violations.map((violation, idx) => (
              <li key={idx}>
                {violation.type || "Unknown"} – Severity:{" "}
                {violation.severity || "Unknown"}
                {violation.description}
              </li>
            ))}
          </ul>
        </div>
      )}

      {recommendations.length > 0 && (
        <div className="pt-4">
          <h3 className="text-lg font-semibold text-blue-600 mb-2">
            Recommendations
          </h3>
          <ul className="list-disc pl-6 text-sm text-blue-700 space-y-1">
            {recommendations.map((rec, idx) => (
              <li key={idx}>{rec}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default SessionReportDisplay;
