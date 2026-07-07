import { useAiStatus } from '../../hooks/useAiStatus';
import GenerationCinematic from '../preview/GenerationCinematic';

interface Props {
  businessName?: string;
}

export default function GeneratingOverlay({ businessName }: Props) {
  const aiStatus = useAiStatus(12000);
  const modelsPulling = aiStatus?.provider === 'ollama' && !aiStatus.ready;

  if (modelsPulling) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-navy text-white overflow-hidden">
        <div className="absolute inset-0 hero-mesh pointer-events-none opacity-40" />
        <div className="text-center max-w-md px-6">
          <div className="w-16 h-16 border-2 border-cyan-400/30 border-t-cyan-400 rounded-full animate-spin mx-auto mb-6" />
          <h2 className="text-2xl font-bold mb-2">Setting up AI models</h2>
          <p className="text-white/60 text-sm">
            Downloading models ({aiStatus?.models_ready_count ?? 0}/{aiStatus?.models_required_count ?? 3} ready).
            This one-time setup is ~10 GB — then generation starts automatically.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-[100] bg-navy text-white overflow-y-auto overflow-x-hidden">
      <GenerationCinematic
        businessName={businessName}
        title="Creating your business version"
      />
    </div>
  );
}
