import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AuthProvider } from "./lib/auth";
import { GroupProvider } from "./lib/group-context";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AuthProvider><GroupProvider><App /></GroupProvider></AuthProvider>
  </StrictMode>,
);
