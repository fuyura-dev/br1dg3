import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAccessibilityStudio } from "../../hooks/useAccessibilityStudio.js";

import HtmlEditor from "./HtmlEditor.jsx";
import SdgGraphModal from "./SdgGraphModal.jsx";
import DiffViewer from "./DiffViewer.jsx";

import ViolationsPanel from "./ViolationsPanel.jsx";
import SdgContextPanel from "./SdgContextPanel.jsx";
import RepairSummary from "./RepairSummary.jsx";
import EvaluationSummary from "./EvaluationSummary.jsx";
import TerminalLogs from "./TerminalLogs.jsx";
import ErrorBoundary from "../ErrorBoundary.jsx";
import '../../styles/AccessibilityStudio.css';

function AccessibilityStudio() {
  const navigate = useNavigate();
  const {
    status,
    errorMessage,
    htmlSource,
    repairedHtml,
    violations,
    evaluationMetrics,
    documentGraph,
    selectedViolation,
    sdgContext,
    repair,
    selectViolation,
    runScan,
    runRepair,
  } = useAccessibilityStudio();

  const [isGraphOpen, setGraphOpen] = useState(false);
  const [showRepairToast, setShowRepairToast] = useState(false);
  const [showScanToast, setShowScanToast] = useState(false);

  // Show a success toast when a scan or repair finishes
  useEffect(() => {
    if (status === "success") {
      if (repairedHtml) {
        setShowRepairToast(true);
        setShowScanToast(false);
        const timer = setTimeout(() => setShowRepairToast(false), 10000);
        return () => clearTimeout(timer);
      } else {
        setShowScanToast(true);
        setShowRepairToast(false);
        const timer = setTimeout(() => setShowScanToast(false), 10000);
        return () => clearTimeout(timer);
      }
    } else {
      setShowRepairToast(false);
      setShowScanToast(false);
    }
  }, [status, repairedHtml]);

  const handleOpenGraph = useCallback(() => {
    setGraphOpen(true);
  }, []);

  const handleCloseGraph = useCallback(() => {
    setGraphOpen(false);
  }, []);

  const handleBackToLanding = useCallback(() => {
    if (htmlSource && htmlSource.trim() !== '') {
      const confirmLeave = window.confirm("You have unsaved changes. Are you sure you want to leave? All scan results and generated repairs will be lost.");
      if (!confirmLeave) return;
    }
    navigate('/');
  }, [htmlSource, navigate]);

  // Prevent accidental navigation/refresh data loss
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (htmlSource && htmlSource.trim() !== '') {
        e.preventDefault();
        e.returnValue = ''; // Required for Chrome
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [htmlSource]);

  return (
    <div className="studio-page-wrapper">
      <div className="accessibility-studio">
        <header className="accessibility-studio__header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <img className="br1dg3-logo" src="/BR1DG3 - Logo.png" alt="BR1DG3 Logo" style={{ width: '40px', height: '40px', objectFit: 'contain' }} />
            <h1 style={{ margin: 0 }}>BR1DG3 — Accessibility Repair Studio</h1>
          </div>

          <button
            className="accessibility-studio__back-btn"
            onClick={handleBackToLanding}
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="19" y1="12" x2="5" y2="12"></line>
              <polyline points="12 19 5 12 12 5"></polyline>
            </svg>
            Back to Landing
          </button>
        </header>

        <ErrorBoundary>
          {errorMessage && (
            <div role="alert" style={{ padding: "12px 16px", marginBottom: "16px", borderRadius: "8px", backgroundColor: "rgba(220, 38, 38, 0.15)", color: "#fca5a5", border: "1px solid rgba(220, 38, 38, 0.4)" }}>
              {errorMessage}
            </div>
          )}

          {showRepairToast && (
            <div className="repair-success-toast" role="alert" aria-live="assertive">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                <polyline points="22 4 12 14.01 9 11.01"></polyline>
              </svg>
              <div>
                <strong>Repair Completed Successfully!</strong>
                <p>AI patches have been seamlessly integrated.</p>
              </div>
              <button onClick={() => setShowRepairToast(false)} className="toast-close-btn">&times;</button>
              <div className="toast-progress-bar"></div>
            </div>
          )}

          {showScanToast && (
            <div className="repair-success-toast" role="alert" aria-live="assertive">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                <polyline points="11 8 11 11 14 14"></polyline>
              </svg>
              <div>
                <strong>Scan Completed Successfully!</strong>
                <p>Detected {violations.length} accessibility violations.</p>
              </div>
              <button onClick={() => setShowScanToast(false)} className="toast-close-btn">&times;</button>
              <div className="toast-progress-bar"></div>
            </div>
          )}

          <div className="accessibility-studio__workspace">
            <HtmlEditor
              initialHtml={htmlSource}
              isScanning={status === "scanning"}
              isRepairing={status === "repairing"}
              onRunScan={runScan}
              onRunRepair={runRepair}
              highlightLine={selectedViolation?.line ?? null}
              highlightImpact={selectedViolation?.impact ?? null}
            />

            <ViolationsPanel
              violations={violations}
              selectedId={selectedViolation?.id ?? null}
              onSelect={selectViolation}
            />
            <SdgContextPanel
              violation={selectedViolation}
              context={sdgContext}
              onOpenGraph={handleOpenGraph}
            />
          </div>

          <TerminalLogs isRepairing={status === "repairing"} />

          {/* Stale Data Dimming Wrapper */}
          <div style={{ position: 'relative' }}>

            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '24px',
              transition: 'opacity 0.3s ease',
              opacity: status === 'repairing' ? 0.35 : 1,
              pointerEvents: status === 'repairing' ? 'none' : 'auto',
            }}>
              <RepairSummary violation={selectedViolation} repair={repair} />
              <DiffViewer original={htmlSource} repaired={repairedHtml} />
              <EvaluationSummary metrics={evaluationMetrics} />
            </div>

            {/* Overlay Text (Now outside the dimmed element so it stays solid) */}
            {status === 'repairing' && (
              <div style={{
                position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <div style={{
                  background: '#ffffff',
                  border: '1px solid #e2e8f0',
                  padding: '12px 24px',
                  borderRadius: '999px',
                  boxShadow: '0 4px 12px rgba(15, 23, 42, 0.1)',
                  color: '#2563eb',
                  fontWeight: 600,
                  fontSize: '15px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px'
                }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ animation: 'spin 1.5s linear infinite' }}>
                    <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
                  </svg>
                  Updating AI Repair Results...
                </div>
              </div>
            )}
          </div>

          {isGraphOpen && (
            <SdgGraphModal
              violation={selectedViolation}
              context={sdgContext}
              documentGraph={documentGraph}
              violations={violations}
              onClose={handleCloseGraph}
              onSelectViolation={selectViolation}
            />
          )}
        </ErrorBoundary>
      </div>
    </div>
  );
}

export default AccessibilityStudio;