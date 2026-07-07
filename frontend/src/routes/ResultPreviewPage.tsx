import { useEffect, useState, useCallback } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { motion } from 'framer-motion';
import { getPreview, requestBuild } from '../api/requests';
import type { PreviewResponse } from '../types/request';
import PreviewRefineChat from '../components/PreviewRefineChat';
import BuildRequestCTA from '../components/BuildRequestCTA';
import AiModelsBanner from '../components/AiModelsBanner';
import Logo from '../components/Logo';
import GenerationCinematic from '../components/preview/GenerationCinematic';
import VisualDemoPreview from '../components/VisualDemoPreview';
import PreviewExplainer from '../components/preview/PreviewExplainer';
import PreviewAppPreview from '../components/preview/PreviewAppPreview';
import RoleBasedPreview from '../components/preview/rolePages/RoleBasedPreview';
import DeliveryNavigator from '../components/delivery/DeliveryNavigator';
import { buildDeliveryNavItems } from '../components/delivery/deliveryNavItems';
import FullDeliveryPackage from '../components/delivery/FullDeliveryPackage';
import { useAiStatus } from '../hooks/useAiStatus';
import type { BuildRequestContact } from '../types/buildRequest';

const ease = [0.22, 1, 0.36, 1] as const;

export default function ResultPreviewPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [revealed, setRevealed] = useState(false);
  const aiStatus = useAiStatus(12000);

  const fetchPreview = useCallback(async () => {
    if (!id) return;
    try {
      const data = await getPreview(Number(id));
      setPreview(data);
      if (data.is_generating && !data.concept_name) {
        setTimeout(fetchPreview, 5000);
      }
    } catch {
      setError('Preview not found.');
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchPreview();
  }, [fetchPreview]);

  useEffect(() => {
    if (preview?.concept_name && !preview.is_generating) {
      const t = setTimeout(() => setRevealed(true), 200);
      return () => clearTimeout(t);
    }
    setRevealed(false);
  }, [preview?.concept_name, preview?.is_generating]);

  const handleRequestBuild = async (contact: BuildRequestContact) => {
    if (!id) return;
    await requestBuild(Number(id), contact);
    setPreview((prev) => (prev ? { ...prev, build_requested: true } : prev));
  };

  const requestId = id ? Number(id) : 0;
  const isDemoView = searchParams.get('from') === 'demo';
  const showRefineChat = !isDemoView;
  const chatGutter = showRefineChat ? 'result-with-chat-gutter' : '';

  const handlePreviewUpdate = useCallback((updates: Partial<PreviewResponse>) => {
    setPreview((prev) => (prev ? { ...prev, ...updates } : prev));
  }, []);

  const isGenerating = preview ? preview.is_generating && !preview.concept_name : loading;
  const modelsPulling = aiStatus?.provider === 'ollama' && !aiStatus.ready;

  if (loading && !preview) {
    return (
      <div className="min-h-screen bg-slate-50">
        <GenerationCinematic requestId={requestId || undefined} title="Designing your complete package" />
      </div>
    );
  }

  if (error || !preview) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 mb-4">{error || 'Preview not found'}</p>
          <Link to="/submit" className="gradient-btn">Try Again</Link>
        </div>
      </div>
    );
  }

  if (isGenerating) {
    return (
      <div className="min-h-screen bg-slate-50">
        <AiModelsBanner status={aiStatus} />
        {modelsPulling ? (
          <div className="flex items-center justify-center min-h-[60vh] text-center px-4">
            <div className="w-14 h-14 border-2 border-indigo-200 border-t-indigo-500 rounded-full animate-spin mx-auto mb-5" />
            <p className="text-slate-800 font-medium">Waiting for AI models…</p>
          </div>
        ) : (
          <GenerationCinematic requestId={requestId || undefined} businessName={preview.business_name} title="Building your complete package" compact />
        )}
      </div>
    );
  }

  const previewAppInfo = preview.generated_pages?.preview_app;
  const showLivePreviewApp =
    Boolean(previewAppInfo?.url) &&
    (previewAppInfo?.status === 'ready' || previewAppInfo?.status === 'rebuilding');

  return (
    <div className={`min-h-screen bg-[#f8fafc] ${showRefineChat ? 'result-page--with-chat' : ''}`}>
      <nav className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/90 backdrop-blur-xl">
        <div className="max-w-5xl mx-auto flex items-center justify-between py-3.5 px-4 sm:px-6">
          <Logo />
          <div className="flex items-center gap-3">
            <span className="text-sm text-slate-500 hidden sm:inline">{preview.business_name}</span>
            <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 px-2.5 py-1 rounded-full bg-indigo-50 border border-indigo-100">
              Full package
            </span>
          </div>
        </div>
      </nav>

      <AiModelsBanner status={aiStatus} compact />

      <div className="result-above-fold">
        {revealed && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease }}
            className="result-hero-intro shrink-0 w-full px-3 sm:px-4 pt-3 pb-0"
          >
            <div className="text-center mb-2">
              <p className="text-xs font-semibold text-indigo-600 mb-0.5">
                {isDemoView ? 'Example demo' : 'Built exclusively for you'}
              </p>
              <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
                {preview.concept_name}
              </h1>
            </div>
            {!isDemoView && (
              <PreviewExplainer
                businessName={preview.business_name}
                industry={preview.industry}
                conceptName={preview.concept_name}
              />
            )}
          </motion.div>
        )}

        {/* First screen: nav + full-width product window (fits in viewport) */}
        <section id="live-product" className="result-first-screen scroll-mt-28">
          <div className={`sticky top-14 z-30 shrink-0 w-full px-2 sm:px-3 pt-1 pb-2 bg-[#f8fafc]/95 backdrop-blur-xl ${chatGutter}`}>
            <DeliveryNavigator items={buildDeliveryNavItems(preview, true)} embedded compact />
          </div>

          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, duration: 0.55, ease }}
            className={`result-window-stage flex-1 min-h-0 w-full ${chatGutter}`}
          >
            {showLivePreviewApp && preview.generated_pages ? (
              <div className="h-full w-full">
                <PreviewAppPreview
                  pages={preview.generated_pages}
                  requestId={preview.id}
                  conceptName={preview.concept_name ?? undefined}
                  features={preview.preview_features}
                />
              </div>
            ) : preview.generated_pages?.roles?.length ? (
              <div className="h-full w-full">
                <RoleBasedPreview
                  pages={preview.generated_pages}
                  conceptName={preview.concept_name ?? undefined}
                  features={preview.preview_features}
                />
              </div>
            ) : (
              <div className="desktop-desk desktop-desk--fullbleed rounded-lg sm:rounded-xl p-1.5 sm:p-2 h-full w-full">
                <VisualDemoPreview
                  demo={preview.visual_demo}
                  businessName={preview.business_name}
                  industry={preview.industry}
                  previewFeatures={preview.preview_features}
                  immersive
                  mode="product"
                />
              </div>
            )}
          </motion.div>
        </section>
      </div>

      {/* Full delivery details */}
      <section className="border-t border-slate-200/80 bg-white">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-12 sm:py-16">
          <FullDeliveryPackage preview={preview} liveSiteAbove hideNavigator />
        </div>
      </section>

      <div className="max-w-4xl mx-auto px-4 sm:px-6 pb-28">
        <BuildRequestCTA
          requestId={preview.id}
          conceptName={preview.concept_name}
          businessName={preview.business_name}
          onRequestBuild={handleRequestBuild}
          buildRequested={preview.build_requested}
          demoView={isDemoView}
        />
      </div>

      {showRefineChat && (
        <PreviewRefineChat
          requestId={preview.id}
          onPreviewUpdate={handlePreviewUpdate}
          onRefetchPreview={fetchPreview}
        />
      )}
    </div>
  );
}
