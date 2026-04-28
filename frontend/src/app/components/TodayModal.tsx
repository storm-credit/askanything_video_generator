"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { X } from "lucide-react";
import { API_BASE } from "../constants";

interface TodayModalProps {
  show: boolean;
  onClose: () => void;
  todayTopics: any[];
  todayFile: string;
  todayChannel: string | null;
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
  todayChannel,
  todayPrevDate, todayNextDate,
  setTodayTopics, setTodayFile, setTodayDate, setTodayPrevDate, setTodayNextDate,
  onSelectTopic,
}: TodayModalProps) {
  const [historySearch, setHistorySearch] = useState("");
  const [historyResults, setHistoryResults] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  if (!show) return null;

  const searchHistory = async () => {
    const query = historySearch.trim();
    if (!query) {
      setHistoryResults([]);
      return;
    }
    setHistoryLoading(true);
    try {
      const params = new URLSearchParams({ search: query, limit: "80" });
      if (todayChannel) params.set("channel", todayChannel);
      const res = await fetch(`${API_BASE}/api/batch/task-history?${params.toString()}`);
      const data = await res.json();
      setHistoryResults(data.success ? data.tasks || [] : []);
    } catch {
      setHistoryResults([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const navigateDate = async (date: string | null) => {
    if (!date) return;
    try {
      const params = new URLSearchParams({ date });
      if (todayChannel) params.set("channel", todayChannel);
      const res = await fetch(`${API_BASE}/api/batch/today-topics?${params.toString()}`);
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
        <div className="border-b border-white/10 p-4">
          <div className="flex gap-2">
            <input
              value={historySearch}
              onChange={(e) => setHistorySearch(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") searchHistory();
              }}
              placeholder={todayChannel ? `${todayChannel} 기록 검색` : "완료/실행 기록 검색"}
              className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
            />
            <button
              type="button"
              onClick={searchHistory}
              className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white hover:bg-emerald-500"
            >
              검색
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {historySearch.trim() && (
            <div className="mb-3 space-y-2">
              <p className="text-xs text-gray-500">
                {historyLoading ? "검색 중..." : `검색 결과 ${historyResults.length}개`}
              </p>
              {historyResults.map((item: any, i: number) => (
                <div key={`${item.task_date}-${item.topic_group}-${item.channel}-${i}`} className="rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-white">{item.title || item.topic_group}</p>
                    <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] text-emerald-300">{item.status}</span>
                  </div>
                  <p className="mt-1 text-xs text-gray-400">{item.task_date} · {item.channel}</p>
                  <p className="mt-1 text-[11px] text-gray-500">{item.topic_group}</p>
                </div>
              ))}
            </div>
          )}
          {!historySearch.trim() && todayTopics.map((t: any, i: number) => (
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
          {!historySearch.trim() && todayTopics.length === 0 && (
            <p className="text-gray-500 text-center py-8">{"\uc624\ub298 \uc8fc\uc81c\uac00 \uc5c6\uc2b5\ub2c8\ub2e4"}</p>
          )}
        </div>
      </motion.div>
    </>
  );
}
