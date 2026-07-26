import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { CandidateErrorBoundary } from "./runtime/ErrorBoundary";
import "./index.css";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root mount point");

createRoot(root).render(
  <StrictMode>
    <CandidateErrorBoundary>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </CandidateErrorBoundary>
  </StrictMode>,
);
