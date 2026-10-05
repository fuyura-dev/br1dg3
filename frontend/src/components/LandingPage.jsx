import React from 'react';
import { useNavigate } from 'react-router-dom';
import '../styles/LandingPage.css';

export default function LandingPage() {
  const navigate = useNavigate();

  const features = [
    {
      title: "Semantic Dependency Graph",
      desc: "Models structural and semantic relationships among HTML elements (like ARIA references and heading hierarchies) to guide accurate repairs.",
      icon: (
        <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--color-accent)" }}>
          <circle cx="18" cy="5" r="3"></circle>
          <circle cx="6" cy="12" r="3"></circle>
          <circle cx="18" cy="19" r="3"></circle>
          <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line>
          <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line>
        </svg>
      )
    },
    {
      title: "LLM-Based Remediation",
      desc: "Utilizes Gemini 3.1 Flash-Lite to dynamically generate context-aware, dependency-guided accessibility patches in real-time.",
      icon: (
        <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--metric-effectiveness)" }}>
          <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
        </svg>
      )
    },
    {
      title: "Comprehensive Validation",
      desc: "Evaluates generated patches across effectiveness, safety, structural preservation, efficiency, and semantic dependency preservation.",
      icon: (
        <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--color-success)" }}>
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
        </svg>
      )
    }
  ];

  const developers = [
    { name: "Joseph C. Acacio", avatar: "JA" },
    { name: "John Lloyd T. Allas", avatar: "JA" },
    { name: "Ivan Joseph M. Bontia", avatar: "IB" },
    { name: "Janine P. Lumbang", avatar: "JL" },
    { name: "Bryan B. Montecalvo", avatar: "BM" }
  ];

  const scrollToSection = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="landing-page">
      <header className="landing-header">
        <div className="landing-logo" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <img src="/BR1DG3 - Logo.png" alt="BR1DG3 Logo" style={{ width: '32px', height: '32px', objectFit: 'contain', mixBlendMode: 'multiply' }} />
          <h2>br1dg3</h2>
        </div>
        <nav className="landing-nav">
          <button className="nav-btn" onClick={() => scrollToSection('project')}>The Project</button>
          <button className="nav-btn" onClick={() => scrollToSection('team')}>Meet the Team</button>
        </nav>
      </header>

      <main className="landing-main">
        <div className="hero-section">
          <div className="hero-badge">PUP BSCS Thesis 2026</div>
          <h1 className="hero-title">
            BR1DG3: LLM-Based Repair <br />
            <span className="hero-highlight">with SDG Context.</span>
          </h1>
          <p className="hero-subtitle">
            A dependency-aware web accessibility remediation system for visually impaired users. 
            Moving beyond isolated fixes to structurally consistent, intelligent code repair.
          </p>
          <div className="hero-actions">
            <button className="btn-primary" onClick={() => navigate('/studio')}>
              Launch Studio
            </button>
          </div>
        </div>

        <div className="features-section">
          {features.map((f, i) => (
            <div key={i} className="feature-card">
              <div className="feature-icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.desc}</p>
            </div>
          ))}
        </div>

        <div className="project-section" id="project">
          <h2 className="section-title">The Digital Divide</h2>
          <p className="project-desc">
            Web accessibility is essential for individuals with visual disabilities, yet <strong>95.9% of top homepages</strong> contain detectable WCAG failures. 
            While automated detection tools exist, remediation has largely remained a tedious, manual process.
            <br/><br/>
            Existing LLM-based repair systems treat accessibility violations as an independent, flat list, generating corrections without considering the 
            semantic dependencies between HTML elements. <strong>BR1DG3</strong> bridges this gap by constructing a Semantic Dependency Graph (SDG) 
            to provide critical structural context to the LLM, ensuring that repairs are not only locally valid, but globally consistent.
          </p>
        </div>

        <div className="about-section" id="team">
          <h2 className="section-title">The Researchers</h2>
          <p className="section-subtitle">Polytechnic University of the Philippines • BS Computer Science</p>
          <div className="developer-grid five-cols">
            {developers.map((dev, i) => (
              <div key={i} className="developer-card">
                <div className="developer-avatar">{dev.avatar}</div>
                <h3>{dev.name}</h3>
                <span className="developer-role">Researcher</span>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}
