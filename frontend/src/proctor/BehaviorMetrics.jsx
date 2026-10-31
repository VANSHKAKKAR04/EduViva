import React from "react";

const BehaviorMetrics = ({ behaviorMetrics, violations }) => (
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
);

export default BehaviorMetrics;
