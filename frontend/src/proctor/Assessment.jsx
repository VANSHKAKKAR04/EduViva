import React, { useState, useRef, useEffect } from 'react';
import { Camera, Mic, Play, Pause, AlertTriangle, CheckCircle, XCircle, BarChart3, Eye, Volume2, Clock, User, FileText } from 'lucide-react';

const ProctoredAssessment = () => {
  const [currentPhase, setCurrentPhase] = useState('setup'); // setup, liveness, assessment, results
  const [isRecording, setIsRecording] = useState(false);
  const [livenessChecks, setLivenessChecks] = useState({
    faceDetection: false,
    voiceDetection: false,
    livenessVerified: false
  });
  const [assessmentData, setAssessmentData] = useState({
    currentQuestion: 1,
    totalQuestions: 10,
    timeRemaining: 1800, // 30 minutes
    answers: {}
  });
  const [behavioralMetrics, setBehavioralMetrics] = useState(null);
  const [alerts, setAlerts] = useState([]);
  
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const videoSocketRef = useRef(null);
  const audioSocketRef = useRef(null);
  const streamRef = useRef(null);

  // Initialize camera and microphone
  const initializeMedia = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'user' },
        audio: { echoCancellation: true, noiseSuppression: true }
      });
      
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }
      streamRef.current = stream;
      return true;
    } catch (error) {
      console.error('Error accessing media devices:', error);
      setAlerts(prev => [...prev, { type: 'error', message: 'Camera and microphone access required' }]);
      return false;
    }
  };

  // Simulate liveness detection
  const performLivenessCheck = () => {
    setLivenessChecks({ faceDetection: false, voiceDetection: false, livenessVerified: false });
    
    // Simulate face detection
    setTimeout(() => {
      setLivenessChecks(prev => ({ ...prev, faceDetection: true }));
    }, 2000);
    
    // Simulate voice detection
    setTimeout(() => {
      setLivenessChecks(prev => ({ ...prev, voiceDetection: true }));
    }, 4000);
    
    // Complete liveness verification
    setTimeout(() => {
      setLivenessChecks(prev => ({ ...prev, livenessVerified: true }));
      setTimeout(() => setCurrentPhase('assessment'), 1000);
    }, 6000);
  };

  // Initialize WebSocket connections
  const initializeWebSockets = () => {
    // Video WebSocket
    videoSocketRef.current = new WebSocket('ws://localhost:8080/video');
    videoSocketRef.current.onopen = () => console.log('Video WebSocket connected');
    videoSocketRef.current.onerror = (error) => console.error('Video WebSocket error:', error);
    
    // Audio WebSocket
    audioSocketRef.current = new WebSocket('ws://localhost:8080/audio');
    audioSocketRef.current.onopen = () => console.log('Audio WebSocket connected');
    audioSocketRef.current.onerror = (error) => console.error('Audio WebSocket error:', error);
  };

  // Start recording and streaming
  const startRecording = () => {
    if (!streamRef.current) return;
    
    const videoTrack = streamRef.current.getVideoTracks()[0];
    const audioTrack = streamRef.current.getAudioTracks()[0];
    
    // Create separate streams for video and audio
    const videoStream = new MediaStream([videoTrack]);
    const audioStream = new MediaStream([audioTrack]);
    
    // Video recorder
    const videoRecorder = new MediaRecorder(videoStream, { mimeType: 'video/webm' });
    videoRecorder.ondataavailable = (event) => {
      if (event.data.size > 0 && videoSocketRef.current?.readyState === WebSocket.OPEN) {
        videoSocketRef.current.send(event.data);
      }
    };
    videoRecorder.start(1000); // Send chunks every second
    
    // Audio recorder
    const audioRecorder = new MediaRecorder(audioStream, { mimeType: 'audio/webm' });
    audioRecorder.ondataavailable = (event) => {
      if (event.data.size > 0 && audioSocketRef.current?.readyState === WebSocket.OPEN) {
        audioSocketRef.current.send(event.data);
      }
    };
    audioRecorder.start(1000);
    
    setIsRecording(true);
  };

  // Timer countdown
  useEffect(() => {
    let interval;
    if (currentPhase === 'assessment' && assessmentData.timeRemaining > 0) {
      interval = setInterval(() => {
        setAssessmentData(prev => ({
          ...prev,
          timeRemaining: prev.timeRemaining - 1
        }));
      }, 1000);
    } else if (assessmentData.timeRemaining === 0) {
      setCurrentPhase('results');
      fetchBehavioralAnalytics();
    }
    
    return () => clearInterval(interval);
  }, [currentPhase, assessmentData.timeRemaining]);

  // Fetch behavioral analytics (simulated)
  const fetchBehavioralAnalytics = () => {
    setTimeout(() => {
      setBehavioralMetrics({
        suspiciousActivity: {
          eyeMovement: 3,
          headMovement: 2,
          audioAnomalies: 1,
          tabSwitches: 0
        },
        attentionScore: 85,
        riskLevel: 'Low',
        totalViolations: 6,
        timeAnalysis: [
          { time: '0-10min', violations: 2 },
          { time: '10-20min', violations: 3 },
          { time: '20-30min', violations: 1 }
        ]
      });
    }, 2000);
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const sampleQuestions = [
    "What is the time complexity of binary search?",
    "Explain the difference between HTTP and HTTPS.",
    "What is the purpose of React hooks?",
    "Define polymorphism in object-oriented programming.",
    "What is the difference between SQL and NoSQL databases?"
  ];

  // Setup Phase
  if (currentPhase === 'setup') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6">
        <div className="max-w-4xl mx-auto">
          <div className="bg-white rounded-lg shadow-lg p-8">
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold text-gray-800 mb-4">Proctored Assessment Setup</h1>
              <p className="text-gray-600">Please ensure your camera and microphone are working properly</p>
            </div>
            
            <div className="grid md:grid-cols-2 gap-8">
              <div className="space-y-6">
                <div className="bg-gray-50 rounded-lg p-6">
                  <h3 className="text-lg font-semibold mb-4 flex items-center">
                    <Camera className="mr-2 text-blue-600" size={20} />
                    Camera Setup
                  </h3>
                  <video
                    ref={videoRef}
                    autoPlay
                    muted
                    className="w-full h-48 bg-gray-200 rounded-lg object-cover"
                  />
                  <button
                    onClick={initializeMedia}
                    className="mt-4 w-full bg-blue-600 text-white py-2 px-4 rounded-lg hover:bg-blue-700 transition-colors"
                  >
                    Enable Camera & Microphone
                  </button>
                </div>
              </div>
              
              <div className="space-y-6">
                <div className="bg-gray-50 rounded-lg p-6">
                  <h3 className="text-lg font-semibold mb-4">System Requirements</h3>
                  <div className="space-y-3">
                    <div className="flex items-center">
                      <CheckCircle className="text-green-500 mr-2" size={16} />
                      <span className="text-sm">Stable internet connection</span>
                    </div>
                    <div className="flex items-center">
                      <CheckCircle className="text-green-500 mr-2" size={16} />
                      <span className="text-sm">Working camera and microphone</span>
                    </div>
                    <div className="flex items-center">
                      <CheckCircle className="text-green-500 mr-2" size={16} />
                      <span className="text-sm">Well-lit environment</span>
                    </div>
                    <div className="flex items-center">
                      <CheckCircle className="text-green-500 mr-2" size={16} />
                      <span className="text-sm">Quiet surroundings</span>
                    </div>
                  </div>
                </div>
                
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                  <div className="flex items-start">
                    <AlertTriangle className="text-yellow-600 mr-2 mt-1" size={16} />
                    <div className="text-sm text-yellow-800">
                      <strong>Important:</strong> You will be monitored throughout the assessment. 
                      Any suspicious activity will be recorded and flagged.
                    </div>
                  </div>
                </div>
                
                <button
                  onClick={() => setCurrentPhase('liveness')}
                  className="w-full bg-green-600 text-white py-3 px-6 rounded-lg hover:bg-green-700 transition-colors font-semibold"
                >
                  Start Liveness Detection
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Liveness Detection Phase
  if (currentPhase === 'liveness') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-50 to-pink-100 p-6">
        <div className="max-w-3xl mx-auto">
          <div className="bg-white rounded-lg shadow-lg p-8">
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold text-gray-800 mb-4">Liveness Detection</h1>
              <p className="text-gray-600">Please look directly at the camera and speak clearly</p>
            </div>
            
            <div className="grid md:grid-cols-2 gap-8">
              <div>
                <video
                  ref={videoRef}
                  autoPlay
                  muted
                  className="w-full h-64 bg-gray-200 rounded-lg object-cover"
                />
                <canvas ref={canvasRef} className="hidden" />
              </div>
              
              <div className="space-y-6">
                <div className="space-y-4">
                  <div className={`flex items-center p-4 rounded-lg ${livenessChecks.faceDetection ? 'bg-green-50 border border-green-200' : 'bg-gray-50 border border-gray-200'}`}>
                    {livenessChecks.faceDetection ? 
                      <CheckCircle className="text-green-500 mr-3" size={20} /> :
                      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mr-3"></div>
                    }
                    <span className={livenessChecks.faceDetection ? 'text-green-700' : 'text-gray-600'}>
                      Face Detection
                    </span>
                  </div>
                  
                  <div className={`flex items-center p-4 rounded-lg ${livenessChecks.voiceDetection ? 'bg-green-50 border border-green-200' : 'bg-gray-50 border border-gray-200'}`}>
                    {livenessChecks.voiceDetection ? 
                      <CheckCircle className="text-green-500 mr-3" size={20} /> :
                      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mr-3"></div>
                    }
                    <span className={livenessChecks.voiceDetection ? 'text-green-700' : 'text-gray-600'}>
                      Voice Detection
                    </span>
                  </div>
                  
                  <div className={`flex items-center p-4 rounded-lg ${livenessChecks.livenessVerified ? 'bg-green-50 border border-green-200' : 'bg-gray-50 border border-gray-200'}`}>
                    {livenessChecks.livenessVerified ? 
                      <CheckCircle className="text-green-500 mr-3" size={20} /> :
                      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mr-3"></div>
                    }
                    <span className={livenessChecks.livenessVerified ? 'text-green-700' : 'text-gray-600'}>
                      Liveness Verified
                    </span>
                  </div>
                </div>
                
                <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                  <h4 className="font-semibold text-blue-800 mb-2">Instructions:</h4>
                  <ul className="text-sm text-blue-700 space-y-1">
                    <li>• Look directly at the camera</li>
                    <li>• Say "Hello, I am ready for the assessment"</li>
                    <li>• Keep your face clearly visible</li>
                    <li>• Ensure good lighting</li>
                  </ul>
                </div>
                
                <button
                  onClick={performLivenessCheck}
                  className="w-full bg-purple-600 text-white py-3 px-6 rounded-lg hover:bg-purple-700 transition-colors font-semibold"
                >
                  Begin Liveness Check
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Assessment Phase
  if (currentPhase === 'assessment') {
    return (
      <div className="min-h-screen bg-gray-50">
        {/* Header with monitoring indicators */}
        <div className="bg-white shadow-sm border-b px-6 py-4">
          <div className="flex justify-between items-center">
            <div className="flex items-center space-x-6">
              <h1 className="text-xl font-semibold text-gray-800">Technical Assessment</h1>
              <div className="flex items-center space-x-4">
                <div className="flex items-center">
                  <div className="w-3 h-3 bg-green-500 rounded-full mr-2 animate-pulse"></div>
                  <Camera size={16} className="text-gray-600 mr-1" />
                  <span className="text-sm text-gray-600">Recording</span>
                </div>
                <div className="flex items-center">
                  <div className="w-3 h-3 bg-red-500 rounded-full mr-2 animate-pulse"></div>
                  <Mic size={16} className="text-gray-600 mr-1" />
                  <span className="text-sm text-gray-600">Monitoring</span>
                </div>
              </div>
            </div>
            
            <div className="flex items-center space-x-6">
              <div className="flex items-center">
                <Clock className="text-gray-600 mr-2" size={16} />
                <span className="text-lg font-mono font-semibold text-red-600">
                  {formatTime(assessmentData.timeRemaining)}
                </span>
              </div>
              <div className="text-sm text-gray-600">
                Question {assessmentData.currentQuestion} of {assessmentData.totalQuestions}
              </div>
            </div>
          </div>
        </div>

        <div className="flex">
          {/* Main Content */}
          <div className="flex-1 p-6">
            <div className="max-w-4xl mx-auto">
              <div className="bg-white rounded-lg shadow-sm p-8">
                <div className="mb-6">
                  <div className="flex justify-between items-center mb-4">
                    <h2 className="text-lg font-semibold text-gray-800">
                      Question {assessmentData.currentQuestion}
                    </h2>
                    <div className="text-sm text-gray-500">
                      Multiple Choice
                    </div>
                  </div>
                  
                  <div className="w-full bg-gray-200 rounded-full h-2 mb-6">
                    <div 
                      className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${(assessmentData.currentQuestion / assessmentData.totalQuestions) * 100}%` }}
                    ></div>
                  </div>
                  
                  <div className="prose max-w-none">
                    <p className="text-lg text-gray-800 mb-6">
                      {sampleQuestions[assessmentData.currentQuestion - 1]}
                    </p>
                    
                    <div className="space-y-3">
                      {['O(log n)', 'O(n)', 'O(n log n)', 'O(1)'].map((option, index) => (
                        <label key={index} className="flex items-center p-4 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                          <input
                            type="radio"
                            name="answer"
                            value={option}
                            className="mr-3"
                            onChange={() => {
                              setAssessmentData(prev => ({
                                ...prev,
                                answers: { ...prev.answers, [prev.currentQuestion]: option }
                              }));
                            }}
                          />
                          <span className="text-gray-700">{option}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
                
                <div className="flex justify-between">
                  <button
                    onClick={() => {
                      if (assessmentData.currentQuestion > 1) {
                        setAssessmentData(prev => ({
                          ...prev,
                          currentQuestion: prev.currentQuestion - 1
                        }));
                      }
                    }}
                    disabled={assessmentData.currentQuestion === 1}
                    className="px-6 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  
                  <button
                    onClick={() => {
                      if (assessmentData.currentQuestion < assessmentData.totalQuestions) {
                        setAssessmentData(prev => ({
                          ...prev,
                          currentQuestion: prev.currentQuestion + 1
                        }));
                      } else {
                        setCurrentPhase('results');
                        fetchBehavioralAnalytics();
                      }
                    }}
                    className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                  >
                    {assessmentData.currentQuestion === assessmentData.totalQuestions ? 'Submit' : 'Next'}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Monitoring Panel */}
          <div className="w-80 bg-white border-l border-gray-200 p-4">
            <h3 className="font-semibold text-gray-800 mb-4">Live Monitoring</h3>
            
            <div className="space-y-4">
              <div className="bg-gray-50 rounded-lg p-3">
                <video
                  ref={videoRef}
                  autoPlay
                  muted
                  className="w-full h-32 bg-gray-200 rounded object-cover"
                />
              </div>
              
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Eye Tracking</span>
                  <span className="text-green-600 font-semibold">Normal</span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Audio Level</span>
                  <div className="flex items-center">
                    <div className="w-12 h-2 bg-gray-200 rounded-full mr-2">
                      <div className="w-8 h-2 bg-green-500 rounded-full animate-pulse"></div>
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600">Violations</span>
                  <span className="text-orange-600 font-semibold">2</span>
                </div>
              </div>
              
              {alerts.length > 0 && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                  <h4 className="font-semibold text-yellow-800 text-sm mb-2">Alerts</h4>
                  <div className="space-y-1">
                    {alerts.map((alert, index) => (
                      <div key={index} className="text-xs text-yellow-700">
                        {alert.message}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Results Phase
  if (currentPhase === 'results') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-green-50 to-blue-100 p-6">
        <div className="max-w-6xl mx-auto">
          <div className="bg-white rounded-lg shadow-lg p-8">
            <div className="text-center mb-8">
              <h1 className="text-3xl font-bold text-gray-800 mb-4">Assessment Complete</h1>
              <p className="text-gray-600">Your submission has been recorded and analyzed</p>
            </div>
            
            {behavioralMetrics ? (
              <div className="grid lg:grid-cols-2 gap-8">
                {/* Assessment Summary */}
                <div className="space-y-6">
                  <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold mb-4 flex items-center">
                      <FileText className="mr-2 text-blue-600" size={20} />
                      Assessment Summary
                    </h3>
                    <div className="space-y-3">
                      <div className="flex justify-between">
                        <span className="text-gray-600">Questions Attempted</span>
                        <span className="font-semibold">{assessmentData.totalQuestions}/10</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Time Taken</span>
                        <span className="font-semibold">28:45</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-600">Status</span>
                        <span className="font-semibold text-green-600">Submitted</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold mb-4 flex items-center">
                      <BarChart3 className="mr-2 text-green-600" size={20} />
                      Proctoring Analysis
                    </h3>
                    <div className="space-y-4">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-600">Overall Risk Level</span>
                        <span className={`px-3 py-1 rounded-full text-sm font-semibold ${
                          behavioralMetrics.riskLevel === 'Low' ? 'bg-green-100 text-green-800' :
                          behavioralMetrics.riskLevel === 'Medium' ? 'bg-yellow-100 text-yellow-800' :
                          'bg-red-100 text-red-800'
                        }`}>
                          {behavioralMetrics.riskLevel}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-gray-600">Attention Score</span>
                        <span className="font-semibold text-blue-600">{behavioralMetrics.attentionScore}%</span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-gray-600">Total Violations</span>
                        <span className="font-semibold text-orange-600">{behavioralMetrics.totalViolations}</span>
                      </div>
                    </div>
                  </div>
                </div>
                
                {/* Behavioral Analytics */}
                <div className="space-y-6">
                  <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold mb-4 flex items-center">
                      <Eye className="mr-2 text-purple-600" size={20} />
                      Behavioral Metrics
                    </h3>
                    <div className="space-y-4">
                      <div className="flex justify-between items-center">
                        <span className="text-gray-600">Eye Movement Irregularities</span>
                        <span className="font-semibold">{behavioralMetrics.suspiciousActivity.eyeMovement}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-600">Head Movement Alerts</span>
                        <span className="font-semibold">{behavioralMetrics.suspiciousActivity.headMovement}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-600">Audio Anomalies</span>
                        <span className="font-semibold">{behavioralMetrics.suspiciousActivity.audioAnomalies}</span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-gray-600">Tab Switches</span>
                        <span className="font-semibold">{behavioralMetrics.suspiciousActivity.tabSwitches}</span>
                      </div>
                    </div>
                  </div>
                  
                  <div className="bg-gray-50 rounded-lg p-6">
                    <h3 className="text-lg font-semibold mb-4">Time-based Analysis</h3>
                    <div className="space-y-3">
                      {behavioralMetrics.timeAnalysis.map((period, index) => (
                        <div key={index} className="flex justify-between items-center">
                          <span className="text-gray-600">{period.time}</span>
                          <div className="flex items-center">
                            <div className="w-24 h-2 bg-gray-200 rounded-full mr-3">
                              <div 
                                className="h-2 bg-red-400 rounded-full"
                                style={{ width: `${(period.violations / 5) * 100}%` }}
                              ></div>
                            </div>
                            <span className="text-sm font-semibold">{period.violations}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-12">
                <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
                <p className="text-gray-600">Analyzing behavioral data...</p>
              </div>
            )}
            
            <div className="mt-8 text-center">
              <button
                onClick={() => {
                  setCurrentPhase('setup');
                  setBehavioralMetrics(null);
                  setAssessmentData({
                    currentQuestion: 1,
                    totalQuestions: 10,
                    timeRemaining: 1800,
                    answers: {}
                  });
                }}
                className="bg-blue-600 text-white py-3 px-8 rounded-lg hover:bg-blue-700 transition-colors font-semibold"
              >
                Take Another Assessment
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return null;
};

export default ProctoredAssessment;