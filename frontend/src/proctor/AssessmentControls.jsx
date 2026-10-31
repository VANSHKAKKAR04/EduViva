import React from "react";
import { Play, Square } from "lucide-react";

const AssessmentControls = ({ sessionStatus, startAssessment, endAssessment }) => {
  if (sessionStatus === "authenticated") {
    return (
      <div className="bg-green-50 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Ready to Start Assessment</h2>
        <p className="text-gray-600 mb-4">
          All pre-assessment checks have passed. You can now start the proctored assessment.
        </p>
        <button
          onClick={startAssessment}
          className="bg-green-600 text-white px-6 py-2 rounded-md hover:bg-green-700 transition-colors"
        >
          <Play className="w-5 h-5 inline mr-2" />
          Start Assessment
        </button>
      </div>
    );
  }
  if (sessionStatus === "active") {
    return (
      <div className="bg-red-50 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Assessment Active</h2>
        <p className="text-gray-600 mb-4">
          The assessment is now running with active proctoring monitoring.
        </p>
        <button
          onClick={endAssessment}
          className="bg-red-600 text-white px-6 py-2 rounded-md hover:bg-red-700 transition-colors"
        >
          <Square className="w-5 h-5 inline mr-2" />
          End Assessment
        </button>
      </div>
    );
  }
  return null;
};

export default AssessmentControls;
