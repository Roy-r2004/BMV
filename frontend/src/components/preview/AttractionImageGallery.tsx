import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { API_BASE } from '../../api/client';
import type { AttractionImage } from '../../types/request';

const ease = [0.22, 1, 0.36, 1] as const;

interface Props {
  images: AttractionImage[];
  conceptName?: string;
  businessName?: string;
}

interface RoleGroup {
  roleId: string;
  roleLabel: string;
  images: AttractionImage[];
}

function resolveImageUrl(path: string): string {
  if (path.startsWith('http')) return path;
  return `${API_BASE}${path}`;
}

export default function AttractionImageGallery({ images, conceptName, businessName }: Props) {
  const roleGroups = useMemo<RoleGroup[]>(() => {
    const byRole = new Map<string, RoleGroup>();
    for (const img of images) {
      const group = byRole.get(img.role_id) ?? { roleId: img.role_id, roleLabel: img.role_label, images: [] };
      group.images.push(img);
      byRole.set(img.role_id, group);
    }
    return [...byRole.values()];
  }, [images]);

  const [activeRoleId, setActiveRoleId] = useState(roleGroups[0]?.roleId ?? '');
  const [activeVariant, setActiveVariant] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  const activeGroup = roleGroups.find((g) => g.roleId === activeRoleId) ?? roleGroups[0];
  const activeImage = activeGroup?.images[activeVariant] ?? activeGroup?.images[0];

  useEffect(() => {
    if (!lightboxOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setLightboxOpen(false);
      if (e.key === 'ArrowRight' && activeGroup) {
        setActiveVariant((v) => (v + 1) % activeGroup.images.length);
      }
      if (e.key === 'ArrowLeft' && activeGroup) {
        setActiveVariant((v) => (v - 1 + activeGroup.images.length) % activeGroup.images.length);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [lightboxOpen, activeGroup]);

  if (!activeGroup || !activeImage) return null;

  return (
    <div className="flex h-full min-h-0 w-full flex-1 flex-col gap-2">
      {/* Role switcher */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease }}
        className="flex items-center justify-center gap-1.5 flex-wrap px-2"
      >
        {roleGroups.map((group) => {
          const active = group.roleId === activeGroup.roleId;
          return (
            <button
              key={group.roleId}
              type="button"
              onClick={() => {
                setActiveRoleId(group.roleId);
                setActiveVariant(0);
              }}
              className={`px-3.5 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all duration-200 border ${
                active
                  ? 'bg-slate-900 text-white border-slate-900 shadow-lg shadow-slate-900/20'
                  : 'bg-white/80 text-slate-600 border-slate-200 hover:border-slate-300 hover:text-slate-900'
              }`}
            >
              {group.roleLabel}
            </button>
          );
        })}
      </motion.div>

      {/* Main showcase — browser-chrome frame */}
      <div className="relative flex-1 min-h-0 px-1 sm:px-2">
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.6, ease }}
          className="h-full min-h-0 flex flex-col rounded-xl overflow-hidden border border-slate-200/90 bg-white shadow-[0_24px_70px_-28px_rgba(15,23,42,0.35)]"
        >
          {/* Chrome bar */}
          <div className="shrink-0 flex items-center gap-2 px-3.5 py-2 bg-slate-50/90 border-b border-slate-200/80">
            <span className="flex gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#ff5f57]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#febc2e]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#28c840]" />
            </span>
            <span className="flex-1 mx-2 truncate text-center text-[11px] font-medium text-slate-400 bg-white border border-slate-200/80 rounded-md px-3 py-1">
              {(conceptName || businessName || 'your-business').toLowerCase().replace(/[^a-z0-9]+/g, '')}.app — {activeGroup.roleLabel}
            </span>
            <button
              type="button"
              onClick={() => setLightboxOpen(true)}
              className="shrink-0 text-slate-400 hover:text-slate-700 transition-colors"
              title="View fullscreen"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
              </svg>
            </button>
          </div>

          {/* Image */}
          <div
            className="relative flex-1 min-h-0 bg-slate-100 cursor-zoom-in"
            onClick={() => setLightboxOpen(true)}
          >
            <AnimatePresence mode="wait">
              <motion.img
                key={`${activeGroup.roleId}-${activeVariant}`}
                src={resolveImageUrl(activeImage.image_url)}
                alt={`${activeGroup.roleLabel} — concept ${activeVariant + 1}`}
                initial={{ opacity: 0, scale: 1.015 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.35, ease }}
                className="absolute inset-0 w-full h-full object-cover object-top"
              />
            </AnimatePresence>
          </div>
        </motion.div>
      </div>

      {/* Variant thumbnails */}
      {activeGroup.images.length > 1 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2, duration: 0.5, ease }}
          className="shrink-0 flex items-center justify-center gap-2.5 px-2 pb-1"
        >
          {activeGroup.images.map((img, i) => {
            const active = i === activeVariant;
            return (
              <button
                key={`${img.role_id}-${img.variant}`}
                type="button"
                onClick={() => setActiveVariant(i)}
                className={`relative w-20 h-12 sm:w-24 sm:h-14 rounded-lg overflow-hidden border-2 transition-all duration-200 ${
                  active
                    ? 'border-indigo-500 shadow-md shadow-indigo-500/25 scale-[1.04]'
                    : 'border-slate-200 opacity-70 hover:opacity-100 hover:border-slate-300'
                }`}
                title={`Concept ${i + 1}`}
              >
                <img
                  src={resolveImageUrl(img.image_url)}
                  alt={`${activeGroup.roleLabel} concept ${i + 1} thumbnail`}
                  className="w-full h-full object-cover object-top"
                />
                <span className={`absolute bottom-0.5 right-1 text-[9px] font-bold rounded px-1 ${active ? 'bg-indigo-500 text-white' : 'bg-slate-900/60 text-white'}`}>
                  {i + 1}
                </span>
              </button>
            );
          })}
        </motion.div>
      )}

      {/* Fullscreen lightbox */}
      <AnimatePresence>
        {lightboxOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="fixed inset-0 z-[90] bg-slate-950/90 backdrop-blur-md flex flex-col"
            onClick={() => setLightboxOpen(false)}
          >
            <div className="shrink-0 flex items-center justify-between px-4 sm:px-6 py-3">
              <span className="text-sm font-semibold text-white/90">
                {activeGroup.roleLabel}
                <span className="ml-2 text-white/40 font-normal">
                  concept {activeVariant + 1} of {activeGroup.images.length}
                </span>
              </span>
              <button
                type="button"
                className="text-white/60 hover:text-white transition-colors"
                onClick={() => setLightboxOpen(false)}
                title="Close"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-6 h-6">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 min-h-0 flex items-center justify-center px-4 sm:px-10 pb-6" onClick={(e) => e.stopPropagation()}>
              <AnimatePresence mode="wait">
                <motion.img
                  key={`lb-${activeGroup.roleId}-${activeVariant}`}
                  src={resolveImageUrl(activeImage.image_url)}
                  alt={`${activeGroup.roleLabel} — fullscreen`}
                  initial={{ opacity: 0, scale: 0.97 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.3, ease }}
                  className="max-w-full max-h-full object-contain rounded-lg shadow-2xl"
                />
              </AnimatePresence>
            </div>
            {activeGroup.images.length > 1 && (
              <div className="shrink-0 flex items-center justify-center gap-2 pb-5" onClick={(e) => e.stopPropagation()}>
                {activeGroup.images.map((img, i) => (
                  <button
                    key={`lb-dot-${img.variant}`}
                    type="button"
                    onClick={() => setActiveVariant(i)}
                    className={`w-2.5 h-2.5 rounded-full transition-all ${i === activeVariant ? 'bg-white scale-110' : 'bg-white/30 hover:bg-white/60'}`}
                    title={`Concept ${i + 1}`}
                  />
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
