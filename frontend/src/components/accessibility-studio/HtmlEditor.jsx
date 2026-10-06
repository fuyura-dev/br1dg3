import React, { useState, useEffect, useRef } from 'react';
import Editor from '@monaco-editor/react';
import '../../styles/HtmlEditor.css';

const HtmlEditor = ({ initialHtml, onRunScan, onRunRepair, isScanning, isRepairing }) => {
  const [code, setCode] = useState(initialHtml || '');
  
  const [scanTime, setScanTime] = useState(null);
  const [repairTime, setRepairTime] = useState(null);
  const [elapsed, setElapsed] = useState(0);

  // Keep editor in sync if the parent updates the initial HTML
  useEffect(() => {
    if (initialHtml) {
      setCode(initialHtml);
    }
  }, [initialHtml]);

  // Live timer effect
  useEffect(() => {
    let interval;
    if (isScanning || isRepairing) {
      setElapsed(0);
      const start = Date.now();
      interval = setInterval(() => {
        setElapsed(Math.floor((Date.now() - start) / 1000));
      }, 1000);
    } 
    return () => clearInterval(interval);
  }, [isScanning, isRepairing]);

  // Capture final time when done
  const prevScanning = useRef(isScanning);
  const prevRepairing = useRef(isRepairing);

  useEffect(() => {
    if (prevScanning.current && !isScanning) {
      setScanTime(elapsed);
    }
    if (prevRepairing.current && !isRepairing) {
      setRepairTime(elapsed);
    }
    prevScanning.current = isScanning;
    prevRepairing.current = isRepairing;
  }, [isScanning, isRepairing, elapsed]);

  const handleEditorChange = (value) => {
    setCode(value ?? '');
  };

  const handleScanClick = () => {
    if (onRunScan) {
      setScanTime(null);
      setRepairTime(null);
      onRunScan(code);
    }
  };

  const handleRepairClick = () => {
    if (onRunRepair) {
      setRepairTime(null);
      onRunRepair(code);
    }
  };

  const isBusy = isScanning || isRepairing;

  return (
    <div className="html-editor-wrapper">
      <div className="editor-header">
        <h3>HTML Editor</h3>
        <div className="editor-actions" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {scanTime !== null && !isBusy && (
            <span style={{ fontSize: '12px', color: '#64748b', fontWeight: 600 }}>Last scan: {scanTime}s</span>
          )}
          {repairTime !== null && !isBusy && (
            <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 600 }}>Last repair: {repairTime}s</span>
          )}
          <button
            type="button"
            className="run-scan-button"
            onClick={handleScanClick}
            disabled={isBusy || !code.trim()}
          >
            {isScanning ? `Scanning... ${elapsed}s` : 'Run Scan'}
          </button>
          <button
            type="button"
            className="run-repair-button"
            onClick={handleRepairClick}
            disabled={isBusy || !code.trim()}
          >
            {isRepairing ? `Repairing... ${elapsed}s` : 'Run Repair'}
          </button>
        </div>
      </div>

      <div className="editor-container">
        <Editor
          height="100%"
          defaultLanguage="html"
          theme="vs-dark"
          value={code}
          onChange={handleEditorChange}
          options={{
            minimap: { enabled: false },
            wordWrap: 'on',
            formatOnPaste: false,
            fontSize: 14,
            tabSize: 2,
          }}
        />
      </div>
    </div>
  );
};

export default React.memo(HtmlEditor);