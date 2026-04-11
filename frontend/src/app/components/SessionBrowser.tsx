"use client";

import { useState } from "react";
import { motion } from "framer-motion";

interface SessionBrowserProps {
  show: boolean;
  onClose: () => void;
  savedSessions: Array<{ folder: string; title: string; cuts_count: number; image_count: number; has_video: boolean; channel: string; language: string; created_at: string }>;
  onRestore: (folders: string[]) => void;
}

export function SessionBrowser({ show, onClose, savedSessions, onRestore }: SessionBrowserProps) {
  const [selectedFolders, setSelectedFolders] = useState<Set<string>>(new Set());

  if (!show) return null;

  const toggleFolder = (folder: string) => {
    setSelectedFolders(prev => {
      const next = new Set(prev);
      if (next.has(folder)) next.delete(folder); else next.add(folder);
      return next;
    });
  };

  const toggleAll = (folders: string[]) => {
    setSelectedFolders(prev => {
      const next = new Set(prev);
      const allSelected = folders.every(f => next.has(f));
      if (allSelected) folders.forEach(f => next.delete(f));
      else folders.forEach(f => next.add(f));
      return next;
    });
  };

  const grouped: Record<string, typeof savedSessions> = {};
  for (const s of savedSessions) {
    const base = s.folder.replace(/_(askanything|wonderdrop|exploratodo|prismtale)$/, "");
    if (!grouped[base]) grouped[base] = [];
    grouped[base].push(s);
  }
  const groups = Object.entries(grouped);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 pointer-events-auto"
      onMouseDown={onClose}
    >
      <motion.div
        initial={{ scale: 0.95 }}
        animate={{ scale: 1 }}
        exit={{ scale: 0.95 }}
        className="relative bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-lg max-h-[70vh] flex flex-col pointer-events-auto"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex justify-between items-center p-4 border-b border-gray-800">
          <h2 className="text-lg font-bold">{"\uc774\uc804 \uc138\uc158 \ubd88\ub7ec\uc624\uae30"}</h2>
          <div className="flex items-center gap-2">
            {selectedFolders.size > 0 && (
              <button
                onClick={() => onRestore(Array.from(selectedFolders))}
                className="text-sm px-3 py-1 rounded-lg bg-indigo-600 hover:bg-indigo-500 font-medium"
              >
                {"\ubd88\ub7ec\uc624\uae30"} ({selectedFolders.size})
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-white text-xl">&times;</button>
          </div>
        </div>
        <div className="overflow-y-auto p-4 space-y-2 flex-1">
          {groups.length === 0 ? (
            <p className="text-gray-500 text-center py-8">{"\uc800\uc7a5\ub41c \uc138\uc158\uc774 \uc5c6\uc2b5\ub2c8\ub2e4"}</p>
          ) : (
            groups.slice(0, 50).map(([base, items]) => (
              <div key={base} className="rounded-xl bg-gray-800 border border-gray-700 p-3">
                <div className="font-medium text-sm truncate mb-2">{items[0].title.replace(/_/g, " ")}</div>
                <div className="flex flex-wrap gap-1">
                  {items.map(s => (
                    <button
                      key={s.folder}
                      onClick={() => toggleFolder(s.folder)}
                      className={`text-xs px-2 py-1 rounded transition-colors cursor-pointer ${selectedFolders.has(s.folder) ? "bg-indigo-600 text-white" : "bg-gray-700 hover:bg-gray-600"}`}
                    >
                      {s.channel || "default"} ({s.image_count}{"\uc7a5"}{s.has_video ? " \u2713" : ""})
                    </button>
                  ))}
                  {items.length > 1 && (
                    <button
                      onClick={() => toggleAll(items.map(s => s.folder))}
                      className={`text-xs px-2 py-1 rounded font-medium transition-colors cursor-pointer ${items.every(s => selectedFolders.has(s.folder)) ? "bg-indigo-500 text-white" : "bg-gray-600 hover:bg-gray-500"}`}
                    >
                      {"\uc804\uccb4"} ({items.length})
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </motion.div>
    </motion.div>
  );
}
