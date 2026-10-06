import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import '../styles/LandingPage.css';

export default function LandingPage() {
  const navigate = useNavigate();
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 50);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

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
        <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "#eab308" }}>
          <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>
        </svg>
      )
    },
    {
      title: "Comprehensive Validation",
      desc: "Evaluates generated patches across effectiveness, safety, structural preservation, efficiency, and semantic dependency preservation.",
      icon: (
        <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "#0ea5e9" }}>
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
        </svg>
      )
    }
  ];

  const developers = [
    { name: "Joseph C. Acacio", avatar: "JA", imgSrc: "/joseph.jpg", role: "Quality Assurance Analyst" },
    { name: "John Lloyd T. Allas", avatar: "JA", imgSrc: "/jl.jpg", role: "Front-end Developer" },
    { name: "Ivan Joseph M. Bontia", avatar: "IB", imgSrc: "/ivan.jpg", role: "System Analyst" },
    { name: "Janine P. Lumbang", avatar: "JL", imgSrc: "/janine.jpg", role: "UI/UX Designer" },
    { name: "Bryan B. Montecalvo", avatar: "BM", imgSrc: "/bryan.jpg", role: "Back-end / Prompt Engineer" }
  ];

  const scrollToSection = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    <div className="landing-page">
      <div className="bg-orb orb-1"></div>
      <div className="bg-orb orb-2"></div>
      <div className="bg-orb orb-3"></div>
      <div className="bg-halftone"></div>

      <header className={`landing-header ${isScrolled ? 'scrolled' : ''}`}>
        <div className="landing-logo" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <img src="/BR1DG3 - Logo - Transp2.png" alt="BR1DG3 Logo" style={{ width: '32px', height: '32px', objectFit: 'contain' }} />
        </div>
        <nav className="landing-nav">
          <button className="nav-btn" onClick={() => scrollToSection('project')}>The Project</button>
          <button className="nav-btn" onClick={() => scrollToSection('workflow')}>How it Works</button>
          <button className="nav-btn" onClick={() => scrollToSection('team')}>Meet the Team</button>
          <button className="nav-btn btn-nav-cta" onClick={() => navigate('/studio')}>Launch Studio</button>
        </nav>
      </header>

      <main className="landing-main">
        <div className="hero-section">
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
          <div className="project-content-grid">
            <div className="stat-highlight">
              <span className="stat-number">95.9%</span>
              <span className="stat-text">of top homepages contain detectable WCAG failures.</span>
            </div>
            <p className="project-desc">
              Web accessibility is essential for individuals with visual disabilities, yet automated detection tools only scratch the surface. Remediation has largely remained a tedious, manual process.
              <br /><br />
              Existing LLM-based repair systems treat accessibility violations as an independent, flat list, generating corrections without considering the
              semantic dependencies between HTML elements. <strong>BR1DG3</strong> bridges this gap by constructing a Semantic Dependency Graph (SDG)
              to provide critical structural context to the LLM, ensuring that repairs are not only locally valid, but globally consistent.
            </p>
          </div>
        </div>

        <div className="workflow-section" id="workflow">
          <h2 className="section-title">How BR1DG3 Works</h2>
          <div className="workflow-steps">
            <div className="workflow-step">
              <div className="step-number">1</div>
              <h4>Input HTML</h4>
              <p>Detects violations</p>
            </div>
            <div className="workflow-step">
              <div className="step-number">2</div>
              <h4>Build SDG</h4>
              <p>Maps dependencies</p>
            </div>
            <div className="workflow-step">
              <div className="step-number">3</div>
              <h4>LLM Repair</h4>
              <p>Generates smart patches</p>
            </div>
            <div className="workflow-step">
              <div className="step-number">4</div>
              <h4>Validated Code</h4>
              <p>Accessible HTML</p>
            </div>
          </div>
        </div>

        <div className="demo-section">
          <h2 className="section-title">See It In Action</h2>
          <p className="section-subtitle">A comprehensive suite for accessibility remediation.</p>
          <div className="showcase-gallery">
            <div className="showcase-item">
              <h3 className="showcase-label">Accessibility Repair Studio Interface</h3>
              <img src="/Accessibility Repair Studio Interface.png" alt="Accessibility Repair Studio Interface" className="showcase-img" loading="lazy" />
            </div>
            <div className="showcase-item">
              <h3 className="showcase-label">Execution Trace & Repair Strategy</h3>
              <img src="/Execution Trace and Repair Strategy.png" alt="Execution Trace and Repair Strategy" className="showcase-img" loading="lazy" />
            </div>
            <div className="showcase-item">
              <h3 className="showcase-label">Original vs Repaired HTML (Diff View)</h3>
              <img src="/Original vs Repaired HTML Diff View.png" alt="Original vs Repaired HTML Diff View" className="showcase-img" loading="lazy" />
            </div>
            <div className="showcase-item">
              <h3 className="showcase-label">Validation & Evaluation Summary</h3>
              <img src="/Validation and Evaluation Summary.png" alt="Validation and Evaluation Summary" className="showcase-img" loading="lazy" />
            </div>
          </div>
        </div>


        <div className="about-section" id="team">
          <h2 className="section-title">The Researchers</h2>
          <p className="section-subtitle">Polytechnic University of the Philippines • BS Computer Science</p>
          <div className="developer-grid five-cols">
            {developers.map((dev, i) => (
              <div key={i} className="developer-card">
                <div className="developer-avatar">
                  {dev.imgSrc ? (
                    <img src={dev.imgSrc} alt={dev.name} loading="lazy" />
                  ) : (
                    <span>{dev.avatar}</span>
                  )}
                </div>
                <h3>{dev.name}</h3>
                <span className="developer-role">Researcher</span>
              </div>
            ))}
          </div>
        </div>

        <div className="bottom-cta-section">
          <h2>Ready to repair web accessibility?</h2>
          <p>Experience the SDG-guided remediation engine.</p>
          <button className="btn-primary" onClick={() => navigate('/studio')}>
            Launch BR1DG3 Studio
          </button>
        </div>
      </main>

      <footer className="landing-footer">
        <p>© 2026 BR1DG3. Polytechnic University of the Philippines - BS Computer Science.</p>
      </footer>
    </div>
  );
}
