"use client";

import { motion } from "framer-motion";
import { X } from "lucide-react";

interface DashboardModalProps {
  show: boolean;
  onClose: () => void;
  dashboardData: Record<string, any>;
  dashboardLoading: boolean;
}

export function DashboardModal({ show, onClose, dashboardData, dashboardLoading }: DashboardModalProps) {
  if (!show) return null;

  return (
    <>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50" onClick={onClose} />
      <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.95 }} className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-gray-900 border border-white/10 rounded-2xl w-[90vw] max-w-2xl max-h-[80vh] overflow-hidden z-50 flex flex-col">
        <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
          <h2 className="text-lg font-bold text-white">{"\ud83d\udcca \ucc44\ub110 \uc131\uacfc \ub300\uc2dc\ubcf4\ub4dc"}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X className="w-5 h-5" /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {dashboardLoading ? (
            <p className="text-gray-400 text-center py-8">{"\ub370\uc774\ud130 \uc218\uc9d1 \uc911..."}</p>
          ) : Object.keys(dashboardData).length === 0 ? (
            <p className="text-gray-500 text-center py-8">{"\uc5f0\uacb0\ub41c \ucc44\ub110\uc774 \uc5c6\uc2b5\ub2c8\ub2e4"}</p>
          ) : (
            Object.entries(dashboardData).map(([ch, data]: [string, any]) => {
              const s = data?.summary || {};
              const top5 = s.top_5 || [];
              return (
                <div key={ch} className="bg-white/5 border border-white/10 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <h3 className="text-white font-bold text-sm">{ch}</h3>
                    <span className="text-[10px] text-gray-500">{s.total_videos || 0}{"\uac1c \uc601\uc0c1"}</span>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                    <div className="bg-white/5 rounded-lg p-2 text-center">
                      <p className="text-[10px] text-gray-500">{"\ucd1d \uc870\ud68c"}</p>
                      <p className="text-white font-bold text-sm">{(s.total_views || 0).toLocaleString()}</p>
                    </div>
                    <div className="bg-white/5 rounded-lg p-2 text-center">
                      <p className="text-[10px] text-gray-500">{"\ud3c9\uade0 \uc870\ud68c"}</p>
                      <p className="text-white font-bold text-sm">{(s.avg_views || 0).toLocaleString()}</p>
                    </div>
                    <div className="bg-white/5 rounded-lg p-2 text-center">
                      <p className="text-[10px] text-gray-500">{"\ucd5c\uadfc 7\uc77c"}</p>
                      <p className="text-emerald-400 font-bold text-sm">{(s.recent_7d_views || 0).toLocaleString()}</p>
                    </div>
                  </div>
                  {top5.length > 0 && (
                    <div>
                      <p className="text-[10px] text-gray-500 mb-1">Top 5</p>
                      {top5.map((v: any, i: number) => (
                        <div key={i} className="flex items-center justify-between py-1 border-b border-white/5 last:border-0">
                          <span className="text-[11px] text-gray-300 truncate flex-1 mr-2">{i + 1}. {v.title}</span>
                          <span className="text-[11px] text-white font-medium whitespace-nowrap">{(v.views || 0).toLocaleString()}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </motion.div>
    </>
  );
}
