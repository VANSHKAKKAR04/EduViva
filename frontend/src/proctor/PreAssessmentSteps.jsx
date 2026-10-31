import React from "react";
import { Eye, User, Volume2, Shield, RotateCcw } from "lucide-react";

const PreAssessmentSteps = ({
  sessionStatus,
  preAssessmentSteps,
  processingSteps,
  livenessChallengeActive,
  livenessChallenge,
  livenessCountdown,
  livenessChallengeLoading,
  livenessChallengeResult,
  MAX_RETRY_ATTEMPTS,
  startPreAssessment,
  requestLivenessChallenge,
  performFaceEnrollment,
  startVoiceRecording,
  performEnvironmentCheck,
  retryAssessmentStep,
  hasRetryableFailures,
}) => {
  if (sessionStatus === "created") {
    return (
      <div className="bg-yellow-50 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Pre-Assessment Setup</h2>
        <button
          onClick={startPreAssessment}
          className="bg-yellow-600 text-white px-6 py-2 rounded-md hover:bg-yellow-700 transition-colors mb-4"
        >
          Start Pre-Assessment
        </button>
      </div>
    );
  }
  if (sessionStatus === "pre_assessment") {
    return (
      <div className="bg-blue-50 rounded-lg p-6 mb-6">
        <h2 className="text-xl font-semibold mb-4">Pre-Assessment Steps</h2>
        {/* Progress Summary */}
        <div className="mb-6 p-4 bg-white rounded-lg border">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Overall Progress</span>
            <span className="text-sm text-gray-600">
              {Object.values(preAssessmentSteps).filter((step) => step.status === "completed").length} / {Object.keys(preAssessmentSteps).length} completed
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{
                width: `${
                  (Object.values(preAssessmentSteps).filter((step) => step.status === "completed").length /
                    Object.keys(preAssessmentSteps).length) * 100
                }%`,
              }}
            ></div>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {Object.entries(preAssessmentSteps).map(([step, data]) => (
            <div key={step} className="bg-white rounded-lg p-4 border">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-medium capitalize">{step.replace("_", " ")}</h3>
                {/* Status Icon */}
                {processingSteps[step] ? (
                  <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                ) : data.status === "completed" ? (
                  <span className="text-green-500">&#10003;</span>
                ) : data.status === "failed" ? (
                  <span className="text-red-500">&#10007;</span>
                ) : (
                  <div className="w-5 h-5 border-2 border-gray-300 rounded-full" />
                )}
              </div>
              <p className="text-sm text-gray-600 mb-3">{data.message || "Ready to begin"}</p>
              {data.retryCount > 0 && (
                <p className="text-xs text-orange-600 mb-3">
                  Attempt {data.retryCount + 1} of {MAX_RETRY_ATTEMPTS + 1}
                </p>
              )}
              <div className="flex gap-2">
                {/* Liveness Check */}
                {step === "liveness_check" &&
                  (data.status === "pending" || data.status === "failed") &&
                  (livenessChallengeActive ? (
                    <div className="flex flex-col gap-2 w-full">
                      <div className="p-3 bg-blue-100 border border-blue-300 rounded text-blue-900 text-sm mb-2">
                        <strong>Liveness Challenge:</strong> {livenessChallenge?.instructions || "Follow the instructions shown."}
                        <div className="mt-1 text-xs text-blue-700">Time remaining: {livenessCountdown}s</div>
                      </div>
                      {livenessChallengeLoading && (
                        <div className="flex items-center gap-2 text-blue-700 text-xs">
                          <RotateCcw className="w-4 h-4 animate-spin" />
                          Analyzing... Please perform the challenge.
                        </div>
                      )}
                      {livenessChallengeResult && (
                        <div className={`mt-2 p-2 rounded text-xs ${livenessChallengeResult.status === "passed" ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}`}>
                          {livenessChallengeResult.message}
                        </div>
                      )}
                    </div>
                  ) : (
                    <button
                      onClick={() => requestLivenessChallenge()}
                      disabled={processingSteps[step]}
                      className="bg-blue-600 text-white px-4 py-2 rounded text-sm hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      <Eye className="w-4 h-4" />
                      Start Liveness Challenge
                    </button>
                  ))}
                {/* Face Enrollment */}
                {step === "face_enrollment" &&
                  (data.status === "pending" || data.status === "failed") && (
                    <button
                      onClick={data.status === "failed" ? () => retryAssessmentStep(step) : performFaceEnrollment}
                      disabled={processingSteps[step] || (data.status === "failed" && data.retryCount >= MAX_RETRY_ATTEMPTS)}
                      className="bg-green-600 text-white px-4 py-2 rounded text-sm hover:bg-green-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {data.status === "failed" ? (
                        <>
                          <RotateCcw className="w-4 h-4" /> Retry Face Enrollment
                        </>
                      ) : (
                        <>
                          <User className="w-4 h-4" /> Enroll Face
                        </>
                      )}
                    </button>
                  )}
                {/* Voice Enrollment */}
                {step === "voice_enrollment" &&
                  (data.status === "pending" || data.status === "failed") && (
                    <button
                      onClick={data.status === "failed" ? () => retryAssessmentStep(step) : startVoiceRecording}
                      disabled={processingSteps[step] || (data.status === "failed" && data.retryCount >= MAX_RETRY_ATTEMPTS)}
                      className="bg-purple-600 text-white px-4 py-2 rounded text-sm hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {data.status === "failed" ? (
                        <>
                          <RotateCcw className="w-4 h-4" /> Retry Voice Enrollment
                        </>
                      ) : (
                        <>
                          <Volume2 className="w-4 h-4" /> Record Voice
                        </>
                      )}
                    </button>
                  )}
                {/* Environment Check */}
                {step === "environment_check" &&
                  (data.status === "pending" || data.status === "failed") && (
                    <button
                      onClick={data.status === "failed" ? () => retryAssessmentStep(step) : performEnvironmentCheck}
                      disabled={processingSteps[step] || (data.status === "failed" && data.retryCount >= MAX_RETRY_ATTEMPTS)}
                      className="bg-orange-600 text-white px-4 py-2 rounded text-sm hover:bg-orange-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                    >
                      {data.status === "failed" ? (
                        <>
                          <RotateCcw className="w-4 h-4" /> Retry Environment Check
                        </>
                      ) : (
                        <>
                          <Shield className="w-4 h-4" /> Check Environment
                        </>
                      )}
                    </button>
                  )}
              </div>
              {/* Max attempts reached message */}
              {data.status === "failed" && data.retryCount >= MAX_RETRY_ATTEMPTS && (
                <div className="mt-3 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
                  Maximum retry attempts reached. Please contact support for assistance.
                </div>
              )}
            </div>
          ))}
        </div>
        {/* Retry All Failed Steps Button */}
        {hasRetryableFailures() && (
          <div className="mt-6 p-4 bg-orange-50 border border-orange-200 rounded-lg">
            <h3 className="font-medium text-orange-800 mb-2">Some steps failed</h3>
            <p className="text-sm text-orange-700 mb-3">
              You can retry failed steps individually using the retry buttons above, or contact support if you continue to experience issues.
            </p>
          </div>
        )}
      </div>
    );
  }
  return null;
};

export default PreAssessmentSteps;
