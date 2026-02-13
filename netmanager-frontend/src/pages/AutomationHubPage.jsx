import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import ReactFlow, { Background, Controls, MiniMap, Panel, useEdgesState, useNodesState } from 'reactflow';
import 'reactflow/dist/style.css';
import { ExternalLink, Play, RefreshCw, Workflow, Scan, Activity, Zap, Shield, FileCheck, Blocks } from 'lucide-react';
import { DeviceService } from '../api/services';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

const hashToVariant = (key) => {
  const s = String(key || 'anonymous');
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) % 2 === 0 ? 'A' : 'B';
};

const makeNode = (type, position) => {
  const id = `${type}-${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  return {
    id,
    type: 'default',
    position,
    data: {
      label: type,
      stepType: type,
      configText: '{}',
    },
  };
};

const getWorkflowOrder = (nodes, edges) => {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const out = new Map();
  const inDeg = new Map();
  for (const n of nodes) {
    out.set(n.id, []);
    inDeg.set(n.id, 0);
  }
  for (const e of edges) {
    const s = String(e.source || '');
    const t = String(e.target || '');
    if (!byId.has(s) || !byId.has(t)) continue;
    out.get(s).push(t);
    inDeg.set(t, (inDeg.get(t) || 0) + 1);
  }
  const q = [];
  for (const [id, deg] of inDeg.entries()) {
    if (!deg) q.push(id);
  }
  const ordered = [];
  while (q.length) {
    q.sort((a, b) => {
      const ax = byId.get(a)?.position?.x ?? 0;
      const bx = byId.get(b)?.position?.x ?? 0;
      return ax - bx;
    });
    const id = q.shift();
    ordered.push(id);
    for (const nxt of out.get(id) || []) {
      inDeg.set(nxt, (inDeg.get(nxt) || 0) - 1);
      if (inDeg.get(nxt) === 0) q.push(nxt);
    }
  }
  if (ordered.length !== nodes.length) {
    return [...nodes].sort((a, b) => (a.position?.x ?? 0) - (b.position?.x ?? 0)).map((n) => n.id);
  }
  return ordered;
};

const safeJsonParse = (s, fallback = {}) => {
  try {
    const v = JSON.parse(String(s || ''));
    return v && typeof v === 'object' ? v : fallback;
  } catch (e) {
    return fallback;
  }
};

const endpointByStepType = (stepType) => {
  const t = String(stepType || '').toLowerCase();
  if (t === 'template') return 'template';
  if (t === 'fault-tolerance') return 'fault-tolerance';
  if (t === 'qos-autoscale') return 'qos-autoscale';
  if (t === 'acl-enforce') return 'acl-enforce';
  if (t === 'discovery') return 'discovery';
  return null;
};

const modulePalette = [
  { key: 'discovery', title: 'Auto Discovery', desc: '자동 장비 발견 및 등록 (Core)' },
  { key: 'template', title: 'Template Automation', desc: '5분 이내 템플릿 기반 자동화' },
  { key: 'fault-tolerance', title: 'Fault-Tolerance', desc: '30초 이내 자동 복구 오케스트레이션' },
  { key: 'qos-autoscale', title: 'QoS Autoscaling', desc: '대역폭 임계치 기반 확장/축소' },
  { key: 'acl-enforce', title: 'Auto ACL', desc: '보안 위반 즉시 차단 ACL 배포' },
];

const AutomationHubPage = () => {
  const { user, isAtLeast } = useAuth();
  const navigate = useNavigate();
  const canView = isAtLeast('operator');
  const [variant] = useState(() => {
    const existing = localStorage.getItem('ab.automationHub.variant');
    if (existing === 'A' || existing === 'B') return existing;
    const v = hashToVariant(user?.username || user?.full_name || user?.id);
    localStorage.setItem('ab.automationHub.variant', v);
    return v;
  });

  const [devices, setDevices] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [runLoading, setRunLoading] = useState(false);
  const [runLog, setRunLog] = useState('');
  const [usage, setUsage] = useState(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const [feedbackRating, setFeedbackRating] = useState(5);
  const [feedbackComment, setFeedbackComment] = useState('');
  const [feedbackSending, setFeedbackSending] = useState(false);
  const [viewMode, setViewMode] = useState('overview');

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const rfWrapperRef = useRef(null);

  const selectedNode = useMemo(() => {
    if (!selectedNodeId) return null;
    return nodes.find((n) => String(n.id) === String(selectedNodeId)) || null;
  }, [nodes, selectedNodeId]);

  const [discoveryStatus, setDiscoveryStatus] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [devRes, tplRes, polRes, discRes] = await Promise.all([
        DeviceService.getDevices(),
        DeviceService.getTemplates(),
        DeviceService.getPolicies?.() || Promise.resolve({ data: [] }),
        // Check latest discovery job if possible, or just mock status for now since no specific API for "latest status"
        // But we can fetch jobs to show something useful.
        // Assuming we can get some status or just skip if not critical.
        // Let's try to get discovery jobs if possible, or just use devices count as proxy.
        Promise.resolve({ status: 'idle' }) 
      ]);
      setDevices(Array.isArray(devRes.data) ? devRes.data : []);
      setTemplates(Array.isArray(tplRes.data) ? tplRes.data : []);
      setPolicies(Array.isArray(polRes.data) ? polRes.data : []);
      setDiscoveryStatus(discRes);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!canView) return;
    load();
  }, [canView, load]);

  useEffect(() => {
    if (!canView) return;
    try {
      const token = localStorage.getItem('authToken');
      fetch(`${API_BASE_URL}/automation-hub/track`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ event: 'view', variant }),
      });
    } catch (e) {
      console.error(e);
    }
  }, [canView, variant]);

  useEffect(() => {
    if (!canView) return;
    setUsageLoading(true);
    (async () => {
      try {
        const token = localStorage.getItem('authToken');
        const res = await fetch(`${API_BASE_URL}/automation-hub/usage?days=14`, {
          headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        });
        const json = await res.json().catch(() => ({}));
        setUsage(res.ok ? json : null);
      } finally {
        setUsageLoading(false);
      }
    })();
  }, [canView]);

  const submitFeedback = async () => {
    setFeedbackSending(true);
    try {
      const token = localStorage.getItem('authToken');
      await fetch(`${API_BASE_URL}/automation-hub/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({ rating: Number(feedbackRating || 0), comment: feedbackComment, variant }),
      });
      setFeedbackComment('');
    } finally {
      setFeedbackSending(false);
    }
  };

  const onDragStart = (evt, stepKey) => {
    evt.dataTransfer.setData('application/automation-step', stepKey);
    evt.dataTransfer.effectAllowed = 'move';
  };

  const onDrop = (evt) => {
    evt.preventDefault();
    const type = evt.dataTransfer.getData('application/automation-step');
    if (!type) return;
    const bounds = rfWrapperRef.current?.getBoundingClientRect();
    const x = evt.clientX - (bounds?.left || 0);
    const y = evt.clientY - (bounds?.top || 0);
    setNodes((nds) => [...nds, makeNode(type, { x, y })]);
  };

  const onDragOver = (evt) => {
    evt.preventDefault();
    evt.dataTransfer.dropEffect = 'move';
  };

  const updateSelectedNodeConfig = (patch) => {
    if (!selectedNodeId) return;
    setNodes((nds) =>
      nds.map((n) => {
        if (String(n.id) !== String(selectedNodeId)) return n;
        return { ...n, data: { ...n.data, ...patch } };
      })
    );
  };

  const runWorkflow = async () => {
    setRunLoading(true);
    setRunLog('');
    try {
      const orderedIds = getWorkflowOrder(nodes, edges);
      if (orderedIds.length === 0) {
        setRunLog('No steps.');
        return;
      }
      const results = [];
      for (const id of orderedIds) {
        const n = nodes.find((x) => String(x.id) === String(id));
        const stepType = n?.data?.stepType;
        const ep = endpointByStepType(stepType);
        if (!ep) {
          results.push({ step: stepType, ok: false, error: 'Unknown stepType' });
          continue;
        }
        const payload = safeJsonParse(n?.data?.configText, {});
        const token = localStorage.getItem('authToken');
        const res = await fetch(`${API_BASE_URL}/automation-hub/${ep}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify({ ...payload, meta: { variant } }),
        });
        const json = await res.json().catch(() => ({}));
        results.push({ step: stepType, status: res.status, body: json });
        if (!res.ok) break;
      }
      setRunLog(JSON.stringify(results, null, 2));
    } finally {
      setRunLoading(false);
    }
  };

  const moduleCards = [
    {
      key: 'discovery',
      title: 'Auto Discovery',
      desc: '네트워크 장비 자동 탐색 및 등록',
      icon: Scan,
      actionLabel: 'Open',
      onClick: () => navigate('/discovery'),
      meta: discoveryStatus?.status ? String(discoveryStatus.status).toUpperCase() : 'READY',
    },
    {
      key: 'visual-config',
      title: 'Visual Config',
      desc: '드래그 기반 구성 설계 및 배포',
      icon: Blocks,
      actionLabel: 'Open',
      onClick: () => navigate('/visual-config'),
    },
    {
      key: 'templates',
      title: 'Template Automation',
      desc: '템플릿 기반 즉시 자동화',
      icon: FileCheck,
      actionLabel: 'Open',
      onClick: () => navigate('/config'),
      meta: `${templates.length} Templates`,
    },
    {
      key: 'policy',
      title: 'Policy / ACL',
      desc: '보안 정책 자동 배포',
      icon: Shield,
      actionLabel: 'Open',
      onClick: () => navigate('/policy'),
      meta: `${policies.length} Policies`,
    },
    {
      key: 'qos',
      title: 'QoS Autoscaling',
      desc: '트래픽 임계치 기반 자동 스케일',
      icon: Zap,
      actionLabel: 'Open Builder',
      onClick: () => setViewMode('workflow'),
    },
    {
      key: 'fault',
      title: 'Fault-Tolerance',
      desc: '문제 발생 시 자동 복구 플로우',
      icon: Activity,
      actionLabel: 'Open Builder',
      onClick: () => setViewMode('workflow'),
    },
  ];

  if (!canView) {
    return (
      <div className="p-6">
        <div className="max-w-3xl bg-white/90 dark:bg-[#1b1d1f]/90 border border-gray-200 dark:border-white/5 rounded-2xl p-6 shadow-sm">
          <div className="text-lg font-bold text-gray-900 dark:text-white">접근 권한이 없습니다</div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">Automation Hub는 Operator 이상만 접근할 수 있습니다.</div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-transparent text-primary-glow font-mono">
        <RefreshCw className="animate-spin mr-2" /> Loading automation hub...
      </div>
    );
  }

  const insightsPanel = (
    <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
      <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Insights</div>
      <div className="mt-4 rounded-xl border border-gray-200 dark:border-white/10 p-3">
        <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Assets</div>
        <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">Devices: {devices.length}</div>
        <div className="text-[11px] text-gray-600 dark:text-gray-300">Templates: {templates.length}</div>
        <div className="text-[11px] text-gray-600 dark:text-gray-300">Policies: {policies.length}</div>
      </div>

      <div className="mt-4 rounded-xl border border-gray-200 dark:border-white/10 p-3">
        <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Usage (14d)</div>
        {usageLoading ? (
          <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">Loading...</div>
        ) : usage ? (
          <div className="mt-2 space-y-1 text-[11px] text-gray-600 dark:text-gray-300">
            <div>Views: {Number(usage.counts_by_action?.AUTO_HUB_VIEW || 0)}</div>
            <div>Template: {Number(usage.counts_by_action?.AUTO_HUB_TEMPLATE || 0)}</div>
            <div>Fault: {Number(usage.counts_by_action?.AUTO_HUB_FT || 0)}</div>
            <div>QoS: {Number(usage.counts_by_action?.AUTO_HUB_QOS || 0)}</div>
            <div>ACL: {Number(usage.counts_by_action?.AUTO_HUB_ACL || 0)}</div>
          </div>
        ) : (
          <div className="mt-2 text-[11px] text-gray-600 dark:text-gray-300">No data</div>
        )}
      </div>

      <div className="mt-4 rounded-xl border border-gray-200 dark:border-white/10 p-3">
        <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Feedback</div>
        <div className="mt-2 flex items-center gap-2">
          <select
            value={feedbackRating}
            onChange={(e) => setFeedbackRating(e.target.value)}
            className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-2 py-2 focus:outline-none focus:border-primary/50 cursor-pointer transition-all"
          >
            {[5, 4, 3, 2, 1].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <div className="text-[11px] text-gray-500 dark:text-gray-400">/ 5</div>
        </div>
        <textarea
          value={feedbackComment}
          onChange={(e) => setFeedbackComment(e.target.value)}
          className="mt-2 w-full h-20 bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 transition-all"
          placeholder="의견을 남겨주세요 (선택)"
        />
        <button
          onClick={submitFeedback}
          disabled={feedbackSending}
          className="mt-2 w-full px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors disabled:opacity-60"
        >
          Submit
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full gap-6 animate-fade-in text-gray-900 dark:text-white font-sans pb-6">
      <div className="flex justify-between items-end pb-4 border-b border-gray-200 dark:border-white/5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white/90 flex items-center gap-2">
              <Workflow size={20} /> Automation Hub
            </h1>
          </div>
          <p className="text-xs text-gray-500 pl-4">Enterprise automation modules · Variant {variant}</p>
        </div>
        <div className="flex gap-3 items-center flex-wrap justify-end">
          <div className="flex items-center gap-1 bg-white dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-lg p-1">
            <button
              type="button"
              onClick={() => setViewMode('overview')}
              className={`px-3 py-2 text-xs font-extrabold rounded-md transition-colors ${viewMode === 'overview' ? 'bg-gray-900 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10'}`}
            >
              Overview
            </button>
            <button
              type="button"
              onClick={() => setViewMode('workflow')}
              className={`px-3 py-2 text-xs font-extrabold rounded-md transition-colors ${viewMode === 'workflow' ? 'bg-gray-900 text-white' : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-white/10'}`}
            >
              Workflow
            </button>
          </div>
          <button
            type="button"
            onClick={() => navigate('/discovery')}
            className="hidden md:flex items-center gap-2 px-3 py-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-500/30 hover:bg-blue-100/70 dark:hover:bg-blue-900/30 transition-colors"
          >
            <Scan size={14} className="text-blue-600 dark:text-blue-400" />
            <div className="flex flex-col">
              <span className="text-[10px] font-bold text-blue-500 dark:text-blue-400 uppercase tracking-wider leading-none">Auto Discovery</span>
              <span className="text-xs font-black text-blue-700 dark:text-blue-200 leading-none mt-1">Ready ({devices.length} Devices)</span>
            </div>
          </button>
          <a
            href="/grafana/"
            target="_blank"
            rel="noreferrer"
            className="px-3 py-2 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg text-xs font-bold text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-white/10 flex items-center gap-2"
          >
            Grafana <ExternalLink size={14} />
          </a>
          <button
            onClick={load}
            className="p-2 bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors border border-transparent hover:border-gray-300 dark:hover:border-white/10"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {viewMode === 'overview' ? (
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
          <div className="xl:col-span-3 space-y-6">
            <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Automation Modules</div>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {moduleCards.map((m) => (
                  <div key={m.key} className="rounded-2xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 p-4 flex flex-col gap-3">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <m.icon size={16} className="text-blue-600 dark:text-blue-400" />
                        <div className="text-sm font-black text-gray-900 dark:text-white">{m.title}</div>
                      </div>
                      {m.meta ? (
                        <div className="text-[10px] font-extrabold text-blue-600 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 border border-blue-100 dark:border-blue-700/40 px-2 py-1 rounded-full">
                          {m.meta}
                        </div>
                      ) : null}
                    </div>
                    <div className="text-xs text-gray-600 dark:text-gray-300">{m.desc}</div>
                    <button
                      type="button"
                      onClick={m.onClick}
                      className="mt-auto px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors"
                    >
                      {m.actionLabel}
                    </button>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Workflow Builder</div>
              <div className="mt-3 flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setViewMode('workflow')}
                  className="px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors flex items-center gap-2"
                >
                  <Workflow size={14} /> Open Builder
                </button>
                <button
                  type="button"
                  onClick={() => navigate('/visual-config')}
                  className="px-3 py-2 rounded-xl text-xs font-extrabold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  Visual Config
                </button>
              </div>
            </div>
          </div>
          {insightsPanel}
        </div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-6">
          <div className="xl:col-span-3 bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl overflow-hidden">
            <div className="flex items-center justify-between gap-3 p-4 border-b border-gray-200 dark:border-white/10">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Workflow Builder</div>
              <div className="flex items-center gap-2">
                <button
                  onClick={runWorkflow}
                  disabled={runLoading}
                  className="px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors disabled:opacity-60 flex items-center gap-2"
                >
                  <Play size={14} /> Run
                </button>
                <button
                  onClick={() => { setNodes([]); setEdges([]); setSelectedNodeId(null); setRunLog(''); }}
                  className="px-3 py-2 rounded-xl text-xs font-extrabold bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 transition-colors border border-gray-200 dark:border-white/10"
                >
                  Reset
                </button>
              </div>
            </div>

            <div className="h-[520px]" ref={rfWrapperRef}>
              <ReactFlow
                nodes={nodes}
                edges={edges}
                onNodesChange={onNodesChange}
                onEdgesChange={onEdgesChange}
                onConnect={(c) => setEdges((eds) => [...eds, { ...c, id: `${c.source}-${c.target}-${Date.now()}` }])}
                onNodeClick={(_, n) => setSelectedNodeId(n.id)}
                onDrop={onDrop}
                onDragOver={onDragOver}
                fitView
                className="bg-gray-50 dark:bg-[#0e1012]"
              >
                <MiniMap nodeColor="#aaa" maskColor="rgba(0,0,0,0.1)" />
                <Controls />
                <Background color="#ccc" gap={20} size={1} />
                <Panel position="top-left" className="m-3 bg-white/90 dark:bg-[#1b1d1f]/90 border border-gray-200 dark:border-white/10 rounded-xl p-3 w-64">
                  <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">Palette</div>
                  <div className="space-y-2">
                    {modulePalette.map((m) => (
                      <div
                        key={m.key}
                        draggable
                        onDragStart={(e) => onDragStart(e, m.key)}
                        className="cursor-move select-none rounded-xl border border-gray-200 dark:border-white/10 bg-white dark:bg-black/20 p-3 hover:bg-gray-50 dark:hover:bg-white/5"
                      >
                        <div className="text-sm font-black text-gray-900 dark:text-white">{m.title}</div>
                        <div className="mt-1 text-[11px] text-gray-600 dark:text-gray-300">{m.desc}</div>
                      </div>
                    ))}
                  </div>
                </Panel>
              </ReactFlow>
            </div>

            {runLog ? (
              <div className="border-t border-gray-200 dark:border-white/10 p-4">
                <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-2">Run Log</div>
                <pre className="text-xs bg-black/90 text-white rounded-xl p-3 overflow-auto max-h-56">{runLog}</pre>
              </div>
            ) : null}
          </div>

          <div className="space-y-4">
            <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
              <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Step Config</div>
              {selectedNode ? (
                <>
                  <div className="mt-3 text-xs text-gray-600 dark:text-gray-300">Type</div>
                  <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{selectedNode.data?.stepType}</div>
                  <div className="mt-4 text-xs text-gray-600 dark:text-gray-300">Config JSON</div>
                  <textarea
                    value={selectedNode.data?.configText || ''}
                    onChange={(e) => updateSelectedNodeConfig({ configText: e.target.value })}
                    className="mt-2 w-full h-48 bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 transition-all"
                    placeholder='{"example":"value"}'
                  />
                  <div className="mt-3 text-[11px] text-gray-500 dark:text-gray-400">
                    Available: discovery | template | fault-tolerance | qos-autoscale | acl-enforce
                  </div>
                  <div className="mt-4 text-[11px] text-gray-500 dark:text-gray-400">
                    Hints: use device_ids (array), template_id/policy_id, variables (object), threshold_bps/current_bps.
                  </div>
                </>
              ) : (
                <div className="mt-3 text-sm text-gray-500 dark:text-gray-400">노드를 선택하거나 팔레트에서 추가하세요.</div>
              )}
            </div>
            {insightsPanel}
          </div>
        </div>
      )}
    </div>
  );
};

export default AutomationHubPage;
