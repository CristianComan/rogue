import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ScenarioEditorPage } from "./routes/ScenarioEditorPage";
import { ScenarioLibraryPage } from "./routes/ScenarioLibraryPage";
import { ScenarioVersionViewerPage } from "./routes/ScenarioVersionViewerPage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ScenarioLibraryPage />} />
        <Route path="/scenarios/:scenarioId" element={<ScenarioEditorPage />} />
        <Route
          path="/scenarios/:scenarioId/versions/:versionNumber"
          element={<ScenarioVersionViewerPage />}
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
