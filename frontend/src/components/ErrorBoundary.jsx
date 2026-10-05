import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("UI Component Error Caught by Boundary:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '24px',
          margin: '16px 0',
          borderRadius: '8px',
          backgroundColor: '#fef2f2',
          border: '1px solid #fca5a5',
          color: '#991b1b',
          fontFamily: 'Inter, sans-serif'
        }}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: '16px' }}>Something went wrong in this section.</h3>
          <p style={{ margin: '0 0 16px 0', fontSize: '14px', opacity: 0.8 }}>
            {this.state.error?.message || "An unexpected error occurred."}
          </p>
          <button 
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: '6px 12px',
              backgroundColor: '#dc2626',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '13px'
            }}
          >
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
