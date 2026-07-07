import { useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { IconClose, IconFilm, IconUpload } from './icons/SubmitIcons';

interface Props {
  onFileSelect: (file: File | null) => void;
}

export default function FileUpload({ onFileSelect }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const applyFile = (file: File | null) => {
    onFileSelect(file);
    if (file) {
      setFileName(file.name);
      if (file.type.startsWith('image/')) {
        const reader = new FileReader();
        reader.onload = () => setPreview(reader.result as string);
        reader.readAsDataURL(file);
      } else {
        setPreview(null);
      }
    } else {
      setPreview(null);
      setFileName(null);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    applyFile(e.target.files?.[0] || null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    applyFile(e.dataTransfer.files[0] || null);
  };

  const clear = (e: React.MouseEvent) => {
    e.stopPropagation();
    applyFile(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <div>
      <motion.div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        whileHover={{ scale: 1.008 }}
        className={`relative border-2 border-dashed rounded-2xl p-6 sm:p-8 text-center cursor-pointer transition-all duration-300 overflow-hidden group ${
          dragging
            ? 'border-cyan-400 bg-cyan-50/90 scale-[1.01] shadow-lg shadow-cyan-500/10'
            : preview || fileName
              ? 'border-blue-300/80 bg-blue-50/50'
              : 'border-slate-200/90 bg-gradient-to-br from-slate-50/80 to-blue-50/30 hover:border-blue-400/60 hover:bg-blue-50/40 hover:shadow-lg hover:shadow-blue-500/5'
        }`}
      >
        <div className="absolute inset-0 cinematic-grid opacity-[0.04] pointer-events-none group-hover:opacity-[0.07] transition-opacity" />

        {preview ? (
          <div className="relative inline-block">
            <img src={preview} alt="Preview" className="max-h-40 mx-auto rounded-xl shadow-xl ring-2 ring-blue-200/80" />
            <button
              type="button"
              onClick={clear}
              className="absolute -top-2 -right-2 w-7 h-7 rounded-full bg-white border border-slate-200 text-slate-500 hover:text-red-500 hover:border-red-200 flex items-center justify-center shadow-md transition-colors"
              aria-label="Remove file"
            >
              <IconClose />
            </button>
          </div>
        ) : fileName ? (
          <div className="py-4 relative">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white flex items-center justify-center mx-auto mb-3 shadow-lg shadow-blue-500/25">
              <IconFilm className="w-6 h-6" />
            </div>
            <p className="text-sm font-semibold text-navy">{fileName}</p>
            <button type="button" onClick={clear} className="text-xs text-blue-600 mt-2 hover:underline font-medium">
              Remove file
            </button>
          </div>
        ) : (
          <div className="relative">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-blue-600 to-cyan-500 text-white flex items-center justify-center mx-auto mb-4 shadow-lg shadow-blue-500/25 group-hover:scale-105 transition-transform duration-300">
              <IconUpload className="w-6 h-6" />
            </div>
            <p className="text-sm font-semibold text-navy">
              Drop a screenshot or video here
            </p>
            <p className="text-xs text-slate-500 mt-1.5">or click to browse · PNG, JPG, GIF, MP4, WebM</p>
          </div>
        )}
      </motion.div>
      <input ref={inputRef} type="file" accept="image/*,video/*" className="hidden" onChange={handleChange} />
    </div>
  );
}
