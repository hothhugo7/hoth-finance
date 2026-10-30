import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { Avisos } from "./components/ui";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Avisos>
      <App />
    </Avisos>
  </StrictMode>,
);
