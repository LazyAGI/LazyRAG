import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.scss";
import "./i18n";

if (import.meta.env.DEV) {
  import("@/utils/testTokenRefresh");
}

const container = document.getElementById("app");
if (!container) throw new Error("Root element #app not found");
const root = createRoot(container);
root.render(<App />);
