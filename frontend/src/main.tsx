import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./theme/fonts.css";
import "katex/dist/katex.min.css";
import "./index.css";

const container = document.getElementById("root");
if (!container) throw new Error("root element missing");
createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
