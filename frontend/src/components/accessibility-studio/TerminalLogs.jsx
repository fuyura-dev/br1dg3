import React, { useEffect, useRef, useState } from "react";
import "../../styles/TerminalLogs.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api";

// Icons for the timeline
const IconAnalyze = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>;
const IconPrompt = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>;
const IconCode = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>;
const IconCheck = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>;
const IconMetrics = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="20" x2="18" y2="10"></line><line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line></svg>;
const IconCascade = () => <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polyline></svg>;

function parseLogLine(log) {
  if (!log || typeof log !== 'string') return { type: 'raw', content: String(log) };

  // 1. Cascade Resolved
  if (log.includes('[CASCADE RESOLVED')) {
    const match = log.match(/\[CASCADE RESOLVED (.*?)\] <(.*?)> \| Rules: \[(.*?)\]/);
    if (match) return { type: 'cascade', token: match[1], tag: match[2], rules: match[3].replace(/['"]/g, ''), raw: log };
  }

  // 2. Not Cascaded (Analysis)
  if (log.includes('[NOT CASCADED')) {
    const match = log.match(/\[NOT CASCADED (.*?)\] <(.*?)>/);
    if (match) return { type: 'analysis', token: match[1], tag: match[2], raw: log };
  }

  // 3. Prompt generation
  if (log.includes('Prompt Size:')) {
    const match = log.match(/\[STEP (.*?)\] Target: <(.*?)>.*?Prompt Size: (.*?) chars/);
    if (match) return { type: 'prompt', token: match[1], tag: match[2], size: match[3], raw: log };
  }

  // 4. LLM Metrics
  if (log.startsWith('[LLM] Status:')) {
    const match = log.match(/Latency: (.*?)s \| Input: (.*?) \| Output: (.*?) \| Thought: (.*?) \| Total: (.*?) tokens/);
    if (match) return { type: 'llm_metrics', latency: match[1], input: match[2], output: match[3], total: match[5], raw: log };
  }

  // 5. LLM Reply
  if (log.includes('LLM Reply')) {
    const match = log.match(/\[STEP (.*?)\] LLM Reply.*?:\n([\s\S]*)/);
    if (match) return { type: 'reply', token: match[1], reply: match[2], raw: log };
  }

  // 6. Applied Result
  if (log.includes('Applied: status=')) {
    const match = log.match(/\[STEP (.*?)\] Applied: status=(.*?) warnings/);
    if (match) return { type: 'applied', token: match[1], status: match[2].trim(), raw: log };
  }

  // 7. Post-repair verification / evaluation
  if (log.includes('[POST-REPAIR]')) {
    return { type: 'post_repair', text: log.replace('[POST-REPAIR]', '').trim(), raw: log };
  }

  // 8. Individual evaluation metric
  if (log.includes('[METRICS]')) {
    return { type: 'metric', text: log.replace('[METRICS]', '').trim(), raw: log };
  }

  // 9. Workflow complete
  if (log.includes('[DONE]')) {
    return { type: 'done', text: log.replace('[DONE]', '').trim(), raw: log };
  }

  if (log.includes('---')) return { type: 'divider', raw: log };

  return { type: 'raw', content: log };
}

function LogItem({ item }) {
  const [expanded, setExpanded] = useState(false);

  if (item.type === 'divider') {
    return <div className="timeline-divider"></div>;
  }

  if (item.type === 'raw') {
    return <div className="timeline-raw">{item.content}</div>;
  }

  const toggleRaw = () => setExpanded(!expanded);

  let icon, title, badge, content;

  switch (item.type) {
    case 'cascade':
      icon = <IconCascade />;
      title = <span>Auto-resolved <code>&lt;{item.tag}&gt;</code></span>;
      badge = <span className="log-badge badge-warning">{item.token}</span>;
      content = `Satisfied rule: ${item.rules}`;
      break;
    case 'analysis':
      icon = <IconAnalyze />;
      title = <span>Analyzing <code>&lt;{item.tag}&gt;</code></span>;
      badge = <span className="log-badge badge-info">{item.token}</span>;
      content = "Extracting SDG dependencies and parent landmarks...";
      break;
    case 'prompt':
      icon = <IconPrompt />;
      title = <span>Building AI Prompt for <code>&lt;{item.tag}&gt;</code></span>;
      badge = <span className="log-badge badge-info">{item.token}</span>;
      content = `Generated Prompt Size: ${item.size} chars`;
      break;
    case 'llm_metrics':
      icon = <IconMetrics />;
      title = <span>LLM Request Completed</span>;
      badge = <span className="log-badge badge-purple">LLM</span>;
      content = `Latency: ${item.latency}s | Tokens: ${item.input} in, ${item.output} out`;
      break;
    case 'reply':
      icon = <IconCode />;
      title = <span>Generated Patch</span>;
      badge = <span className="log-badge badge-info">{item.token}</span>;
      content = (
        <pre className="log-code-block">
          <code>{item.reply}</code>
        </pre>
      );
      break;
    case 'applied':
      const isOk = item.status === 'applied';
      icon = isOk ? <IconCheck /> : <IconCascade />; // fallback icon
      title = <span>Patch Application Result</span>;
      badge = <span className={`log-badge ${isOk ? 'badge-success' : 'badge-danger'}`}>{item.token}</span>;
      content = `Status: ${item.status}`;
      break;
    case 'post_repair':
      icon = <IconAnalyze />;
      title = <span>Verification & Metrics</span>;
      badge = <span className="log-badge badge-info">VERIFY</span>;
      content = item.text;
      break;
    case 'metric':
      icon = <IconAnalyze />;
      title = <span>Thesis Metric</span>;
      badge = <span className="log-badge badge-info">METRIC</span>;
      content = item.text;
      break;
    case 'done':
      icon = <IconCheck />;
      title = <span>Repair Complete</span>;
      badge = <span className="log-badge badge-success">DONE</span>;
      content = item.text;
      break;
    default:
      return null;
  }

  return (
    <div className={`timeline-item timeline-${item.type}`}>
      <div className="timeline-icon">{icon}</div>
      <div className="timeline-content">
        <div className="timeline-header" onClick={toggleRaw} title="Click to view raw log">
          <div className="timeline-title-wrap">
            {badge}
            <div className="timeline-title">{title}</div>
          </div>
          <span className="timeline-toggle">{expanded ? '▲' : '▼'}</span>
        </div>
        <div className="timeline-body">{content}</div>
        {expanded && (
          <div className="timeline-raw-dump">
            {item.raw}
          </div>
        )}
      </div>
    </div>
  );
}

function TerminalLogs({ isRepairing }) {
  const [logs, setLogs] = useState([]);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    if (!isRepairing) return;
    
    // Clear logs when a new repair starts
    setLogs([]);
    setIsCollapsed(false);
    
    const eventSource = new EventSource(`${API_BASE_URL}/repair/logs`);
    
    eventSource.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const parsed = parseLogLine(message);
        setLogs((prev) => [...prev, parsed]);
      } catch (err) {
        setLogs((prev) => [...prev, { type: 'raw', content: event.data }]);
      }
    };
    
    eventSource.onerror = (error) => {
      console.error("EventSource error:", error);
    };

    return () => {
      eventSource.close();
    };
  }, [isRepairing]);

  useEffect(() => {
    if (!isRepairing && logs.length > 0) {
      // Auto-collapse when repair successfully finishes to save space
      setIsCollapsed(true);
    }
  }, [isRepairing]);

  useEffect(() => {
    // Auto-scroll to bottom only within the container, not the whole page
    if (containerRef.current && !isCollapsed) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, isCollapsed]);

  if (!isRepairing && logs.length === 0) {
    return null; // Don't show if empty and not repairing
  }

  return (
    <div className="terminal-logs-panel">
      <div 
        className="terminal-logs-header" 
        style={{ cursor: 'pointer' }}
        onClick={() => setIsCollapsed(!isCollapsed)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span>Execution Trace</span>
          <span style={{ fontSize: '12px', color: '#64748b', textTransform: 'none', letterSpacing: 'normal', fontWeight: 500 }}>
            — Watch the AI's thought process and HTML patching operations in real-time
          </span>
          {isRepairing && <span className="terminal-logs-pulse"></span>}
        </div>
        <button 
          style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '16px' }}
        >
          {isCollapsed ? '+' : '-'}
        </button>
      </div>
      
      {!isCollapsed && (
        <div className="terminal-logs-content" ref={containerRef}>
          <div className="timeline-container">
            {logs.length === 0 && isRepairing && (
              <div className="timeline-item timeline-raw" style={{ margin: '12px 0 12px 30px' }}>
                <span style={{ color: '#10b981', display: 'flex', alignItems: 'center', gap: '12px', fontSize: '13px' }}>
                  <span className="terminal-logs-pulse"></span> 
                  Initializing AI Engine and connecting to stream...
                </span>
              </div>
            )}
            
            {logs.map((log, index) => (
              <LogItem key={index} item={log} />
            ))}
            
            {!isRepairing && logs.length > 0 && (
              <div className="timeline-item timeline-completed">
                <div className="timeline-icon" style={{ borderColor: '#10b981', color: '#10b981' }}>
                  <IconCheck />
                </div>
                <div className="timeline-content" style={{ border: '1px solid #10b981', background: 'rgba(16, 185, 129, 0.05)' }}>
                  <div className="timeline-header">
                    <div className="timeline-title-wrap">
                      <span className="log-badge badge-success">DONE</span>
                      <div className="timeline-title">All AI Repairs Completed Successfully</div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default React.memo(TerminalLogs);
