import React, { useState, useEffect } from 'react';
import Editor from '@monaco-editor/react';
import '../../styles/HtmlEditor.css';

const HtmlEditor = ({ initialHtml, onRunScan, isScanning }) => {
  const [code, setCode] = useState(initialHtml || '');

  // Keep editor in sync if the parent updates the initial HTML
  useEffect(() => {
    if (initialHtml) {
      setCode(initialHtml);
    }
  }, [initialHtml]);

  const handleEditorChange = (value) => {
    setCode(value);
  };

  const handleScanClick = () => {
    if (onRunScan) {
      onRunScan(code);
    }
  };

  return (
    <div className="html-editor-wrapper">
      <div className="editor-header">
        <h3>HTML Editor</h3>
        <button 
          className="run-scan-button" 
          onClick={handleScanClick}
          disabled={isScanning || !code.trim()}
        >
          {isScanning ? 'Scanning...' : 'Run Scan'}
        </button>
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
            formatOnPaste: true,
            fontSize: 14,
            tabSize: 2,
          }}
        />
      </div>
    </div>
  );
};

export default HtmlEditor;