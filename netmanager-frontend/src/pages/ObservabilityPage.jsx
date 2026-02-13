import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';
import { Activity, RefreshCw, ExternalLink } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { DeviceService, IssueService, ObservabilityService } from '../api/services';
import { useAuth } from '../context/AuthContext';

const formatTime = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const formatRelativeTime = (iso) => {
  if (!iso) return '';
  const date = new Date(iso);
  const now = new Date();
  const diffInSeconds = Math.floor((now - date) / 1000);
  if (diffInSeconds < 60) return `${diffInSeconds}s ago`;
  if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
  if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
  return `${Math.floor(diffInSeconds / 86400)}d ago`;
};

const formatBps = (v) => {
  const n = Number(v || 0);
  if (!Number.isFinite(n)) return '0 bps';
  const units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
  let value = n;
  let idx = 0;
  while (value >= 1000 && idx < units.length - 1) {
    value /= 1000;
    idx += 1;
  }
  return `${value.toFixed(value >= 10 || idx === 0 ? 0 : 1)} ${units[idx]}`;
};

const StatCard = ({ title, value, sub }) => {
  return (
    <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-5">
      <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">{title}</div>
      <div className="mt-2 text-3xl font-black tracking-tight text-gray-900 dark:text-white">{value}</div>
      {sub ? <div className="mt-1 text-xs text-gray-500 dark:text-gray-300">{sub}</div> : null}
    </div>
  );
};

