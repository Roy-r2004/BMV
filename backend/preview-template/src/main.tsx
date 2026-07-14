import { Component, type ErrorInfo, type ReactNode, StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';
import { RECIPE_ID } from './lib/recipe-id';

document.documentElement.dataset.recipe = RECIPE_ID;

/** Catch render crashes so the iframe never stays a silent white screen. */
class PreviewErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[preview]', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            fontFamily: 'system-ui, sans-serif',
            padding: '2rem',
            maxWidth: 520,
            margin: '10vh auto',
            color: '#0f172a',
          }}
        >
          <p style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.08em', color: '#be185d' }}>
            PREVIEW ERROR
          </p>
          <h1 style={{ fontSize: 22, margin: '0.5rem 0 0.75rem' }}>This screen failed to render</h1>
          <p style={{ color: '#475569', lineHeight: 1.5 }}>
            Usually missing mock data (for example <code>brand.design_system</code>). Refine chat or
            regenerate to fix.
          </p>
          <pre
            style={{
              marginTop: '1rem',
              padding: '0.75rem 1rem',
              background: '#f1f5f9',
              borderRadius: 8,
              fontSize: 12,
              overflow: 'auto',
            }}
          >
            {this.state.error.message}
          </pre>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <PreviewErrorBoundary>
      <App />
    </PreviewErrorBoundary>
  </StrictMode>,
);
