import { useState } from "react";
import LivenessDetection from "./components/LivenessDetection";
import VoiceAuth from "./components/VoiceAuth";
import EnvSoundDetect from "./components/EnvSoundDetect";
import FaceVerify from "./components/FaceVerify";
import ObjectDetect from "./components/ObjectDetect";
import GazePosture from "./components/GazePosture";
import ProctoredAssessment from "./components/Assessment";
import ProctoringTestInterface from "./components/Proctor";
import SessionReportDisplay from "./components/Report";
// import "./index.css"
function App() {
  const [count, setCount] = useState(0);

  return (
    <>
      {/* <LivenessDetection /> */}
      {/* <VoiceAuth /> */}
      {/* <EnvSoundDetect /> */}
      {/* <FaceVerify />  */}
      {/* <GazePosture/> */}
      {/* <ObjectDetect /> */}
      {/* <ProctoredAssessment /> */}
      <ProctoringTestInterface />
      {/* <SessionReport /> */}
    </>
  );
}

export default App;
