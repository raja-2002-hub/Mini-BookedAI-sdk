import "./styles.css";
import React from "react";
import { createRoot } from "react-dom/client";

function App() {
  return (
    <div className="widget-root">
      <h2>My Widget</h2>
      <button id="actionBtn" onClick={() => alert("Clicked!")}>Click me</button>
    </div>
  );
}

export default App;

const rootEl = document.getElementById("my-widget-root");
if (rootEl) {
  createRoot(rootEl).render(<App />);
}
