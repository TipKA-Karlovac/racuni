import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import Shell from "./Shell.jsx";
import Clients from "./pages/Clients.jsx";
import DocumentForm from "./pages/DocumentForm.jsx";
import DocumentView from "./pages/DocumentView.jsx";
import Documents from "./pages/Documents.jsx";
import Home from "./pages/Home.jsx";
import Settings from "./pages/Settings.jsx";
import "./styles.css";
import "./app.css";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<Home />} />
          <Route path="racuni" element={<Documents kind="invoice" />} />
          <Route path="ponude" element={<Documents kind="quote" />} />
          <Route path="novi/:kind" element={<DocumentForm />} />
          <Route path="dokument/:id" element={<DocumentView />} />
          <Route path="dokument/:id/uredi" element={<DocumentForm />} />
          <Route path="klijenti" element={<Clients />} />
          <Route path="postavke" element={<Settings />} />
          <Route path="*" element={<p>Stranica ne postoji.</p>} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
);
