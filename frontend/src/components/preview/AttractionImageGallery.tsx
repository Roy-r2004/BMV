import { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { API_BASE } from '../../api/client';
import type { AttractionImage } from '../../types/request';

const ease = [0.22, 1, 0.36, 1] as const;

interface Props {
  images: AttractionImage[];
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

export default function AttractionImageGallery({ images }: Props) {
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
    <div className="flex w-full flex-col gap-2">
      {/* Role switcher */}
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease }}
        className="shrink-0 flex items-center justify-center gap-1.5 flex-wrap px-2"
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

      {/* Main showcase — full width, natural (uncropped) height so nothing
          the hero graphic composed is ever cut off or hidden. */}
      <div className="relative w-full px-1 sm:px-2">
        <motion.div
          initial={{ opacity: 0, y: 20, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.6, ease }}
          className="relative w-full rounded-2xl overflow-hidden bg-slate-950 shadow-[0_30px_80px_-24px_rgba(15,23,42,0.5)] cursor-zoom-in"
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
              className="block w-full h-auto"
            />
          </AnimatePresence>

          {/* Caption badge */}
          <div className="absolute left-4 bottom-4 flex items-center gap-2 rounded-full bg-black/40 backdrop-blur-md border border-white/10 pl-3 pr-4 py-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span className="text-xs font-semibold text-white/90 tracking-wide">{activeGroup.roleLabel}</span>
          </div>

          {/* Expand icon */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setLightboxOpen(true);
            }}
            className="absolute right-4 top-4 flex items-center justify-center w-9 h-9 rounded-full bg-black/40 backdrop-blur-md border border-white/10 text-white/80 hover:text-white hover:bg-black/60 transition-colors"
            title="View fullscreen"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="w-4 h-4">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
            </svg>
          </button>
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
                  className="w-full h-full object-cover object-center"
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
