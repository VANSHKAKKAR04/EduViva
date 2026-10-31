import React from "react";

const SessionSetup = ({ candidateId, setCandidateId, examId, setExamId, createSession }) => (
  <div className="bg-blue-50 rounded-lg p-6 mb-6">
    <h2 className="text-xl font-semibold mb-4">Session Setup</h2>
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
      <div>
        <label className="block text-sm font-medium mb-2">Candidate ID</label>
        <input
          type="text"
          value={candidateId}
          onChange={(e) => setCandidateId(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-2">Exam ID</label>
        <input
          type="text"
          value={examId}
          onChange={(e) => setExamId(e.target.value)}
          className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
    </div>
    <button
      onClick={createSession}
      className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 transition-colors"
    >
      Create Proctoring Session
    </button>
  </div>
);

export default SessionSetup;
