import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";
import "./chat.css";
import { DEFAULT_VIBE } from "./vibes";

// Every visit opens in the default theme; paint it before React mounts to avoid a flash.
document.documentElement.dataset.vibe = DEFAULT_VIBE;

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
