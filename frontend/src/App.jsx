import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import LandingPage from './components/LandingPage.jsx';
import AccessibilityStudio from './components/accessibility-studio/AccessibilityStudio.jsx';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/studio" element={<AccessibilityStudio />} />
      </Routes>
    </Router>
  );
}

export default App;
