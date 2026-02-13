import React, { useMemo, useState } from 'react';
import { Activity, Play, RefreshCw } from 'lucide-react';
import { DiagnosisService } from '../api/services';
import { useToast } from '../context/ToastContext';

const JsonBlock = ({ value }) => {
  const text = useMemo(() => {
    try {
      return JSON.stringify(value ?? null, null, 2);
    } catch (e) {
      return String(value ?? '');
    }
  }, [value]);
  return (
    <pre className="text-xs whitespace-pre-wrap break-words bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-xl p-4 text-gray-800 dark:text-gray-200 max-h-[420px] overflow-auto">
      {text}
    </pre>
  );
};

const DiagnosisPage = () => {
  const { showToast } = useToast();
  const [srcIp, setSrcIp] = useState('');
  const [dstIp, setDstIp] = useState('');
  const [includeShow, setIncludeShow] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const canRun = String(srcIp).trim().length > 0 && String(dstIp).trim().length > 0 && !loading;

  const run = async () => {
    if (!canRun) return;
    setLoading(true);
    try {
      const res = await DiagnosisService.oneClick(String(srcIp).trim(), String(dstIp).trim(), includeShow);
      setResult(res.data);
      showToast('One-click diagnosis completed', 'success');
    } catch (e) {
      const msg = e?.response?.data?.detail?.message || e?.response?.data?.detail || e?.message || 'Diagnosis failed';
      showToast(String(msg), 'error');
    } finally {
      setLoading(false);
    }
  };

  const summary = result?.summary || null;
  const abnormal = Array.isArray(result?.abnormal) ? result.abnormal : [];
  const showBlocks = Array.isArray(result?.show) ? result.show : [];

  return (
    <div className="h-full w-full bg-[#f4f5f9] dark:bg-[#0e1012] p-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Activity className="text-indigo-500" />
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">One-Click Diagnosis</h1>
        </div>
        <button
          onClick={() => setResult(null)}
          className="flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold bg-white dark:bg-surface/40 border border-gray-200 dark:border-white/10 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-white/5"
        >
          <RefreshCw size={16} /> Reset
        </button>
      </div>

      <div className="mt-5 grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/10 shadow-sm rounded-2xl p-5 lg:col-span-1">
          <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Inputs</div>

          <div className="mt-4 space-y-3">
            <div>
              <div className="text-xs font-semibold text-gray-700 dark:text-gray-200">Source IP</div>
              <input
                value={srcIp}
                onChange={(e) => setSrcIp(e.target.value)}
                placeholder="e.g. 10.0.0.10"
                className="mt-1 w-full px-3 py-2 rounded-xl text-sm bg-white dark:bg-black/20 border border-gray-300 dark:border-white/10 text-gray-800 dark:text-gray-100 outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>
            <div>
              <div className="text-xs font-semibold text-gray-700 dark:text-gray-200">Destination IP</div>
              <input
                value={dstIp}
                onChange={(e) => setDstIp(e.target.value)}
                placeholder="e.g. 10.0.1.20"
                className="mt-1 w-full px-3 py-2 rounded-xl text-sm bg-white dark:bg-black/20 border border-gray-300 dark:border-white/10 text-gray-800 dark:text-gray-100 outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>

            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
              <input
                type="checkbox"
                checked={includeShow}
                onChange={(e) => setIncludeShow(e.target.checked)}
                className="rounded border-gray-300 dark:border-white/10"
              />
              Collect show commands on abnormal hops
            </label>

            <button
              onClick={run}
              disabled={!canRun}
              className={`w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-colors border ${
                canRun
                  ? 'bg-indigo-600 text-white border-indigo-600 hover:bg-indigo-700'
                  : 'bg-gray-200 dark:bg-white/10 text-gray-500 border-gray-200 dark:border-white/10 cursor-not-allowed'
              }`}
            >
              <Play size={16} />
              {loading ? 'Running…' : 'Run'}
            </button>
          </div>
        </div>

        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/10 shadow-sm rounded-2xl p-5 lg:col-span-2">
          <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Summary</div>
          <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500 dark:text-gray-400 font-bold">Mode</div>
              <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{summary?.mode || '-'}</div>
            </div>
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500 dark:text-gray-400 font-bold">Status</div>
              <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{summary?.status || '-'}</div>
            </div>
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500 dark:text-gray-400 font-bold">Abnormal</div>
              <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{Number(summary?.abnormal_count ?? 0)}</div>
            </div>
            <div className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
              <div className="text-[10px] uppercase tracking-widest text-gray-500 dark:text-gray-400 font-bold">Show</div>
              <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{Number(summary?.show_collected ?? 0)}</div>
            </div>
          </div>

          {abnormal.length > 0 ? (
            <div className="mt-4">
              <div className="text-xs font-bold text-gray-700 dark:text-gray-200">Abnormal hints</div>
              <div className="mt-2 space-y-2">
                {abnormal.slice(0, 8).map((a, idx) => (
                  <div key={idx} className="text-sm rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-50 dark:bg-amber-500/10 px-3 py-2 text-amber-900 dark:text-amber-200">
                    {String(a?.type || 'unknown')} · device_id={String(a?.device_id ?? '')}
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/10 shadow-sm rounded-2xl p-5">
          <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Device Health</div>
          <div className="mt-3">
            <JsonBlock value={result?.device_health || []} />
          </div>
        </div>
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/10 shadow-sm rounded-2xl p-5">
          <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Path Trace</div>
          <div className="mt-3">
            <JsonBlock value={result?.path_trace || null} />
          </div>
        </div>
      </div>

      {showBlocks.length > 0 ? (
        <div className="mt-4 bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/10 shadow-sm rounded-2xl p-5">
          <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Show Outputs</div>
          <div className="mt-3 space-y-3">
            {showBlocks.map((b) => (
              <details key={String(b.device_id)} className="rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-black/20 p-3">
                <summary className="cursor-pointer text-sm font-bold text-gray-800 dark:text-gray-100">
                  {b.device_name} ({b.device_ip}) · {Array.isArray(b.reasons) ? b.reasons.join(', ') : ''}
                </summary>
                <div className="mt-3">
                  <JsonBlock value={b.outputs || {}} />
                </div>
              </details>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
};

export default DiagnosisPage;

