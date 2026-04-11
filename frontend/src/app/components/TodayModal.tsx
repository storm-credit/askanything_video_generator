"use client";

import { motion } from "framer-motion";
import { X } from "lucide-react";
import { API_BASE } from "../constants";

interface TodayModalProps {
  show: boolean;
  onClose: () => void;
  todayTopics: any[];
  todayFile: string;
  todayDate: string | null;
  todayPrevDate: string | null;
  todayNextDate: string | null;
  setTodayTopics: (t: any[]) => void;
  setTodayFile: (f: string) => void;
  setTodayDate: (d: string | null) => void;
  setTodayPrevDate: (d: string | null) => void;
  setTodayNextDate: (d: string | null) => void;
  onSelectTopic: (topic: any) => void;
}

export function TodayModal({
  show, onClose, todayTopics, todayFile,
  todayPrevDate, todayNextDate,
  setTodayTopics, setTodayFile, setTodayDate, setTodayPrevDate, setTodayNextDate,
  onSelectTopic,
}: TodayModalProps) {
  if (!show) return null;

  const navigateDate = async (date: string | null) => {
    if (!date) return;
    try {
      const res = await fetch(`${API_BASE}/api/batch/today-topics?date=${date}`);
      const data = await res.json();
      if (data.success) {
        setTodayTopics(data.topics);
        setTodayFile(data.file || "");
        setTodayDate(data.current_date || null);
        setTodayPrevDate(data.prev_date || null);
        setTodayNextDate(data.next_date || null);
      }
    } catch {}
  };

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
        onClick={onClose}
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-gray-900 border border-white/10 rounded-2xl w-[90vw] max-w-md max-h-[60vh] overflow-hidden z-50 flex flex-col"
      >
        <div className="px-5 py-4 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigateDate(todayPrevDate)}
              disabled={!todayPrevDate}
              className={`text-lg font-bold ${todayPrevDate ? 'text-white hover:text-emerald-400 cursor-pointer' : 'text-gray-600 cursor-not-allowed'}`}
            >{"\u2039"}</button>
            <h2 className="text-lg font-bold text-white">{"\ud83d\udccb"} {todayFile?.replace('.md', '')}</h2>
            <button
              onClick={() => navigateDate(todayNextDate)}
              disabled={!todayNextDate}
              className={`text-lg font-bold ${todayNextDate ? 'text-white hover:text-emerald-400 cursor-pointer' : 'text-gray-600 cursor-not-allowed'}`}
            >{"\u203a"}</button>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {todayTopics.map((t: any, i: number) => (
            <button
              key={i}
              type="button"
              onClick={() => onSelectTopic(t)}
              className={`w-full text-left px-4 py-3 rounded-xl border transition-colors ${t.is_completed ? 'bg-emerald-500/10 border-emerald-500/30 opacity-60' : 'bg-white/5 border-white/10 hover:bg-emerald-500/10 hover:border-emerald-500/30'}`}
            >
              <div className="flex items-center gap-2">
                {t.is_completed && <span className="text-emerald-400 text-sm">{"\u2713"}</span>}
                <p className={`font-medium text-sm ${t.is_completed ? 'text-gray-400 line-through' : 'text-white'}`}>{t.topic_group}</p>
              </div>
              <div className="flex gap-2 mt-1.5 flex-wrap">
                {Object.entries(t.channels || {}).map(([ch, data]: [string, any]) => {
                  const done = (t.completed_channels || []).includes(ch);
                  return (
                    <span key={ch} className={`text-[10px] px-2 py-0.5 rounded-full ${done ? 'bg-emerald-500/20 text-emerald-400' : 'bg-white/10 text-gray-400'}`}>
                      {done ? '\u2713 ' : ''}{ch}
                    </span>
                  );
                })}
              </div>
            </button>
          ))}
          {todayTopics.length === 0 && (
            <p className="text-gray-500 text-center py-8">{"\uc624\ub298 \uc8fc\uc81c\uac00 \uc5c6\uc2b5\ub2c8\ub2e4"}</p>
          )}
        </div>
      </motion.div>
    </>
  );
}