const ObservabilityPage = () => {
  const { isAtLeast } = useAuth();
  const canView = isAtLeast('operator');
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [summary, setSummary] = useState(null);
  const [devices, setDevices] = useState([]);
  const [sites, setSites] = useState([]);
  const [selectedSiteId, setSelectedSiteId] = useState('');
  const [filterText, setFilterText] = useState('');
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [timeseries, setTimeseries] = useState([]);
  const [interfaces, setInterfaces] = useState([]);
  const [selectedInterface, setSelectedInterface] = useState('');
  const [interfaceTimeseries, setInterfaceTimeseries] = useState([]);
  const [issues, setIssues] = useState([]);
  const [statusEvents, setStatusEvents] = useState([]);

  const pollingRef = useRef(null);
  const prevStatusRef = useRef(new Map());
  const statusRestoreDoneRef = useRef(false);

  const urls = useMemo(() => {
    return { grafanaHome: '/grafana/' };
  }, []);

  const sitesById = useMemo(() => {
    const map = new Map();
    for (const s of sites || []) {
      map.set(String(s.id), s);
    }
    return map;
  }, [sites]);

  const filteredDevices = useMemo(() => {
    const siteKey = String(selectedSiteId || '');
    const q = String(filterText || '').trim().toLowerCase();
    return (devices || []).filter((d) => {
      if (siteKey && String(d.site_id || '') !== siteKey) return false;
      if (!q) return true;
      const tags = Array.isArray(d.tags) ? d.tags : [];
      const hay = [d.name, d.ip, d.device_type, d.role, ...tags].map((v) => String(v || '').toLowerCase()).join(' ');
      return hay.includes(q);
    });
  }, [devices, selectedSiteId, filterText]);

  const filteredDeviceIdSet = useMemo(() => {
    return new Set(filteredDevices.map((d) => String(d.id)));
  }, [filteredDevices]);

  const filteredIssues = useMemo(() => {
    const list = Array.isArray(issues) ? issues : [];
    return list.filter((i) => {
      const did = i?.device_id;
      if (!selectedSiteId) return true;
      if (did == null) return false;
      return filteredDeviceIdSet.has(String(did));
    });
  }, [issues, selectedSiteId, filteredDeviceIdSet]);

  const sortedInterfaces = useMemo(() => {
    const list = Array.isArray(interfaces) ? interfaces : [];
    return [...list].sort((a, b) => {
      const av = Number(a?.traffic_in_bps || 0) + Number(a?.traffic_out_bps || 0);
      const bv = Number(b?.traffic_in_bps || 0) + Number(b?.traffic_out_bps || 0);
      return bv - av;
    });
  }, [interfaces]);

  const selectedDevice = useMemo(() => {
    return (devices || []).find((d) => String(d.id) === String(selectedDeviceId)) || null;
  }, [devices, selectedDeviceId]);

  const eventStats = useMemo(() => {
    const now = Date.now();
    const ttlMs = 6 * 60 * 60 * 1000;
    const flapWindowMs = 30 * 60 * 1000;
    const recentMs = 60 * 60 * 1000;
    const byFilter = (statusEvents || []).filter((e) => {
      const ts = Date.parse(e?.ts || '');
      if (!Number.isFinite(ts) || now - ts > ttlMs) return false;
      const did = e?.device_id;
      if (did == null) return false;
      if (!selectedSiteId && !filterText) return true;
      return filteredDeviceIdSet.has(String(did));
    });
    const sorted = [...byFilter].sort((a, b) => Date.parse(b?.ts || '') - Date.parse(a?.ts || ''));
    const recent = sorted.filter((e) => now - Date.parse(e.ts) <= recentMs).slice(0, 20);
    const inWindow = sorted.filter((e) => now - Date.parse(e.ts) <= flapWindowMs);

    const counts = new Map();
    for (const e of inWindow) {
      const did = String(e.device_id);
      const cur = counts.get(did) || { count: 0, lastTs: 0, name: e.name, ip: e.ip, site_id: e.site_id };
      cur.count += 1;
      const ts = Date.parse(e.ts);
      if (Number.isFinite(ts) && ts > cur.lastTs) cur.lastTs = ts;
      if (!cur.name && e.name) cur.name = e.name;
      if (!cur.ip && e.ip) cur.ip = e.ip;
      if (cur.site_id == null && e.site_id != null) cur.site_id = e.site_id;
      counts.set(did, cur);
    }
    const flappers = Array.from(counts.entries())
      .map(([deviceId, v]) => ({ deviceId, ...v }))
      .sort((a, b) => (b.count - a.count) || (b.lastTs - a.lastTs))
      .slice(0, 8);

    return { recent, flappers, ttlMs };
  }, [statusEvents, filteredDeviceIdSet, selectedSiteId, filterText]);
  
  const hotspots = useMemo(() => {
    const list = Array.isArray(filteredDevices) ? filteredDevices : [];
    const nowMs = Date.now();
    const topCpu = [...list]
      .sort((a, b) => Number(b?.cpu || 0) - Number(a?.cpu || 0))
      .slice(0, 5);
    const topMem = [...list]
      .sort((a, b) => Number(b?.memory || 0) - Number(a?.memory || 0))
      .slice(0, 5);
    const offlineLongest = list
      .filter((d) => String(d?.status || '').toLowerCase() !== 'online')
      .map((d) => {
        const t = Date.parse(d?.last_seen || '');
        const lastSeenMs = Number.isFinite(t) ? t : 0;
        return { ...d, _offlineMs: lastSeenMs ? Math.max(0, nowMs - lastSeenMs) : Number.POSITIVE_INFINITY };
      })
      .sort((a, b) => Number(b?._offlineMs || 0) - Number(a?._offlineMs || 0))
      .slice(0, 5);
    return { topCpu, topMem, offlineLongest };
  }, [filteredDevices]);

  const load = async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      setLoadError('');
      const [summaryRes, devicesRes, issuesRes] = await Promise.all([
        ObservabilityService.summary(),
        ObservabilityService.devices(),
        IssueService.getActiveIssues({ is_read: false }),
      ]);
      setSummary(summaryRes.data);
      setDevices(Array.isArray(devicesRes.data) ? devicesRes.data : []);
      setIssues(Array.isArray(issuesRes.data) ? issuesRes.data : []);

      const existingSelected = selectedDeviceId && (devicesRes.data || []).some((d) => String(d.id) === String(selectedDeviceId));
      if (!existingSelected) {
        const first = (devicesRes.data || [])[0];
        setSelectedDeviceId(first ? String(first.id) : '');
      }
    } catch (e) {
      console.error('Observability load failed:', e);
      const msg = e?.response?.data?.detail || e?.message || 'Failed to load observability';
      setLoadError(String(msg));
    } finally {
      if (isInitial) setLoading(false);
    }
  };

  const loadTimeseries = async (deviceId) => {
    if (!deviceId) {
      setTimeseries([]);
      return;
    }
    try {
      const res = await ObservabilityService.deviceTimeseries(deviceId, 360, 720);
      const points = (res.data && res.data.points) || [];
      setTimeseries(
        points.map((p) => ({
          time: formatTime(p.ts),
          cpu: p.cpu,
          memory: p.memory,
          in: p.traffic_in_bps,
          out: p.traffic_out_bps,
        }))
      );
    } catch (e) {
      console.error('Timeseries load failed:', e);
      setTimeseries([]);
    }
  };

  const loadInterfaces = async (deviceId) => {
    if (!deviceId) {
      setInterfaces([]);
      setSelectedInterface('');
      return;
    }
    try {
      const res = await ObservabilityService.deviceInterfaces(deviceId);
      const list = Array.isArray(res.data) ? res.data : [];
      setInterfaces(list);
      const exists = selectedInterface && list.some((x) => String(x.interface) === String(selectedInterface));
      if (!exists) {
        setSelectedInterface(list[0]?.interface || '');
      }
    } catch (e) {
      console.error('Interfaces load failed:', e);
      setInterfaces([]);
      setSelectedInterface('');
    }
  };

  const loadInterfaceTimeseries = async (deviceId, name) => {
    if (!deviceId || !name) {
      setInterfaceTimeseries([]);
      return;
    }
    try {
      const res = await ObservabilityService.interfaceTimeseries(deviceId, name, 360, 720);
      const points = (res.data && res.data.points) || [];
      setInterfaceTimeseries(
        points.map((p) => ({
          time: formatTime(p.ts),
          in: p.traffic_in_bps,
          out: p.traffic_out_bps,
          inErr: p.in_errors_per_sec,
          outErr: p.out_errors_per_sec,
          inDrop: p.in_discards_per_sec,
          outDrop: p.out_discards_per_sec,
          errors: Number(p.in_errors_per_sec || 0) + Number(p.out_errors_per_sec || 0),
          drops: Number(p.in_discards_per_sec || 0) + Number(p.out_discards_per_sec || 0),
        }))
      );
    } catch (e) {
      console.error('Interface timeseries load failed:', e);
      setInterfaceTimeseries([]);
    }
  };

  useEffect(() => {
    if (!canView) return;
    load(true);
    pollingRef.current = setInterval(() => load(false), 10000);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [canView]);

  useEffect(() => {
    if (statusRestoreDoneRef.current) return;
    try {
      const raw = sessionStorage.getItem('observability.statusEvents.v1');
      if (raw) {
        const now = Date.now();
        const ttlMs = 6 * 60 * 60 * 1000;
        const parsed = JSON.parse(raw);
        const next = Array.isArray(parsed)
          ? parsed.filter((e) => {
              const ts = Date.parse(e?.ts || '');
              return Number.isFinite(ts) && (now - ts) <= ttlMs;
            })
          : [];
        setStatusEvents(next);
      }
    } catch (e) {
      console.error(e);
    } finally {
      statusRestoreDoneRef.current = true;
    }
  }, []);

  useEffect(() => {
    if (!statusRestoreDoneRef.current) return;
    try {
      sessionStorage.setItem('observability.statusEvents.v1', JSON.stringify(statusEvents.slice(0, 500)));
    } catch (e) {
      console.error(e);
    }
  }, [statusEvents]);

  useEffect(() => {
    if (!canView) return;
    if (!Array.isArray(devices) || devices.length === 0) return;
    const normalizeStatus = (s) => {
      const v = String(s || '').toLowerCase().trim();
      return v === 'online' ? 'online' : 'offline';
    };
    const nowIso = new Date().toISOString();
    const prev = prevStatusRef.current;
    const nextMap = new Map();
    for (const d of devices) {
      const id = d?.id;
      if (id == null) continue;
      nextMap.set(String(id), { status: normalizeStatus(d.status), last_seen: d.last_seen || null, name: d.name, ip: d.ip, site_id: d.site_id });
    }
    if (prev.size === 0) {
      prevStatusRef.current = nextMap;
      return;
    }
    const newEvents = [];
    for (const [id, cur] of nextMap.entries()) {
      const p = prev.get(id);
      if (!p) continue;
      if (p.status !== cur.status) {
        newEvents.push({
          id: `${Date.now()}-${id}-${cur.status}`,
          ts: nowIso,
          device_id: Number.isFinite(Number(id)) ? Number(id) : id,
          name: cur.name || p.name,
          ip: cur.ip || p.ip,
          site_id: cur.site_id ?? p.site_id,
          from: p.status,
          to: cur.status,
        });
      }
    }
    prevStatusRef.current = nextMap;
    if (newEvents.length) {
      setStatusEvents((prevEvents) => [...newEvents, ...(Array.isArray(prevEvents) ? prevEvents : [])].slice(0, 500));
    }
  }, [canView, devices]);

  useEffect(() => {
    if (!canView) return;
    DeviceService.getSites()
      .then((res) => setSites(Array.isArray(res.data) ? res.data : []))
      .catch((e) => console.error('Failed to load sites:', e));
  }, [canView]);

  useEffect(() => {
    if (!canView) return;
    const exists = filteredDevices.some((d) => String(d.id) === String(selectedDeviceId));
    if (!exists) {
      const first = filteredDevices[0];
      setSelectedDeviceId(first ? String(first.id) : '');
    }
  }, [canView, filteredDevices, selectedDeviceId]);

  useEffect(() => {
    if (!canView) return;
    loadTimeseries(selectedDeviceId);
  }, [canView, selectedDeviceId]);

  useEffect(() => {
    if (!canView) return;
    loadInterfaces(selectedDeviceId);
  }, [canView, selectedDeviceId]);

  useEffect(() => {
    if (!canView) return;
    loadInterfaceTimeseries(selectedDeviceId, selectedInterface);
  }, [canView, selectedDeviceId, selectedInterface]);


  if (!canView) {
    return (
      <div className="p-6">
        <div className="max-w-3xl bg-white/90 dark:bg-[#1b1d1f]/90 border border-gray-200 dark:border-white/5 rounded-2xl p-6 shadow-sm">
          <div className="text-lg font-bold text-gray-900 dark:text-white">접근 권한이 없습니다</div>
          <div className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            Observability 화면은 Operator 이상만 접근할 수 있습니다.
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-transparent text-primary-glow font-mono">
        <RefreshCw className="animate-spin mr-2" /> Loading observability...
      </div>
    );
  }

  const globalCounts = summary?.counts || {};
  const filteredCounts = {
    devices: filteredDevices.length,
    online: filteredDevices.filter((d) => String(d.status || '').toLowerCase() === 'online').length,
    offline: filteredDevices.filter((d) => String(d.status || '').toLowerCase() !== 'online').length,
  };

  const severityBadge = (severity) => {
    const s = String(severity || '').toLowerCase();
    if (s === 'critical') return 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger';
    if (s === 'warning') return 'bg-amber-50 text-amber-800 dark:bg-warning/10 dark:text-warning';
    return 'bg-gray-100 text-gray-700 dark:bg-white/5 dark:text-gray-300';
  };

  const handleMarkRead = async (id) => {
    try {
      await IssueService.markAsRead(id);
      load(false);
    } catch (e) {
      console.error('markAsRead failed:', e);
    }
  };


  return (
    <div className="flex flex-col h-full gap-6 animate-fade-in text-gray-900 dark:text-white font-sans pb-6">
      <div className="flex justify-between items-end pb-4 border-b border-gray-200 dark:border-white/5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white/90">Observability</h1>
          </div>
          <p className="text-xs text-gray-500 pl-4">In-app device health & telemetry view</p>
        </div>
        <div className="flex gap-3 items-center flex-wrap justify-end">
          <div className="flex gap-2 items-center">
            <select
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 cursor-pointer transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20"
            >
              <option value="">All Sites</option>
              {sites.map((s) => (
                <option key={s.id} value={String(s.id)}>{s.name}</option>
              ))}
            </select>
            <input
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Search tags / name / ip"
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20 w-56"
            />
          </div>
          <a
            href={urls.grafanaHome}
            target="_blank"
            rel="noreferrer"
            className="px-3 py-2 bg-white dark:bg-white/5 hover:bg-gray-50 dark:hover:bg-white/10 rounded-lg text-xs font-bold text-gray-700 dark:text-gray-300 transition-colors border border-gray-200 dark:border-white/10 flex items-center gap-2"
          >
            Grafana <ExternalLink size={14} />
          </a>
          <button
            onClick={() => load(true)}
            className="p-2 bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors border border-transparent hover:border-gray-300 dark:hover:border-white/10"
          >
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard title="Devices" value={filteredCounts.devices} sub={`필터 결과 / 전체 ${globalCounts.devices || 0}`} />
        <StatCard title="Online" value={filteredCounts.online} sub={`필터 결과 / 전체 ${globalCounts.online || 0}`} />
        <StatCard title="Offline" value={filteredCounts.offline} sub={`필터 결과 / 전체 ${globalCounts.offline || 0}`} />
      </div>

      {loadError ? (
        <div className="bg-rose-50/80 dark:bg-danger/10 border border-rose-200 dark:border-white/10 rounded-2xl p-4 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-black text-rose-800 dark:text-danger">Observability 로드 실패</div>
            <div className="mt-1 text-xs text-rose-700 dark:text-gray-300 truncate">{loadError}</div>
          </div>
          <button
            onClick={() => load(true)}
            className="px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors"
          >
            Retry
          </button>
        </div>
      ) : null}

      {filteredDevices.length === 0 ? (
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
          <div className="text-sm font-black text-gray-900 dark:text-white">표시할 장비가 없습니다</div>
          <div className="mt-1 text-xs text-gray-600 dark:text-gray-300">사이트/검색 필터를 확인하세요.</div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider mb-4">Top CPU</div>
            <div className="space-y-2">
              {hotspots.topCpu.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDeviceId(String(d.id))}
                  className="w-full text-left flex items-center justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 hover:bg-gray-50 dark:hover:bg-white/5"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white truncate">{d.name}</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{d.ip}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-black text-gray-900 dark:text-white">{Number(d.cpu || 0).toFixed(0)}%</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400">{formatRelativeTime(d.last_seen) || '-'}</div>
                  </div>
                </button>
              ))}
              {hotspots.topCpu.length === 0 ? <div className="text-sm text-gray-500 dark:text-gray-400">-</div> : null}
            </div>
          </div>

          <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider mb-4">Top Memory</div>
            <div className="space-y-2">
              {hotspots.topMem.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDeviceId(String(d.id))}
                  className="w-full text-left flex items-center justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 hover:bg-gray-50 dark:hover:bg-white/5"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white truncate">{d.name}</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{d.ip}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-black text-gray-900 dark:text-white">{Number(d.memory || 0).toFixed(0)}%</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400">{formatRelativeTime(d.last_seen) || '-'}</div>
                  </div>
                </button>
              ))}
              {hotspots.topMem.length === 0 ? <div className="text-sm text-gray-500 dark:text-gray-400">-</div> : null}
            </div>
          </div>

          <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider mb-4">Offline Longest</div>
            <div className="space-y-2">
              {hotspots.offlineLongest.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setSelectedDeviceId(String(d.id))}
                  className="w-full text-left flex items-center justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 hover:bg-gray-50 dark:hover:bg-white/5"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white truncate">{d.name}</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{d.ip}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-black text-rose-700 dark:text-danger">offline</div>
                    <div className="text-[11px] text-gray-500 dark:text-gray-400">{formatRelativeTime(d.last_seen) || '-'}</div>
                  </div>
                </button>
              ))}
              {hotspots.offlineLongest.length === 0 ? <div className="text-sm text-gray-500 dark:text-gray-400">-</div> : null}
            </div>
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">최근 상태 변화</div>
          <div className="flex items-center gap-2">
            <div className="text-xs font-bold text-gray-600 dark:text-gray-300">
              {eventStats.recent.length} events / 1h · {eventStats.flappers.length} flappers / 30m
            </div>
            <button
              onClick={() => {
                setStatusEvents([]);
                try { sessionStorage.removeItem('observability.statusEvents.v1'); } catch (e) { console.error(e); }
              }}
              className="px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors"
            >
              Clear
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="overflow-auto rounded-xl border border-gray-200 dark:border-white/10">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 dark:bg-black/20 text-xs text-gray-600 dark:text-gray-300">
                <tr>
                  <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">Time</th>
                  <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">Device</th>
                  <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">Change</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200 dark:divide-white/10 bg-white dark:bg-transparent">
                {eventStats.recent.map((e) => (
                  <tr
                    key={e.id || `${e.ts}-${e.device_id}`}
                    className="cursor-pointer hover:bg-gray-50 dark:hover:bg-white/5"
                    onClick={() => setSelectedDeviceId(String(e.device_id))}
                  >
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap">{formatRelativeTime(e.ts) || '-'}</td>
                    <td className="px-3 py-2 min-w-0">
                      <div className="text-sm font-semibold text-gray-900 dark:text-white truncate">{e.name || `#${e.device_id}`}</div>
                      <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{e.ip || '-'}</div>
                    </td>
                    <td className="px-3 py-2">
                      <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold ${String(e.from) === 'online' ? 'bg-emerald-50 text-emerald-700 dark:bg-success/10 dark:text-success' : 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger'}`}>
                        {String(e.from || '').toLowerCase() === 'online' ? 'online' : 'offline'}
                      </span>
                      <span className="mx-2 text-gray-400">→</span>
                      <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold ${String(e.to) === 'online' ? 'bg-emerald-50 text-emerald-700 dark:bg-success/10 dark:text-success' : 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger'}`}>
                        {String(e.to || '').toLowerCase() === 'online' ? 'online' : 'offline'}
                      </span>
                    </td>
                  </tr>
                ))}
                {eventStats.recent.length === 0 ? (
                  <tr>
                    <td className="px-3 py-6 text-sm text-gray-500 dark:text-gray-400" colSpan={3}>
                      아직 변화 이벤트가 없습니다. (이 페이지는 폴링으로 상태 변화를 감지합니다)
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className="space-y-2">
            {eventStats.flappers.map((f) => (
              <button
                key={f.deviceId}
                onClick={() => setSelectedDeviceId(String(f.deviceId))}
                className="w-full text-left flex items-center justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20 hover:bg-gray-50 dark:hover:bg-white/5"
              >
                <div className="min-w-0">
                  <div className="text-sm font-black text-gray-900 dark:text-white truncate">{f.name || `#${f.deviceId}`}</div>
                  <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                    {f.ip || '-'} · {(sitesById.get(String(f.site_id || ''))?.name) || 'No Site'}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-black text-gray-900 dark:text-white">{f.count}</div>
                  <div className="text-[11px] text-gray-500 dark:text-gray-400">changes / 30m</div>
                </div>
              </button>
            ))}
            {eventStats.flappers.length === 0 ? (
              <div className="text-sm text-gray-500 dark:text-gray-400">최근 30분간 Flap이 감지되지 않았습니다.</div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Active Alerts (Unread)</div>
          <div className="text-xs font-bold text-gray-600 dark:text-gray-300">
            {filteredIssues.length}
          </div>
        </div>
        <div className="space-y-2">
          {filteredIssues.slice(0, 20).map((i) => (
            <div key={i.id} className="flex items-start justify-between gap-3 p-3 rounded-xl border border-gray-200 dark:border-white/10 bg-white/70 dark:bg-black/20">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded-full text-[11px] font-extrabold ${severityBadge(i.severity)}`}>
                    {String(i.severity || 'info').toUpperCase()}
                  </span>
                  <div className="text-sm font-black text-gray-900 dark:text-white truncate">{i.title}</div>
                </div>
                <div className="mt-1 text-xs text-gray-600 dark:text-gray-300 truncate">
                  {i.device} • {formatRelativeTime(i.created_at)}
                </div>
                {i.message ? (
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400 truncate">
                    {i.message}
                  </div>
                ) : null}
              </div>
              <button
                onClick={() => handleMarkRead(i.id)}
                className="px-3 py-2 rounded-xl text-xs font-extrabold bg-gray-900 text-white hover:bg-gray-800 transition-colors"
              >
                Read
              </button>
            </div>
          ))}
          {filteredIssues.length === 0 ? (
            <div className="text-sm text-gray-500 dark:text-gray-400">현재 읽지 않은 알람이 없습니다.</div>
          ) : null}
        </div>
      </div>

      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-blue-500 dark:text-primary" />
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Device Status Heatmap</div>
          </div>
          <div className="flex items-center gap-3 text-xs font-bold text-gray-600 dark:text-gray-300">
            <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-emerald-500"></span> Online</div>
            <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-rose-500"></span> Offline</div>
          </div>
        </div>
        <div className="grid gap-2" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
          {filteredDevices.map((d) => {
            const isOnline = String(d.status || '').toLowerCase() === 'online';
            const isSelected = String(d.id) === String(selectedDeviceId);
            const siteName = sitesById.get(String(d.site_id || ''))?.name;
            return (
              <button
                key={d.id}
                onClick={() => setSelectedDeviceId(String(d.id))}
                title={`${d.name} (${d.ip})\n${siteName || 'No Site'}\n${isOnline ? 'online' : 'offline'}\nLast seen: ${d.last_seen || ''}`}
                className={`text-left rounded-xl p-3 border transition-all ${isSelected ? 'border-blue-500/60 shadow-[0_0_15px_rgba(59,130,246,0.15)]' : 'border-gray-200 dark:border-white/10'} ${isOnline ? 'bg-emerald-50/80 dark:bg-success/10' : 'bg-rose-50/80 dark:bg-danger/10'}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-black truncate text-gray-900 dark:text-white">{d.name}</div>
                  <span className={`w-2.5 h-2.5 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-rose-500'}`}></span>
                </div>
                <div className="mt-1 text-[11px] font-bold text-gray-600 dark:text-gray-300 truncate">{d.ip}</div>
                <div className="mt-1 text-[10px] text-gray-500 dark:text-gray-400 truncate">{siteName || 'No Site'}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-blue-500 dark:text-primary" />
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Device Telemetry</div>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={selectedDeviceId}
              onChange={(e) => setSelectedDeviceId(e.target.value)}
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 cursor-pointer transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20"
            >
              {filteredDevices.map((d) => (
                <option key={d.id} value={String(d.id)}>
                  {d.name} ({d.ip})
                </option>
              ))}
            </select>
            <button
              disabled={!selectedDeviceId}
              onClick={() => selectedDeviceId && navigate(`/devices/${selectedDeviceId}`)}
              className={`px-3 py-2 rounded-lg text-xs font-extrabold transition-colors border ${
                !selectedDeviceId
                  ? 'bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-500 border-transparent cursor-not-allowed'
                  : 'bg-white text-gray-700 hover:bg-gray-50 dark:bg-white/5 dark:text-gray-300 dark:hover:bg-white/10 border-gray-200 dark:border-white/10'
              }`}
            >
              Open Device
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4 h-[320px]">
            <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
              Traffic (bps)
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeseries}>
                <defs>
                  <linearGradient id="obsIn" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="obsOut" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" vertical={false} />
                <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis
                  stroke="#64748b"
                  fontSize={10}
                  tickLine={false}
                  axisLine={false}
                  width={55}
                  tickFormatter={(v) => formatBps(v)}
                />
                <Tooltip
                  formatter={(v, name) => [formatBps(v), name === 'in' ? 'in' : 'out']}
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    color: '#fff',
                    borderRadius: '12px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                    backdropFilter: 'blur(8px)'
                  }}
                  itemStyle={{ fontSize: '12px', fontWeight: '500' }}
                  labelStyle={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '11px', textTransform: 'uppercase' }}
                />
                <Area type="monotone" dataKey="in" stroke="#3b82f6" strokeWidth={2.5} fill="url(#obsIn)" />
                <Area type="monotone" dataKey="out" stroke="#6366f1" strokeWidth={2.5} fill="url(#obsOut)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4 h-[320px]">
            <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
              CPU / Memory (%)
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeseries}>
                <defs>
                  <linearGradient id="obsCpu" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="obsMem" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" vertical={false} />
                <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} width={35} domain={[0, 100]} />
                <Tooltip
                  formatter={(v, name) => [`${Number(v || 0).toFixed(0)}%`, name === 'cpu' ? 'cpu' : 'memory']}
                  contentStyle={{
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    color: '#fff',
                    borderRadius: '12px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                    backdropFilter: 'blur(8px)'
                  }}
                  itemStyle={{ fontSize: '12px', fontWeight: '500' }}
                  labelStyle={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '11px', textTransform: 'uppercase' }}
                />
                <Area type="monotone" dataKey="cpu" stroke="#10b981" strokeWidth={2.5} fill="url(#obsCpu)" />
                <Area type="monotone" dataKey="memory" stroke="#f59e0b" strokeWidth={2.5} fill="url(#obsMem)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4">
            {selectedDevice ? (
              <>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-black text-gray-900 dark:text-white truncate">{selectedDevice.name || '-'}</div>
                    <div className="mt-1 text-xs text-gray-600 dark:text-gray-300 truncate">{selectedDevice.ip || '-'}</div>
                    <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400 truncate">
                      {(sitesById.get(String(selectedDevice.site_id || ''))?.name) || 'No Site'} · {selectedDevice.role || 'unknown'}
                    </div>
                  </div>
                  <span
                    className={`px-2 py-1 rounded-full text-[11px] font-extrabold ${
                      String(selectedDevice.status || '').toLowerCase() === 'online'
                        ? 'bg-emerald-50 text-emerald-700 dark:bg-success/10 dark:text-success'
                        : 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger'
                    }`}
                  >
                    {String(selectedDevice.status || '').toLowerCase() === 'online' ? 'online' : 'offline'}
                  </span>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
                    <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">CPU</div>
                    <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">{Number(selectedDevice.cpu || 0).toFixed(0)}%</div>
                  </div>
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
                    <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Memory</div>
                    <div className="mt-1 text-lg font-black text-gray-900 dark:text-white">{Number(selectedDevice.memory || 0).toFixed(0)}%</div>
                  </div>
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
                    <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">In</div>
                    <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{formatBps(selectedDevice.traffic_in_bps)}</div>
                  </div>
                  <div className="rounded-xl border border-gray-200 dark:border-white/10 p-3">
                    <div className="text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest">Out</div>
                    <div className="mt-1 text-sm font-black text-gray-900 dark:text-white">{formatBps(selectedDevice.traffic_out_bps)}</div>
                  </div>
                </div>

                <div className="mt-3 text-[11px] text-gray-500 dark:text-gray-400">
                  last seen: {formatRelativeTime(selectedDevice.last_seen) || '-'}
                </div>
              </>
            ) : (
              <div className="text-sm text-gray-500 dark:text-gray-400">선택된 장비가 없습니다.</div>
            )}
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3 mb-4">
          <div className="flex items-center gap-2">
            <Activity size={16} className="text-blue-500 dark:text-primary" />
            <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider">Interface Telemetry</div>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={selectedInterface}
              onChange={(e) => setSelectedInterface(e.target.value)}
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 focus:outline-none focus:border-primary/50 cursor-pointer transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20"
            >
              {sortedInterfaces.map((x) => (
                <option key={x.interface} value={x.interface}>
                  {x.interface}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          <div className="xl:col-span-2 grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4 h-[300px]">
              <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
                Interface Traffic (bps)
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={interfaceTimeseries}>
                  <defs>
                    <linearGradient id="ifIn" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="ifOut" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#6366f1" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" vertical={false} />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis
                    stroke="#64748b"
                    fontSize={10}
                    tickLine={false}
                    axisLine={false}
                    width={55}
                    tickFormatter={(v) => formatBps(v)}
                  />
                  <Tooltip
                    formatter={(v, name) => [formatBps(v), name === 'in' ? 'in' : 'out']}
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.9)',
                      borderColor: 'rgba(255,255,255,0.1)',
                      color: '#fff',
                      borderRadius: '12px',
                      boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                      backdropFilter: 'blur(8px)'
                    }}
                    itemStyle={{ fontSize: '12px', fontWeight: '500' }}
                    labelStyle={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '11px', textTransform: 'uppercase' }}
                  />
                  <Area type="monotone" dataKey="in" stroke="#3b82f6" strokeWidth={2.5} fill="url(#ifIn)" />
                  <Area type="monotone" dataKey="out" stroke="#6366f1" strokeWidth={2.5} fill="url(#ifOut)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>

            <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4 h-[300px]">
              <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
                Interface Errors / Drops (per sec)
              </div>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={interfaceTimeseries}>
                  <defs>
                    <linearGradient id="ifErr" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ef4444" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="ifDrop" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(148, 163, 184, 0.25)" vertical={false} />
                  <XAxis dataKey="time" stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} axisLine={false} width={45} />
                  <Tooltip
                    formatter={(v, name) => [Number(v || 0).toFixed(2), name]}
                    contentStyle={{
                      backgroundColor: 'rgba(15, 23, 42, 0.9)',
                      borderColor: 'rgba(255,255,255,0.1)',
                      color: '#fff',
                      borderRadius: '12px',
                      boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                      backdropFilter: 'blur(8px)'
                    }}
                    itemStyle={{ fontSize: '12px', fontWeight: '500' }}
                    labelStyle={{ color: '#94a3b8', marginBottom: '0.5rem', fontSize: '11px', textTransform: 'uppercase' }}
                  />
                  <Area
                    type="monotone"
                    dataKey="errors"
                    name="errors"
                    stroke="#ef4444"
                    strokeWidth={2.25}
                    fill="url(#ifErr)"
                  />
                  <Area
                    type="monotone"
                    dataKey="drops"
                    name="drops"
                    stroke="#f59e0b"
                    strokeWidth={2.25}
                    fill="url(#ifDrop)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="bg-white/80 dark:bg-black/20 border border-gray-200 dark:border-white/10 rounded-2xl p-4">
            <div className="text-xs font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3">
              Interfaces (top)
            </div>
            <div className="overflow-auto rounded-xl border border-gray-200 dark:border-white/10">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 dark:bg-black/20 text-xs text-gray-600 dark:text-gray-300">
                  <tr>
                    <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">Interface</th>
                    <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">In</th>
                    <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">Out</th>
                    <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">Err/s</th>
                    <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">Drop/s</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-white/10 bg-white dark:bg-transparent">
                  {sortedInterfaces.slice(0, 20).map((x) => {
                    const isSelected = String(x.interface) === String(selectedInterface);
                    const err = Number(x.in_errors_per_sec || 0) + Number(x.out_errors_per_sec || 0);
                    const drop = Number(x.in_discards_per_sec || 0) + Number(x.out_discards_per_sec || 0);
                    return (
                      <tr
                        key={x.interface}
                        className={`cursor-pointer hover:bg-gray-50 dark:hover:bg-white/5 ${isSelected ? 'bg-blue-50/60 dark:bg-blue-600/10' : ''}`}
                        onClick={() => setSelectedInterface(x.interface)}
                      >
                        <td className="px-3 py-2 font-semibold text-gray-900 dark:text-white">{x.interface}</td>
                        <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatBps(x.traffic_in_bps)}</td>
                        <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatBps(x.traffic_out_bps)}</td>
                        <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{err.toFixed(2)}</td>
                        <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{drop.toFixed(2)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6">
        <div className="text-sm font-bold text-gray-600 dark:text-gray-300 uppercase tracking-wider mb-4">
          Devices
        </div>
        <div className="overflow-auto rounded-xl border border-gray-200 dark:border-white/10">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-black/20 text-xs text-gray-600 dark:text-gray-300">
              <tr>
                <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">Name</th>
                <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">IP</th>
                <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">Site</th>
                <th className="text-left px-3 py-2 font-extrabold uppercase tracking-widest">Status</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">CPU</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">Mem</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">In</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">Out</th>
                <th className="text-right px-3 py-2 font-extrabold uppercase tracking-widest">Last Seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 dark:divide-white/10 bg-white dark:bg-transparent">
              {filteredDevices.map((d) => {
                const isOnline = String(d.status || '').toLowerCase() === 'online';
                const siteName = sitesById.get(String(d.site_id || ''))?.name;
                return (
                  <tr
                    key={d.id}
                    className="hover:bg-gray-50 dark:hover:bg-white/5 cursor-pointer"
                    onClick={() => setSelectedDeviceId(String(d.id))}
                  >
                    <td className="px-3 py-2 font-semibold text-gray-900 dark:text-white">{d.name}</td>
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{d.ip}</td>
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{siteName || '-'}</td>
                    <td className="px-3 py-2">
                      <span
                        className={`px-2 py-1 rounded-full text-xs font-bold ${
                          isOnline
                            ? 'bg-emerald-50 text-emerald-700 dark:bg-success/10 dark:text-success'
                            : 'bg-rose-50 text-rose-700 dark:bg-danger/10 dark:text-danger'
                        }`}
                      >
                        {isOnline ? 'online' : 'offline'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{Number(d.cpu || 0).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{Number(d.memory || 0).toFixed(0)}%</td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatBps(d.traffic_in_bps)}</td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatBps(d.traffic_out_bps)}</td>
                    <td className="px-3 py-2 text-right text-gray-700 dark:text-gray-300">{formatRelativeTime(d.last_seen)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default ObservabilityPage;
