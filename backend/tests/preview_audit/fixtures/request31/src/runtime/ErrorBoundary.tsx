import { Component, type ErrorInfo, type ReactNode } from "react";

type Props = { children: ReactNode };
type State = { failed: boolean };

export class CandidateErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("candidate-render-error", error, info);
  }

  render(): ReactNode {
    if (this.state.failed) {
      return <main role="alert">This candidate could not render.</main>;
    }
    return this.props.children;
  }
}
