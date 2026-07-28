import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./chat.css";
import { DEFAULT_VIBE, isVibeId, VIBE_STORAGE_KEY } from "./vibes";

function initializeStoredVibe() {
  try {
    const storedVibe = window.localStorage.getItem(VIBE_STORAGE_KEY);
    document.documentElement.dataset.vibe = isVibeId(storedVibe)
      ? storedVibe
      : DEFAULT_VIBE;
  } catch {
    document.documentElement.dataset.vibe = DEFAULT_VIBE;
  }
}

initializeStoredVibe();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
