import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { initTheme } from "./features/theme/useTheme";
import "./index.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Не найден элемент #root");
}

initTheme();

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
