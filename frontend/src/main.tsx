import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./chat.css";
import { storedAppearance, storedArchivistMode } from "./modes";

function initializeStoredMode() {
  const mode = storedArchivistMode();
  document.documentElement.dataset.vibe = storedAppearance(mode);
}

initializeStoredMode();

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
