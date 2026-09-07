import { BrowserRouter, Route, Routes } from "react-router-dom";
import { ReplayPage } from "./routes/ReplayPage";
import { ReplayPlansPage } from "./routes/ReplayPlansPage";
import { ScenarioEditorPage } from "./routes/ScenarioEditorPage";
import { ScenarioLibraryPage } from "./routes/ScenarioLibraryPage";
import { ScenarioVersionViewerPage } from "./routes/ScenarioVersionViewerPage";
import { SdrConsolePage } from "./routes/SdrConsolePage";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ScenarioLibraryPage />} />
        <Route path="/agents" element={<SdrConsolePage />} />
        <Route path="/scenarios/:scenarioId" element={<ScenarioEditorPage />} />
        <Route
          path="/scenarios/:scenarioId/versions/:versionNumber"
          element={<ScenarioVersionViewerPage />}
        />
        <Route path="/scenarios/:scenarioId/replay" element={<ReplayPlansPage />} />
        <Route
          path="/scenarios/:scenarioId/replay-plans/:planId/runs/:runId"
          element={<ReplayPage />}
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
