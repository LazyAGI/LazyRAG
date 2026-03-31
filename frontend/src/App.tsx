import { HashRouter } from "react-router-dom";
import AppRouter from "./router";

function App() {
  return (
    <HashRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <AppRouter />
    </HashRouter>
  );
}

export default App;
