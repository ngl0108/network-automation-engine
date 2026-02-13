import React, { useCallback, useEffect, useState, useRef } from 'react';
import ReactFlow, {
  useNodesState,
  useEdgesState,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  Panel,
  useReactFlow
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useNavigate } from 'react-router-dom';
import { DeviceService, DiscoveryService, SDNService, TopologyService, TrafficService } from '../../api/services';
import { getElkLayoutedElements } from '../../utils/elkLayout';
import { RefreshCw, Server, AlertCircle, Network, Info, Map as MapIcon, Route, Play, Pause, XCircle, Shield, Wifi, Box, Layers, Globe, Activity, Save, LayoutTemplate, Download, Upload, Link2, CheckCircle, ChevronDown, ChevronRight } from 'lucide-react';
import GroupNode from './GroupNode';
import { useToast } from '../../context/ToastContext';

const nodeTypes = { groupNode: GroupNode };

const formatBps = (bps) => {
  const v = Number(bps || 0);
  if (!Number.isFinite(v) || v <= 0) return '0 bps';
  const units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
  let n = v;
  let i = 0;
  while (n >= 1000 && i < units.length - 1) {
    n /= 1000;
    i += 1;
  }
  const fixed = n >= 100 ? 0 : n >= 10 ? 1 : 2;
  return `${n.toFixed(fixed)} ${units[i]}`;
};

const clamp01 = (x) => Math.max(0, Math.min(1, x));

const truncateLabel = (text, maxLen) => {
  const s = String(text ?? '');
  const n = Number(maxLen ?? 42);
  if (!Number.isFinite(n) || n < 8) return s;
  if (s.length <= n) return s;
  return `${s.slice(0, Math.max(1, n - 1))}…`;
};

const buildEvidenceParts = (node) => {
  const evidence = node?.evidence && typeof node.evidence === 'object' ? node.evidence : {};
  const summary = [];
  const details = [];

  if (evidence.type === 'route_lookup') {
    if (evidence.protocol) summary.push(String(evidence.protocol).toUpperCase());
    if (evidence.vrf) summary.push(`VRF:${evidence.vrf}`);
    if (evidence.next_hop_ip) summary.push(`NH:${evidence.next_hop_ip}`);
    if (evidence.outgoing_interface) summary.push(`OUT:${evidence.outgoing_interface}`);

    if (evidence.protocol) details.push(`프로토콜: ${String(evidence.protocol).toUpperCase()}`);
    if (evidence.vrf) details.push(`VRF: ${evidence.vrf}`);
    if (evidence.next_hop_ip) details.push(`Next-hop IP: ${evidence.next_hop_ip}`);
    if (evidence.outgoing_interface) details.push(`Outgoing IF: ${evidence.outgoing_interface}`);
    if (evidence.arp && typeof evidence.arp === 'object') {
      if (evidence.arp.ip) details.push(`ARP IP: ${evidence.arp.ip}`);
      if (evidence.arp.mac) details.push(`ARP MAC: ${evidence.arp.mac}`);
      if (evidence.arp.interface) details.push(`ARP IF: ${evidence.arp.interface}`);
    }
    if (evidence.mac && typeof evidence.mac === 'object') {
      if (evidence.mac.mac) details.push(`MAC: ${evidence.mac.mac}`);
      if (evidence.mac.port) details.push(`MAC Port: ${evidence.mac.port}`);
      if (evidence.mac.vlan) details.push(`MAC VLAN: ${evidence.mac.vlan}`);
    }
  }

  if (evidence.type === 'l2_mac_trace') {
    if (evidence.learned_port) summary.push(`MAC:${evidence.learned_port}`);
    if (evidence.mac) summary.push(String(evidence.mac).toLowerCase());
    if (evidence.mac) details.push(`MAC: ${String(evidence.mac).toLowerCase()}`);
    if (evidence.learned_port) details.push(`Learned Port: ${evidence.learned_port}`);
  }

  if (evidence.l2_extend && typeof evidence.l2_extend === 'object') {
    if (evidence.l2_extend.host_ip) summary.push(`HOST:${evidence.l2_extend.host_ip}`);
    if (evidence.l2_extend.first_port) summary.push(`PORT:${evidence.l2_extend.first_port}`);
    if (evidence.l2_extend.host_ip) details.push(`호스트: ${evidence.l2_extend.host_ip}`);
    if (evidence.l2_extend.first_port) details.push(`첫 포트: ${evidence.l2_extend.first_port}`);
  }

  return {
    summaryText: summary.join(' · '),
    detailLines: details,
  };
};

// 2. 링크 통합 (Aggregation) 함수
// --------------------------------------------------------------------------
const aggregateLinks = (links, pathResult, opts) => {
  const linkMap = new Map();
  const maxEdgeLabelLen = Number.isFinite(Number(opts?.maxEdgeLabelLen)) ? Number(opts.maxEdgeLabelLen) : 42;
  const pathBadgesEnabled = opts?.pathBadgesEnabled !== false;
  const labelTruncateMode = String(opts?.labelTruncateMode || 'all');

  // Create a Set of edges in the path for fast lookup
  const pathEdgeKeys = new Set();
  const pathEdgeDir = new Map();
  if (pathResult?.path?.length > 1) {
    for (let i = 0; i < pathResult.path.length - 1; i++) {
      const fromId = String(pathResult.path[i].id);
      const toId = String(pathResult.path[i + 1].id);
      const sorted = [fromId, toId].sort().join('-');
      pathEdgeKeys.add(sorted);
      if (!pathEdgeDir.has(sorted)) {
        pathEdgeDir.set(sorted, {
          fromId,
          toId,
          hopIndex: i,
          fromPort: pathResult.path[i]?.egress_intf,
          toPort: pathResult.path[i + 1]?.ingress_intf
        });
      }
    }
  }

  const activeHopIndex = Number.isFinite(Number(opts?.pathPlayback?.activeEdgeIndex))
    ? Number(opts.pathPlayback.activeEdgeIndex)
    : null;

  links.forEach((link) => {
    const proto = (link.protocol || 'LLDP').toUpperCase();
    const sortedIds = [String(link.source), String(link.target)].sort();
    // Use protocol in key to keep L2 and L3 links separate
    const key = `${sortedIds[0]}-${sortedIds[1]}-${proto}`;
    const portInfo = `${link.src_port || '?'} ↔ ${link.dst_port || '?'}`;

    let trafficFwd = 0;
    let trafficRev = 0;
    if (opts?.trafficFlowEnabled) {
      const t = link?.traffic;
      const f = Number(t?.fwd_bps || 0);
      const r = Number(t?.rev_bps || 0);
      if (Number.isFinite(f) || Number.isFinite(r)) {
        trafficFwd = Math.max(0, Number.isFinite(f) ? f : 0);
        trafficRev = Math.max(0, Number.isFinite(r) ? r : 0);
      } else if (opts?.nodeTrafficById) {
        const src = opts.nodeTrafficById.get(String(link.source)) || {};
        const dst = opts.nodeTrafficById.get(String(link.target)) || {};
        const srcIn = Number(src.in_bps || 0);
        const srcOut = Number(src.out_bps || 0);
        const dstIn = Number(dst.in_bps || 0);
        const dstOut = Number(dst.out_bps || 0);
        trafficFwd = Math.max(0, Math.min(srcOut, dstIn));
        trafficRev = Math.max(0, Math.min(dstOut, srcIn));
      }
    }

    if (!linkMap.has(key)) {
      linkMap.set(key, {
        source: String(link.source),
        target: String(link.target),
        count: 1,
        status: link.status,
        ports: [portInfo],
        rawLink: link,
        protocol: proto,
        inPath: pathEdgeKeys.has(`${sortedIds[0]}-${sortedIds[1]}`),
        traffic_fwd_bps: trafficFwd,
        traffic_rev_bps: trafficRev
      });
    } else {
      const existing = linkMap.get(key);
      existing.count += 1;
      existing.ports.push(portInfo);
      if (link.status === 'active' || link.status === 'up') {
        existing.status = 'active';
      } else if (existing.status !== 'active' && link.status === 'degraded') {
        existing.status = 'degraded';
      }
      if (pathEdgeKeys.has(`${sortedIds[0]}-${sortedIds[1]}`)) existing.inPath = true;
      existing.traffic_fwd_bps += trafficFwd;
      existing.traffic_rev_bps += trafficRev;
    }
  });

  const aggregated = Array.from(linkMap.values());
  let maxTraffic = 0;
  if (opts?.trafficFlowEnabled) {
    for (const l of aggregated) {
      const total = Number(l.traffic_fwd_bps || 0) + Number(l.traffic_rev_bps || 0);
      if (total > maxTraffic) maxTraffic = total;
    }
  }

  return aggregated.map((l, idx) => {
    const isMultiLink = l.count > 1;
    const isOSPF = l.protocol === 'OSPF';
    const isBGP = l.protocol === 'BGP';
    const isL3 = isOSPF || isBGP;
    const trafficTotal = Number(l.traffic_fwd_bps || 0) + Number(l.traffic_rev_bps || 0);
    const sortedPair = [String(l.source), String(l.target)].sort().join('-');
    const pathMeta = pathEdgeDir.get(sortedPair);
    const pathPhase = (pathMeta && activeHopIndex != null)
      ? (pathMeta.hopIndex < activeHopIndex ? 'done' : (pathMeta.hopIndex === activeHopIndex ? 'active' : 'pending'))
      : null;

    let edgeLabel = isMultiLink
      ? `${l.count} Links (LAG)`
      : l.rawLink.label || l.ports[0];

    // Add protocol badge for L3 links
    if (isL3) {
      edgeLabel = `[${l.protocol}] ${l.rawLink.label || ''}`;
    }

    // Style overrides for Path Trace
    let strokeColor = l.status === 'active' || l.status === 'up' ? '#3b82f6' : (l.status === 'degraded' ? '#f59e0b' : '#ef4444');
    let strokeWidth = isMultiLink ? 4 : 2;
    let animated = l.status === 'active' || l.status === 'up' || l.status === 'degraded';
    let zIndex = 0;
    let dashArray = undefined; // solid by default
    let markerStart = undefined;
    let edgeSource = l.source;
    let edgeTarget = l.target;

    // L3 link styles: dashed lines with distinct colors
    if (isOSPF) {
      strokeColor = '#f97316'; // Orange for OSPF
      dashArray = '8 4';
      strokeWidth = 2.5;
    } else if (isBGP) {
      strokeColor = '#8b5cf6'; // Purple for BGP
      dashArray = '12 6';
      strokeWidth = 2.5;
    }

    if (l.inPath) {
      if (pathMeta) {
        edgeSource = pathMeta.fromId;
        edgeTarget = pathMeta.toId;
        edgeLabel = `#${pathMeta.hopIndex + 1} ${pathMeta.fromPort || '?'} → ${pathMeta.toPort || '?'}`;

        if (pathBadgesEnabled) {
          const ev = pathResult?.path?.[pathMeta.hopIndex]?.evidence;
          const protocol = ev?.protocol ? String(ev.protocol).toUpperCase() : null;
          const vrf = ev?.vrf ? String(ev.vrf) : null;
          const badgeParts = [];
          if (protocol) badgeParts.push(protocol);
          if (vrf) badgeParts.push(`VRF:${vrf}`);
          if (badgeParts.length > 0) {
            edgeLabel = `[${badgeParts.join(' · ')}] ${edgeLabel}`;
          }
        }
      }

      if (pathPhase === 'active') {
        strokeColor = '#22c55e';
        strokeWidth = 6;
        animated = true;
        zIndex = 12;
        dashArray = undefined;
      } else if (pathPhase === 'done') {
        strokeColor = '#16a34a';
        strokeWidth = 4;
        animated = false;
        zIndex = 11;
        dashArray = undefined;
      } else if (pathPhase === 'pending') {
        strokeColor = '#bbf7d0';
        strokeWidth = 3;
        animated = false;
        zIndex = 10;
        dashArray = '6 6';
      } else {
        strokeColor = '#10b981'; // Green for full path highlight
        strokeWidth = 4;
        animated = true;
        zIndex = 10;
        dashArray = undefined;
      }
    } else if (pathResult) {
      strokeColor = '#e5e7eb'; // Gray 200
      animated = false;
      dashArray = undefined;
    } else if (opts?.trafficFlowEnabled) {
      const heat = maxTraffic > 0 ? clamp01(trafficTotal / maxTraffic) : 0;
      const width = 2 + heat * 8;
      strokeWidth = isMultiLink ? Math.max(width, 4) : width;
      const hue = 200 - heat * 160; // 200(blue) -> 40(orange)
      strokeColor = `hsl(${hue}, 85%, 55%)`;
      animated = trafficTotal > 0;
      if (Number(l.traffic_rev_bps || 0) > 0) {
        markerStart = { type: MarkerType.ArrowClosed, color: strokeColor };
      }
      if (!isL3 && !isMultiLink) {
        edgeLabel = `${edgeLabel} · ${formatBps(trafficTotal)}`;
      }
    }

    const fullLabel = edgeLabel;
    const shouldTruncate = labelTruncateMode === 'all' || (labelTruncateMode === 'path' && l.inPath);
    const displayLabel = shouldTruncate ? truncateLabel(fullLabel, maxEdgeLabelLen) : fullLabel;

    return {
      id: `e-${idx}-${l.source}-${l.target}-${l.protocol}`,
      source: edgeSource,
      target: edgeTarget,
      label: displayLabel,
      type: 'default',
      animated: animated,
      data: {
        portDetails: l.ports,
        isMulti: isMultiLink,
        protocol: l.protocol,
        path: pathMeta ? { hopIndex: pathMeta.hopIndex, fromPort: pathMeta.fromPort, toPort: pathMeta.toPort } : null,
        fullLabel,
        traffic: {
          total_bps: trafficTotal,
          fwd_bps: Number(l.traffic_fwd_bps || 0),
          rev_bps: Number(l.traffic_rev_bps || 0)
        }
      },
      style: {
        stroke: strokeColor,
        strokeWidth: strokeWidth,
        strokeDasharray: dashArray,
        cursor: 'pointer',
        opacity: (pathResult && !l.inPath) ? 0.25 : 1
      },
      labelStyle: {
        fill: (pathResult && !l.inPath) ? '#9ca3af' : (l.inPath ? '#065f46' : (isOSPF ? '#ea580c' : isBGP ? '#7c3aed' : '#4b5563')),
        fontWeight: isMultiLink || isL3 ? 800 : 500,
        fontSize: 11,
        opacity: (pathResult && !l.inPath) ? 0.5 : 1
      },
      markerEnd: l.inPath ? { type: MarkerType.ArrowClosed, color: '#10b981' } : {
        type: MarkerType.ArrowClosed,
        color: strokeColor
      },
      markerStart,
      zIndex: zIndex
    };
  });
};

// Helper for Icons
const getIconByRole = (role) => {
  switch (role) {
    case 'core': return <Globe size={20} />;
    case 'distribution': return <Layers size={20} />;
    case 'security': return <Shield size={20} />;
    case 'wlc': return <Wifi size={20} />;
    case 'access_point': return <Wifi size={16} className="opacity-70" />;
    case 'endpoint': return <Box size={16} className="opacity-70" />;
    case 'endpoint_group': return <Layers size={16} className="opacity-70" />;
    case 'access_domestic': return <Box size={20} />;
    default: return <Box size={20} />; // Standard Access switch
  }
};

// --------------------------------------------------------------------------
// 3. 메인 컴포넌트
// --------------------------------------------------------------------------
const TopologyPage = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [autoRefreshTopology, setAutoRefreshTopology] = useState(true);
  const fileInputRef = useRef(null);
  const esRef = useRef(null);
  const topoReloadTimerRef = useRef(null);
  const topoReloadCooldownRef = useRef(0);

  // Data Filtering
  const [sites, setSites] = useState([]);
  const [selectedSiteId, setSelectedSiteId] = useState('all');
  const [rawTopology, setRawTopology] = useState({ nodes: [], links: [] });

  // Tooltip
  const [tooltip, setTooltip] = useState(null);

  // Path Trace State
  const [showPathTrace, setShowPathTrace] = useState(false);
  const [srcIp, setSrcIp] = useState('');
  const [dstIp, setDstIp] = useState('');
  const [pathResult, setPathResult] = useState(null);
  const [pathPlayback, setPathPlayback] = useState(false);
  const [pathActiveEdgeIndex, setPathActiveEdgeIndex] = useState(null);
  const [pathEvidenceOpen, setPathEvidenceOpen] = useState({});
  const [pathPlaybackSpeed, setPathPlaybackSpeed] = useState(1);
  const [pathBadgesEnabled, setPathBadgesEnabled] = useState(true);
  const [pathEdgeLabelMaxLen, setPathEdgeLabelMaxLen] = useState(42);
  const [pathEdgeLabelTruncateMode, setPathEdgeLabelTruncateMode] = useState('all'); // 'all' | 'path'
  const reactFlowInstanceRef = useRef(null);
  const [tracing, setTracing] = useState(false);

  // Flow Insight (NetFlow)
  const [showFlowInsight, setShowFlowInsight] = useState(false);
  const [flowWindowSec, setFlowWindowSec] = useState(300);
  const [flowTalkers, setFlowTalkers] = useState([]);
  const [flowFlows, setFlowFlows] = useState([]);
  const [flowApps, setFlowApps] = useState([]);
  const [flowSelectedApp, setFlowSelectedApp] = useState('');
  const [flowSelectedAppFlows, setFlowSelectedAppFlows] = useState([]);
  const [flowLoading, setFlowLoading] = useState(false);
  const [flowAppLoading, setFlowAppLoading] = useState(false);

  // L3 Layer Filter State
  const [layerFilter, setLayerFilter] = useState('all'); // 'all' | 'l2' | 'l3'

  const [showCandidates, setShowCandidates] = useState(false);
  const [candidates, setCandidates] = useState([]);
  const [candidateJobId, setCandidateJobId] = useState('');
  const [candidateSearch, setCandidateSearch] = useState('');
  const [candidateLoading, setCandidateLoading] = useState(false);
  const [candidateEdits, setCandidateEdits] = useState({});
  const [candidateStatusFilter, setCandidateStatusFilter] = useState('all');
  const [candidateOrderBy, setCandidateOrderBy] = useState('last_seen');
  const [candidateOrderDir, setCandidateOrderDir] = useState('desc');
  const [candidateAutoRefresh, setCandidateAutoRefresh] = useState(true);
  const [candidateRecommendations, setCandidateRecommendations] = useState({});
  const [candidateRecOpen, setCandidateRecOpen] = useState({});
  const [candidateRecLoading, setCandidateRecLoading] = useState({});
  const [candidateActionError, setCandidateActionError] = useState({});
  const [selectedCandidateIds, setSelectedCandidateIds] = useState([]);

  const [endpointGroupPanel, setEndpointGroupPanel] = useState({ open: false, loading: false, error: '', group: null, endpoints: [] });

  const loadCandidates = async () => {
    setCandidateLoading(true);
    try {
      const params = {
        order_by: candidateOrderBy,
        order_dir: candidateOrderDir,
        limit: 500,
      };
      if (candidateJobId) params.job_id = candidateJobId;
      if (candidateStatusFilter !== 'all') params.status = candidateStatusFilter;
      if (candidateSearch) params.search = candidateSearch;
      const res = await TopologyService.getCandidates(params);
      const list = res.data || [];
      setCandidates(list);
      setSelectedCandidateIds((prev) => prev.filter((id) => list.some((c) => c.id === id)));
      setCandidateEdits((prev) => {
        const next = { ...prev };
        for (const c of list) {
          if (next[c.id] === undefined) next[c.id] = c.mgmt_ip || '';
        }
        return next;
      });
    } catch (e) {
      toast.error("Failed to load candidates");
    } finally {
      setCandidateLoading(false);
    }
  };

  // Health View State
  const [showHealth, setShowHealth] = useState(false);
  const [healthMetric, setHealthMetric] = useState('score'); // 'score' | 'cpu' | 'memory'
  const [trafficFlowEnabled, setTrafficFlowEnabled] = useState(false);

  // 1. Load Data
  const loadData = async () => {
    setLoading(true);
    try {
      console.log("📡 Fetching Topology & Sites...");
      const [topoRes, siteRes] = await Promise.all([
        SDNService.getTopology(),
        DeviceService.getSites()
      ]);

      setSites(siteRes.data);
      setRawTopology({
        nodes: topoRes.data?.nodes || [],
        links: topoRes.data?.links || []
      });

    } catch (error) {
      console.error("❌ Error loading data:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadFlowInsight = async () => {
    setFlowLoading(true);
    try {
      const [talkersRes, flowsRes, appsRes] = await Promise.all([
        TrafficService.getTopTalkers({ window_sec: flowWindowSec, limit: 10 }),
        TrafficService.getTopFlows({ window_sec: flowWindowSec, limit: 10 }),
        TrafficService.getTopApps({ window_sec: flowWindowSec, limit: 10 }),
      ]);
      setFlowTalkers(Array.isArray(talkersRes.data) ? talkersRes.data : []);
      setFlowFlows(Array.isArray(flowsRes.data) ? flowsRes.data : []);
      const apps = Array.isArray(appsRes.data) ? appsRes.data : [];
      setFlowApps(apps);
      if (!flowSelectedApp && apps.length > 0) {
        setFlowSelectedApp(String(apps[0].app || ''));
      }
    } catch (e) {
      toast.error('Failed to load flow insight');
    } finally {
      setFlowLoading(false);
    }
  };

  const loadSelectedAppFlows = async (appName) => {
    const app = String(appName || '').trim();
    if (!app) return;
    setFlowAppLoading(true);
    try {
      const res = await TrafficService.getTopAppFlows({ app, window_sec: flowWindowSec, limit: 10 });
      setFlowSelectedAppFlows(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      toast.error('Failed to load app flows');
    } finally {
      setFlowAppLoading(false);
    }
  };

  const handleTrace = async () => {
    if (!srcIp || !dstIp) return;
    setTracing(true);
    setPathResult(null);
    setPathPlayback(false);
    setPathActiveEdgeIndex(null);
    setPathEvidenceOpen({});
    setPathPlaybackSpeed(1);
    setPathBadgesEnabled(true);
    try {
      const res = await SDNService.tracePath(srcIp, dstIp);
      setPathResult(res.data);
    } catch (err) {
      toast.error("Trace failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setTracing(false);
    }
  };

  const clearTrace = () => {
    setPathResult(null);
    setSrcIp('');
    setDstIp('');
    setPathPlayback(false);
    setPathActiveEdgeIndex(null);
    setPathEvidenceOpen({});
    setPathPlaybackSpeed(1);
    setPathBadgesEnabled(true);
  };

  const focusActiveHop = useCallback((edgeIdx) => {
    const inst = reactFlowInstanceRef.current;
    if (!inst) return;
    if (!pathResult?.path || pathResult.path.length < 2) return;
    if (edgeIdx == null) return;

    const maxIdx = pathResult.path.length - 2;
    const i = Math.min(Math.max(0, Number(edgeIdx)), maxIdx);
    const fromId = String(pathResult.path[i]?.id ?? '');
    const toId = String(pathResult.path[i + 1]?.id ?? '');
    if (!fromId || !toId) return;

    const nodesToFit = inst.getNodes().filter(n => String(n.id) === fromId || String(n.id) === toId);
    if (nodesToFit.length === 0) return;
    inst.fitView({ nodes: nodesToFit, padding: 0.55, duration: 450, maxZoom: 1.35 });
  }, [pathResult]);

  useEffect(() => {
    if (!pathResult?.path || pathResult.path.length < 2) return;
    setPathPlayback(false);
    setPathActiveEdgeIndex(null);
    setPathEvidenceOpen({});

    const ids = new Set(pathResult.path.map(n => String(n.id)));
    const timer = setTimeout(() => {
      const inst = reactFlowInstanceRef.current;
      if (!inst) return;
      const nodesToFit = inst.getNodes().filter(n => ids.has(String(n.id)));
      if (nodesToFit.length > 0) {
        inst.fitView({ nodes: nodesToFit, padding: 0.3, duration: 500 });
      }
    }, 50);
    return () => clearTimeout(timer);
  }, [pathResult]);

  useEffect(() => {
    if (pathActiveEdgeIndex == null) return;
    const t = setTimeout(() => {
      focusActiveHop(pathActiveEdgeIndex);
    }, 30);
    return () => clearTimeout(t);
  }, [pathActiveEdgeIndex, focusActiveHop]);

  useEffect(() => {
    if (!pathPlayback) return;
    if (!pathResult?.path || pathResult.path.length < 2) return;

    const maxIdx = pathResult.path.length - 2;
    const speed = Number(pathPlaybackSpeed || 1);
    const intervalMs = Math.max(200, Math.round(900 / (Number.isFinite(speed) && speed > 0 ? speed : 1)));
    const timer = setTimeout(() => {
      setPathActiveEdgeIndex((prev) => {
        const next = prev == null ? 0 : prev + 1;
        if (next > maxIdx) {
          setPathPlayback(false);
          return maxIdx;
        }
        return next;
      });
    }, intervalMs);
    return () => clearTimeout(timer);
  }, [pathPlayback, pathActiveEdgeIndex, pathResult, pathPlaybackSpeed]);

  useEffect(() => {
    if (!showFlowInsight) return;
    loadFlowInsight();
  }, [showFlowInsight, flowWindowSec]);

  useEffect(() => {
    if (!showFlowInsight) return;
    if (!flowSelectedApp) return;
    loadSelectedAppFlows(flowSelectedApp);
  }, [showFlowInsight, flowSelectedApp, flowWindowSec]);

  useEffect(() => {
    loadData();
  }, [refreshKey]);

  useEffect(() => {
    if (esRef.current) {
      try { esRef.current.close(); } catch (e) { void e; }
      esRef.current = null;
    }

    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
    const url = `${API_BASE_URL}/topology/stream`;
    const es = new EventSource(url);
    esRef.current = es;

    const norm = (s) => String(s || '').trim().toLowerCase().replace(/\s+/g, '');

    es.addEventListener('link_update', (evt) => {
      try {
        const msg = JSON.parse(evt.data || '{}');
        const deviceId = msg.device_id != null ? String(msg.device_id) : null;
        const neighborId = msg.neighbor_device_id != null ? String(msg.neighbor_device_id) : null;
        const protocol = msg.protocol ? String(msg.protocol).toUpperCase() : null;
        const state = String(msg.state || '').toLowerCase();
        const isUp = state === 'up' || state === 'active';
        const isDegraded = state === 'degraded';
        const nextStatus = isDegraded ? 'degraded' : (isUp ? 'active' : 'down');
        const ifName = msg.interface ? String(msg.interface) : '';
        const ifNorm = norm(ifName);

        setRawTopology(prev => {
          const prevLinks = Array.isArray(prev?.links) ? prev.links : [];
          if (prevLinks.length === 0) return prev;
          let matched = false;
          const updated = prevLinks.map((l) => {
            const lProto = String(l?.protocol || 'LLDP').toUpperCase();
            if (protocol && lProto !== protocol) return l;

            const src = String(l?.source ?? '');
            const dst = String(l?.target ?? '');

            if (neighborId) {
              const match = (src === deviceId && dst === neighborId) || (src === neighborId && dst === deviceId);
              if (!match) return l;
              matched = true;
              if (l.status === nextStatus) return l;
              return { ...l, status: nextStatus };
            }

            if (!deviceId || !ifNorm) return l;
            const srcPortNorm = norm(l?.src_port);
            const dstPortNorm = norm(l?.dst_port);
            const match = (src === deviceId && srcPortNorm === ifNorm) || (dst === deviceId && dstPortNorm === ifNorm);
            if (!match) return l;
            matched = true;
            if (l.status === nextStatus) return l;
            return { ...l, status: nextStatus };
          });
          if (!matched && deviceId && neighborId) {
            if (!topoReloadTimerRef.current) {
              topoReloadTimerRef.current = setTimeout(() => {
                topoReloadTimerRef.current = null;
                const now = Date.now();
                if (now - topoReloadCooldownRef.current < 1500) return;
                topoReloadCooldownRef.current = now;
                setRefreshKey((k) => k + 1);
              }, 700);
            }
          }
          return { ...prev, links: updated };
        });
      } catch (e) { void e; }
    });

    es.onerror = () => {
      try { es.close(); } catch (e) { void e; }
      esRef.current = null;
    };

    return () => {
      if (topoReloadTimerRef.current) {
        try { clearTimeout(topoReloadTimerRef.current); } catch (e) { void e; }
        topoReloadTimerRef.current = null;
      }
      try { es.close(); } catch (e) { void e; }
      esRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!autoRefreshTopology) return;
    const t = setInterval(() => {
      loadData();
    }, 10000);
    return () => clearInterval(t);
  }, [autoRefreshTopology]);

  useEffect(() => {
    if (!showCandidates) return;
    loadCandidates();
  }, [showCandidates, candidateJobId, candidateStatusFilter, candidateOrderBy, candidateOrderDir, refreshKey]);

  useEffect(() => {
    if (!showCandidates) return;
    const t = setTimeout(() => {
      loadCandidates();
    }, 400);
    return () => clearTimeout(t);
  }, [showCandidates, candidateSearch]);

  useEffect(() => {
    if (!showCandidates) return;
    if (!candidateAutoRefresh) return;
    const t = setInterval(() => {
      loadCandidates();
    }, 8000);
    return () => clearInterval(t);
  }, [showCandidates, candidateAutoRefresh, candidateJobId, candidateStatusFilter, candidateOrderBy, candidateOrderDir, candidateSearch]);

  // 2. Process Nodes & Edges
  useEffect(() => {
    if (!rawTopology.nodes.length) return;

    // A. Filter Nodes
    let filteredNodes = rawTopology.nodes;
    if (selectedSiteId !== 'all') {
      filteredNodes = rawTopology.nodes.filter(n => n.site_id === parseInt(selectedSiteId));
    }

    const pathNodeIds = new Set(pathResult?.path?.map(n => String(n.id)) || []);
    const pathOrderById = new Map();
    (pathResult?.path || []).forEach((n, idx) => {
      pathOrderById.set(String(n.id), idx);
    });
    const activeFromId = (pathActiveEdgeIndex != null && pathResult?.path?.[pathActiveEdgeIndex])
      ? String(pathResult.path[pathActiveEdgeIndex].id)
      : null;
    const activeToId = (pathActiveEdgeIndex != null && pathResult?.path?.[pathActiveEdgeIndex + 1])
      ? String(pathResult.path[pathActiveEdgeIndex + 1].id)
      : null;

    // B. Transform Nodes
    const flowNodes = filteredNodes.map((d) => {
      const isPathNode = pathNodeIds.has(String(d.id));
      const isDimmed = pathResult && !isPathNode;
      const hopIndex = isPathNode ? pathOrderById.get(String(d.id)) : null;
      const isActivePathNode = isPathNode && (String(d.id) === activeFromId || String(d.id) === activeToId);

      // Metrics extraction
      const healthScore = d.metrics?.health_score ?? 100;
      const cpu = d.metrics?.cpu || 0;
      const memory = d.metrics?.memory || 0;
      const isWLC = d.role === 'wlc';
      const totalAps = d.metrics?.total_aps || 0;
      const downAps = d.metrics?.down_aps || 0;
      const clients = d.metrics?.clients || 0;
      const trafficIn = d.metrics?.traffic_in || 0;
      const trafficOut = d.metrics?.traffic_out || 0;
      const modelText = String(d.model || '').trim();
      const showModel = !!modelText && !modelText.toLowerCase().includes('unknown');

      // Dynamic metric based on user selection
      let metricValue, metricLabel, isHighBad;
      if (healthMetric === 'cpu') {
        metricValue = cpu;
        metricLabel = 'CPU';
        isHighBad = true; // High CPU = bad
      } else if (healthMetric === 'memory') {
        metricValue = memory;
        metricLabel = 'Memory';
        isHighBad = true; // High Memory = bad
      } else {
        metricValue = healthScore;
        metricLabel = 'Health';
        isHighBad = false; // Low Health Score = bad
      }

      let healthColor = 'bg-green-100 text-green-600';
      let healthBorder = '2px solid #10b981';
      let healthBg = '#fff';

      // Color logic based on metric type
      const isBad = isHighBad ? metricValue >= 80 : metricValue < 50;
      const isWarning = isHighBad ? (metricValue >= 50 && metricValue < 80) : (metricValue >= 50 && metricValue < 80);

      if (d.status !== 'online') {
        healthColor = 'bg-gray-100 text-gray-400';
        healthBorder = '2px solid #9ca3af';
      } else if (showHealth) {
        if (isBad) {
          healthColor = 'bg-red-100 text-red-600 animate-pulse';
          healthBorder = '2px solid #ef4444';
          healthBg = '#fef2f2';
        } else if (isWarning) {
          healthColor = 'bg-yellow-100 text-yellow-600';
          healthBorder = '2px solid #f59e0b';
          healthBg = '#fffbeb';
        } else {
          healthColor = 'bg-green-100 text-green-600';
          healthBorder = '2px solid #10b981';
          healthBg = '#ecfdf5';
        }
      } else {
        // Standard Role-based Border
        if (d.role === 'core') healthBorder = '2px solid #3b82f6';
        else if (d.role === 'wlc') healthBorder = '2px solid #9333ea';
        else if (d.role === 'security') healthBorder = '2px solid #ef4444';
        else if (d.role === 'distribution') healthBorder = '2px solid #06b6d4';
        else if (d.role === 'access_domestic') healthBorder = '2px solid #f59e0b';

        // Standard Role-based BG
        if (d.role === 'core') healthBg = '#eff6ff';
        else if (d.role === 'wlc') healthBg = '#fdf4ff';
        else if (d.role === 'security') healthBg = '#fff1f2';
        else if (d.role === 'distribution') healthBg = '#ecfeff';
        else if (d.role === 'access_domestic') healthBg = '#fffbeb';
      }

      // Badge color based on metric
      const getBadgeClass = () => {
        if (isBad) return 'bg-red-500 text-white';
        if (isWarning) return 'bg-yellow-400 text-white';
        return 'bg-green-500 text-white';
      };

      return {
        id: String(d.id),
        site_id: d.site_id, // For ELK grouping
        site_name: d.site_name,
        tier: d.tier,
        data: {
          label: (
            <div className="flex flex-col items-center justify-center p-2 min-w-[120px]">
              <div className={`p-2 rounded-full mb-2 ${healthColor} ${isPathNode ? 'ring-2 ring-green-500 ring-offset-2' : ''}`}>
                {getIconByRole(d.role)}
              </div>
              <div className="font-bold text-sm text-gray-800">{d.label}</div>
              <div className="text-xs text-gray-500 font-mono mb-1">{d.ip}</div>
              {showModel && (
                <div className="text-[10px] text-gray-600 font-mono mb-1 max-w-[150px] truncate" title={modelText}>
                  {modelText}
                </div>
              )}

              {trafficFlowEnabled && d.status === 'online' && (
                <div className="flex items-center gap-1 text-[10px] font-semibold text-gray-600">
                  <span className="px-2 py-0.5 rounded-full bg-sky-50 text-sky-700">IN {formatBps(trafficIn)}</span>
                  <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700">OUT {formatBps(trafficOut)}</span>
                </div>
              )}

              {showHealth && d.status === 'online' && (
                <div className="flex flex-col items-center gap-1">
                  <div className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${getBadgeClass()}`}>
                    {metricLabel}: {metricValue}%
                  </div>
                  {isWLC && totalAps > 0 && (
                    <div className={`text-[9px] px-2 py-0.5 rounded-full font-medium ${downAps > 0 ? 'bg-orange-100 text-orange-700' : 'bg-purple-100 text-purple-700'}`}>
                      AP: {totalAps - downAps}/{totalAps} · {clients} clients
                    </div>
                  )}
                </div>
              )}

              {isPathNode && (
                <div className="mt-1 flex items-center gap-1">
                  <div className={`text-[10px] text-white px-2 py-0.5 rounded-full ${isActivePathNode ? 'bg-emerald-600 animate-pulse' : 'bg-green-500'}`}>
                    Hop {Number.isFinite(Number(hopIndex)) ? (Number(hopIndex) + 1) : '?'}
                  </div>
                </div>
              )}
            </div>
          ),
          tier: d.tier,
          role: d.role,
          device_id: d.device_id,
          port: d.port,
          node_label: d.label
        },
        position: { x: 0, y: 0 },
        style: {
          background: healthBg,
          border: isActivePathNode ? '4px solid #22c55e' : (isPathNode ? '3px solid #10b981' : healthBorder),
          borderRadius: '12px',
          padding: 5,
          boxShadow: isActivePathNode ? '0 0 22px rgba(34, 197, 94, 0.55)' : (isPathNode ? '0 0 15px rgba(16, 185, 129, 0.4)' : '0 4px 6px -1px rgba(0, 0, 0, 0.1)'),
          cursor: 'pointer',
          fontSize: '12px',
          opacity: isDimmed ? 0.3 : 1,
          zIndex: isPathNode ? 10 : 1
        },
      };
    });

    // C. Filter Links (with layer filter)
    const visibleNodeIds = new Set(filteredNodes.map(n => String(n.id)));
    const filteredLinks = rawTopology.links.filter(l => {
      if (!visibleNodeIds.has(String(l.source)) || !visibleNodeIds.has(String(l.target))) return false;
      const proto = (l.protocol || 'LLDP').toUpperCase();
      const isL3Proto = proto === 'OSPF' || proto === 'BGP';
      if (layerFilter === 'l2' && isL3Proto) return false;
      if (layerFilter === 'l3' && !isL3Proto) return false;
      return true;
    });

    const nodeTrafficById = new Map();
    for (const n of filteredNodes) {
      const id = String(n.id);
      nodeTrafficById.set(id, {
        in_bps: n.metrics?.traffic_in || 0,
        out_bps: n.metrics?.traffic_out || 0
      });
    }

    // D. Build Edges (with Path logic)
    const flowEdges = aggregateLinks(filteredLinks, pathResult, {
      trafficFlowEnabled,
      nodeTrafficById,
      pathPlayback: { activeEdgeIndex: pathActiveEdgeIndex },
      pathBadgesEnabled,
      maxEdgeLabelLen: pathEdgeLabelMaxLen,
      labelTruncateMode: pathEdgeLabelTruncateMode,
    });

    // E. Apply Layout
    // E. Apply Layout (Async ELK)
    const runLayout = async () => {
      if (flowNodes.length === 0) {
        setNodes([]);
        setEdges([]);
        return;
      }


      // 0. Check for Saved Layout from DB FIRST
      try {
        const res = await TopologyService.getLayout();
        const savedNodes = res.data?.data; // The actual nodes array is stored in the 'data' field of the layout object

        if (Array.isArray(savedNodes) && savedNodes.length > 0) {
          console.log("Loading saved layout from DB...");

          // Map current live data for quick lookup
          const liveDataMap = new Map(flowNodes.map(n => [n.id, n]));

          // Merge saved position/size with live data
          const mergedNodes = savedNodes.map(savedNode => {
            const liveNode = liveDataMap.get(savedNode.id);
            if (liveNode) {
              return {
                ...savedNode,
                data: liveNode.data, // Use live data (health, status)
                style: {
                  ...savedNode.style,
                  // Merge styles: Keep saved dimensions for groups, use live colors for devices
                  ...(savedNode.type === 'groupNode' ? {} : liveNode.style)
                }
              };
            }
            return savedNode; // Keep saved node (maybe offline, or group)
          });

          setNodes(mergedNodes);
          setEdges(flowEdges);
          return; // Skip ELK auto-layout
        }
      } catch (e) {
        // 404 Not Found is expected if no layout saved
        // console.warn("No saved layout found or error:", e);
      }

      // 1. Create Group Nodes for Sites
      const siteGroups = new Map();

      // Clone nodes to avoid mutating state directly (good practice)
      const deviceNodes = flowNodes.map(node => ({ ...node }));

      deviceNodes.forEach(node => {
        const siteId = node.site_id || 'default_site';
        const groupId = `group-${siteId}`;

        if (!siteGroups.has(groupId)) {
          siteGroups.set(groupId, {
            id: groupId,
            type: 'groupNode', // Use custom Resizable Group Node
            data: { label: node.site_name || siteId },
            position: { x: 0, y: 0 },
            style: {
              backgroundColor: 'rgba(240, 244, 255, 0.2)', // Very transparent
              border: '2px dashed rgba(148, 163, 184, 0.7)', // Slightly darker border for visibility
              borderRadius: '12px',
              padding: 20,
              width: 10,
              height: 10,
              zIndex: -100, // Still behind, but selectable

              // Helper to position label at top
              display: 'flex',
              alignItems: 'flex-start', // Top alignment
              justifyContent: 'center',
              fontWeight: 'bold',
              color: '#475569', // Slate-600 (darker)
              fontSize: '16px', // Larger font
            },
            draggable: true,
            selectable: true, // Allow selection for resizing
          });
        }

        // Link device node to group
        node.parentNode = groupId;
        node.extent = 'parent'; // Keep child inside parent
      });

      // 2. Combine all nodes
      const allNodes = [...Array.from(siteGroups.values()), ...deviceNodes];

      // 3. Calculate Layout
      try {
        const { nodes: layoutedNodes, edges: layoutedEdges } = await getElkLayoutedElements(
          allNodes,
          flowEdges
        );
        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
      } catch (err) {
        console.error("ELK Layout Failed:", err);
      }
    };

    runLayout();

  }, [rawTopology, selectedSiteId, pathResult, showHealth, healthMetric, layerFilter, trafficFlowEnabled, setNodes, setEdges]); // Dep: pathResult, showHealth, healthMetric, layerFilter, trafficFlowEnabled


  // Events
  const onNodeClick = useCallback(async (event, node) => {
    if (node.type === 'groupNode') return;
    if (String(node.id || '').startsWith('ep-') || node?.data?.role === 'endpoint') return;

    if (node?.data?.role === 'endpoint_group') {
      const deviceId = node?.data?.device_id;
      const port = node?.data?.port;
      if (!deviceId || !port) return;

      setEndpointGroupPanel({ open: true, loading: true, error: '', group: { device_id: deviceId, port, label: node?.data?.node_label || null }, endpoints: [] });
      try {
        const res = await DeviceService.getEndpointGroupDetails(deviceId, port, { hours: 24 });
        setEndpointGroupPanel(prev => ({ ...prev, loading: false, endpoints: res.data?.endpoints || [], group: { ...prev.group, count: res.data?.count } }));
      } catch (e) {
        setEndpointGroupPanel(prev => ({ ...prev, loading: false, error: e.response?.data?.detail || e.message || 'Failed to load endpoint group' }));
      }
      return;
    }

    navigate(`/devices/${node.id}`);
  }, [navigate]);

  const onEdgeMouseEnter = useCallback((event, edge) => {
    if (edge.data && edge.data.portDetails) {
      setTooltip({
        x: event.clientX,
        y: event.clientY,
        content: edge.data.portDetails,
        label: edge.data?.fullLabel || edge.label
      });
    }
  }, []);

  const onEdgeMouseLeave = useCallback(() => {
    setTooltip(null);
  }, []);

  const onEdgeMouseMove = useCallback((event) => {
    setTooltip((prev) => prev ? { ...prev, x: event.clientX, y: event.clientY } : null);
  }, []);


  return (
    <div className="h-full w-full bg-[#f4f5f9] dark:bg-[#0e1012] flex flex-col animate-fade-in relative">

      {/* Header */}
      <div className="px-6 py-4 flex justify-between items-center bg-white dark:bg-[#1b1d1f] border-b border-gray-200 dark:border-gray-800 shadow-sm z-10">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Network className="text-indigo-500" /> Network Map
          </h1>
        </div>

        <div className="flex gap-2">
          {/* Health View Toggle + Metric Selector */}
          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowHealth(!showHealth)}
              className={`flex items-center gap-2 px-3 py-1.5 border rounded-md shadow-sm text-sm font-medium transition-colors ${showHealth ? 'bg-red-500 text-white border-red-600' : 'bg-white dark:bg-[#25282c] text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700'}`}
            >
              <Activity size={14} /> Health
            </button>
            {showHealth && (
              <select
                value={healthMetric}
                onChange={(e) => setHealthMetric(e.target.value)}
                className="px-2 py-1.5 text-sm bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 rounded-md text-gray-700 dark:text-gray-300 cursor-pointer outline-none"
              >
                <option value="score">Score</option>
                <option value="cpu">CPU</option>
                <option value="memory">Memory</option>
              </select>
            )}
          </div>

          <button
            onClick={() => setTrafficFlowEnabled(!trafficFlowEnabled)}
            className={`flex items-center gap-2 px-3 py-1.5 border rounded-md shadow-sm text-sm font-medium transition-colors ${trafficFlowEnabled ? 'bg-sky-600 text-white border-sky-700' : 'bg-white dark:bg-[#25282c] text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700'}`}
          >
            <Link2 size={14} /> Traffic Flow
          </button>

          <button
            onClick={() => setShowFlowInsight(!showFlowInsight)}
            className={`flex items-center gap-2 px-3 py-1.5 border rounded-md shadow-sm text-sm font-medium transition-colors ${showFlowInsight ? 'bg-emerald-600 text-white border-emerald-700' : 'bg-white dark:bg-[#25282c] text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700'}`}
          >
            <Activity size={14} /> Flow Insight
          </button>

          {/* Path Trace Toggle */}
          <button
            onClick={() => setShowPathTrace(!showPathTrace)}
            className={`flex items-center gap-2 px-3 py-1.5 border rounded-md shadow-sm text-sm font-medium transition-colors ${showPathTrace ? 'bg-indigo-500 text-white border-indigo-600' : 'bg-white dark:bg-[#25282c] text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700'}`}
          >
            <Route size={14} /> Path Trace
          </button>

          {/* Layer Filter (L2 / L3 / All) */}
          <div className="flex items-center gap-0.5 bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 rounded-md overflow-hidden shadow-sm">
            {['all', 'l2', 'l3'].map(lf => (
              <button
                key={lf}
                onClick={() => setLayerFilter(lf)}
                className={`px-2.5 py-1.5 text-xs font-semibold transition-colors ${layerFilter === lf
                    ? lf === 'l3' ? 'bg-purple-500 text-white' : lf === 'l2' ? 'bg-blue-500 text-white' : 'bg-gray-700 text-white'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
              >
                {lf === 'all' ? 'All' : lf.toUpperCase()}
              </button>
            ))}
          </div>

          <button
            onClick={() => setShowCandidates(!showCandidates)}
            className={`flex items-center gap-2 px-3 py-1.5 border rounded-md shadow-sm text-sm font-medium transition-colors ${showCandidates ? 'bg-amber-500 text-white border-amber-600' : 'bg-white dark:bg-[#25282c] text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-700'}`}
          >
            <Link2 size={14} /> Candidates
          </button>

          {/* Site Filter */}
          <div className="flex items-center px-3 py-1.5 bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 rounded-md shadow-sm">
            <MapIcon size={14} className="text-gray-500 mr-2" />
            <select
              value={selectedSiteId}
              onChange={(e) => setSelectedSiteId(e.target.value)}
              className="text-sm bg-transparent outline-none text-gray-700 dark:text-gray-300 cursor-pointer"
            >
              <option value="all">Global View (All Sites)</option>
              {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>


          {/* Layout Controls */}
          <div className="flex gap-2">
            <button
              onClick={async () => {
                try {
                  await TopologyService.saveLayout({ name: "User Layout", data: nodes });
                  toast.success("Layout saved successfully!");
                } catch (e) {
                  console.error("Failed to save layout:", e);
                  toast.error("Failed to save layout.");
                }
              }}
              title="Save current layout to DB"
              className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm text-sm"
            >
              <Save size={14} />
            </button>

            <button
              onClick={async () => {
                if (window.confirm("Are you sure you want to reset the layout to auto-generated?")) {
                  try {
                    await TopologyService.resetLayout();
                    setRefreshKey(k => k + 1);
                  } catch (e) {
                    console.error("Failed to reset layout:", e);
                  }
                }
              }}
              title="Reset to auto layout"
              className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm text-sm"
            >
              <LayoutTemplate size={14} />
            </button>

            {/* Hidden File Input for Import */}
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              accept=".json"
              onChange={async (e) => {
                const file = e.target.files[0];
                if (!file) return;

                try {
                  const text = await file.text();
                  const json = JSON.parse(text);

                  if (Array.isArray(json)) {
                    if (window.confirm(`Import layout from "${file.name}"? This will overwrite your current layout.`)) {
                      // Apply layout immediately
                      setNodes(json);
                      // Auto-save to DB for persistence
                      try {
                        await TopologyService.saveLayout({ name: "Imported Layout", data: json });
                        toast.success("Layout imported and saved successfully!");
                      } catch (e) {
                        console.error("Failed to save imported layout:", e);
                        toast.warning("Layout imported, but failed to save to DB.");
                      }
                    }
                  } else {
                    toast.warning("Invalid topology file format (must be a node array).");
                  }
                } catch (err) {
                  console.error("File read error:", err);
                  toast.error("Failed to read file.");
                }
                // Reset input
                e.target.value = '';
              }}
            />

            <button
              onClick={() => {
                const jsonString = JSON.stringify(nodes, null, 2);
                const blob = new Blob([jsonString], { type: "application/json" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `topology-layout-${new Date().toISOString().slice(0, 10)}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
              }}
              title="Export Layout (JSON)"
              className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm text-sm"
            >
              <Download size={14} />
            </button>

            <button
              onClick={() => fileInputRef.current?.click()}
              title="Import Layout (JSON)"
              className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm text-sm"
            >
              <Upload size={14} />
            </button>
          </div>

          <button
            onClick={() => setRefreshKey(k => k + 1)}
            className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors shadow-sm text-sm"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>

          <label className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#25282c] border border-gray-300 dark:border-gray-700 text-gray-700 dark:text-gray-300 rounded-md shadow-sm text-sm select-none">
            <input
              type="checkbox"
              checked={autoRefreshTopology}
              onChange={(e) => setAutoRefreshTopology(e.target.checked)}
            />
            Auto
          </label>
        </div>
      </div>

      {/* Map Area */}
      <div className="flex-1 w-full h-full relative">
        {!loading && nodes.length === 0 && (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400 z-10">
            <AlertCircle size={40} className="mb-2" />
            <p>No topology data available for this view.</p>
          </div>
        )}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onEdgeMouseEnter={onEdgeMouseEnter}
          onEdgeMouseLeave={onEdgeMouseLeave}
          onEdgeMouseMove={onEdgeMouseMove}
          nodeTypes={nodeTypes}
          onInit={(inst) => { reactFlowInstanceRef.current = inst; }}
          fitView
          className="bg-gray-50 dark:bg-[#0e1012]"
          minZoom={0.1}
        >
          <MiniMap nodeColor="#aaa" maskColor="rgba(0, 0, 0, 0.1)" />
          <Controls />
          <Background color="#ccc" gap={20} size={1} />

          <Panel position="bottom-left" className="bg-white/90 p-2 rounded shadow text-xs text-gray-500">
            <div>Hover over links to see details.</div>
          </Panel>

          {/* Legend Panel */}
          <Panel position="bottom-right" className="bg-white/90 dark:bg-[#1b1d1f]/90 p-3 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 text-xs text-gray-600 dark:text-gray-300 backdrop-blur-sm m-4 z-50">
            <h4 className="font-bold mb-2 flex items-center gap-1.5 border-b pb-1 dark:border-gray-700 text-gray-800 dark:text-gray-200">
              <Info size={14} /> Legend
            </h4>
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-blue-50 text-blue-600 border border-blue-200">
                  <Globe size={14} />
                </div>
                <span>Core</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-cyan-50 text-cyan-600 border border-cyan-200">
                  <Layers size={14} />
                </div>
                <span>Dist</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-[#fdf4ff] text-[#9333ea] border border-[#9333ea]">
                  <Wifi size={14} />
                </div>
                <span>WLC</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-red-50 text-red-500 border border-red-200">
                  <Shield size={14} />
                </div>
                <span>Security</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-amber-50 text-amber-500 border border-amber-200">
                  <Box size={14} />
                </div>
                <span>Domestic</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded flex items-center justify-center bg-white text-gray-500 border border-gray-300">
                  <Box size={14} />
                </div>
                <span>Access</span>
              </div>
            </div>
          </Panel>

          {/* Path Trace Panel Overlay */}
          {showPathTrace && (
            <Panel position="top-right" className="m-4">
              <div className="w-80 bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 animate-slide-in-right text-white">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-bold flex items-center gap-2"><Route size={18} className="text-indigo-400" /> Visual Path Trace</h3>
                  <button onClick={() => setShowPathTrace(false)}><XCircle size={18} className="text-gray-500 hover:text-white" /></button>
                </div>

                <div className="space-y-3 mb-4">
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Source IP</label>
                    <input
                      type="text"
                      value={srcIp}
                      onChange={(e) => setSrcIp(e.target.value)}
                      placeholder="e.g. 192.168.10.100"
                      className="w-full bg-[#0e1012] border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none font-mono"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-gray-400 block mb-1">Destination IP</label>
                    <input
                      type="text"
                      value={dstIp}
                      onChange={(e) => setDstIp(e.target.value)}
                      placeholder="e.g. 10.20.30.50"
                      className="w-full bg-[#0e1012] border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none font-mono"
                    />
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={handleTrace}
                      disabled={tracing || !srcIp || !dstIp}
                      className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white py-2 rounded font-bold text-sm flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
                    >
                      {tracing ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} fill="currentColor" />}
                      Trace Path
                    </button>
                    {pathResult && (
                      <button onClick={clearTrace} className="px-3 bg-gray-700 hover:bg-gray-600 rounded text-white">
                        Clear
                      </button>
                    )}
                  </div>
                </div>

                {/* Result Summary */}
                {pathResult && (
                  <div className="border-t border-gray-700 pt-3">
                    {pathResult.status === 'success' ? (
                      <div className="text-green-400 text-sm font-bold flex items-center gap-2 mb-2">
                        <AlertCircle size={14} /> Path Found ({pathResult.path.length} Hops)
                      </div>
                    ) : (
                      <div className="text-yellow-400 text-sm font-bold flex items-center gap-2 mb-2">
                        <AlertCircle size={14} /> {pathResult.message || "Path Incomplete"}
                      </div>
                    )}

                    {pathResult?.path?.length > 1 && (
                      <div className="flex gap-2 mb-2">
                        <button
                          onClick={() => {
                            const next = !pathPlayback;
                            setPathPlayback(next);
                            if (next) setPathActiveEdgeIndex((i) => (i == null ? 0 : i));
                          }}
                          className="flex-1 px-3 py-2 bg-emerald-700 hover:bg-emerald-600 rounded text-white text-xs font-bold flex items-center justify-center gap-2"
                        >
                          {pathPlayback ? <Pause size={14} /> : <Play size={14} fill="currentColor" />}
                          {pathPlayback ? '일시정지' : '재생'}
                        </button>
                        <button
                          onClick={() => {
                            setPathPlayback(false);
                            setPathActiveEdgeIndex(null);
                          }}
                          className="px-3 py-2 bg-gray-700 hover:bg-gray-600 rounded text-white text-xs font-bold"
                        >
                          전체
                        </button>
                        <select
                          value={String(pathPlaybackSpeed)}
                          onChange={(e) => setPathPlaybackSpeed(Number(e.target.value))}
                          className="px-2 py-2 bg-[#0e1012] border border-gray-700 rounded text-white text-xs font-bold outline-none"
                          title="재생 속도"
                        >
                          <option value="0.5">0.5x</option>
                          <option value="1">1x</option>
                          <option value="2">2x</option>
                        </select>
                        <label className="flex items-center gap-2 px-2 py-2 bg-[#0e1012] border border-gray-700 rounded text-white text-xs font-bold select-none">
                          <input
                            type="checkbox"
                            checked={pathBadgesEnabled}
                            onChange={(e) => setPathBadgesEnabled(e.target.checked)}
                          />
                          배지
                        </label>
                        <select
                          value={String(pathEdgeLabelMaxLen)}
                          onChange={(e) => setPathEdgeLabelMaxLen(Number(e.target.value))}
                          className="px-2 py-2 bg-[#0e1012] border border-gray-700 rounded text-white text-xs font-bold outline-none"
                          title="링크 라벨 길이"
                        >
                          <option value="24">짧게</option>
                          <option value="42">보통</option>
                          <option value="60">길게</option>
                          <option value="90">전체</option>
                        </select>
                        <label className="flex items-center gap-2 px-2 py-2 bg-[#0e1012] border border-gray-700 rounded text-white text-xs font-bold select-none">
                          <input
                            type="checkbox"
                            checked={pathEdgeLabelTruncateMode === 'path'}
                            onChange={(e) => setPathEdgeLabelTruncateMode(e.target.checked ? 'path' : 'all')}
                          />
                          경로만
                        </label>
                      </div>
                    )}

                    <div className="max-h-52 overflow-y-auto space-y-2 text-xs">
                      {pathResult.path.map((node, i) => (
                        <div
                          key={i}
                          onClick={() => {
                            setPathPlayback(false);
                            const maxIdx = Math.max(0, (pathResult.path.length || 0) - 2);
                            setPathActiveEdgeIndex(Math.min(Math.max(0, i), maxIdx));
                          }}
                          className={`w-full text-left flex flex-col relative pl-4 border-l border-gray-700 pb-2 last:pb-0 rounded cursor-pointer ${pathActiveEdgeIndex != null && (i === pathActiveEdgeIndex || i === pathActiveEdgeIndex + 1) ? 'bg-white/5' : ''}`}
                        >
                          <div className={`absolute left-[-4px] top-0 w-2 h-2 rounded-full ${pathActiveEdgeIndex != null && (i === pathActiveEdgeIndex || i === pathActiveEdgeIndex + 1) ? 'bg-emerald-400' : 'bg-indigo-500'}`}></div>
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex-1 min-w-0">
                              <div className="font-bold text-gray-300 truncate">Hop {i + 1} · {node.name}</div>
                              <div className="text-gray-500 font-mono truncate">{node.ip}</div>
                            </div>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setPathEvidenceOpen((prev) => {
                                  const key = String(i);
                                  const next = { ...prev };
                                  next[key] = !next[key];
                                  return next;
                                });
                              }}
                              className="shrink-0 px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-200 text-[10px] font-bold flex items-center gap-1"
                            >
                              {pathEvidenceOpen[String(i)] ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                              증거
                            </button>
                          </div>
                          {node.ingress_intf && <div className="text-indigo-300 mt-0.5">In: {node.ingress_intf}</div>}
                          {node.egress_intf && <div className="text-indigo-300">Out: {node.egress_intf}</div>}

                          {(() => {
                            const { summaryText, detailLines } = buildEvidenceParts(node);
                            const open = !!pathEvidenceOpen[String(i)];
                            if (!summaryText && (!open || detailLines.length === 0)) return null;
                            return (
                              <div className="mt-1">
                                {summaryText && <div className="text-[10px] text-gray-400">{summaryText}</div>}
                                {open && detailLines.length > 0 && (
                                  <div className="mt-1 text-[10px] text-gray-200 bg-black/25 border border-gray-700 rounded p-2 space-y-0.5">
                                    {detailLines.map((t, idx) => (
                                      <div key={idx} className="break-all">{t}</div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            );
                          })()}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Panel>
          )}

          {showFlowInsight && (
            <Panel position="top-right" className={`m-4 ${showPathTrace ? 'mt-[520px]' : ''}`}>
              <div className="w-[min(52rem,calc(100vw-2rem))] bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 text-white">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="font-bold flex items-center gap-2">
                    <Activity size={18} className="text-emerald-400" /> Flow Insight (NetFlow v5)
                  </h3>
                  <button onClick={() => setShowFlowInsight(false)}>
                    <XCircle size={18} className="text-gray-500 hover:text-white" />
                  </button>
                </div>

                <div className="flex items-center gap-2 mb-3">
                  <select
                    value={flowWindowSec}
                    onChange={(e) => setFlowWindowSec(Number(e.target.value))}
                    className="bg-[#0e1012] border border-gray-700 rounded px-2 py-2 text-sm text-white outline-none"
                  >
                    <option value={60}>Last 60s</option>
                    <option value={300}>Last 5m</option>
                    <option value={900}>Last 15m</option>
                  </select>
                  <button
                    onClick={loadFlowInsight}
                    disabled={flowLoading}
                    className="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 rounded font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    <RefreshCw size={14} className={flowLoading ? "animate-spin" : ""} />
                    Refresh
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="border border-gray-700 rounded-lg overflow-hidden">
                    <div className="px-3 py-2 bg-black/30 border-b border-gray-700 text-sm font-bold">Top Talkers</div>
                    <div className="max-h-64 overflow-y-auto">
                      {flowTalkers.length === 0 ? (
                        <div className="p-3 text-sm text-gray-400">No flow data yet.</div>
                      ) : (
                        flowTalkers.map((t) => (
                          <div key={t.src_ip} className="px-3 py-2 border-b border-gray-700 last:border-b-0 flex items-center justify-between gap-2">
                            <div className="font-mono text-sm text-gray-200">{t.src_ip}</div>
                            <div className="text-xs text-gray-400">{formatBps(Number(t.bps || 0))}</div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                  <div className="border border-gray-700 rounded-lg overflow-hidden">
                    <div className="px-3 py-2 bg-black/30 border-b border-gray-700 text-sm font-bold flex items-center justify-between gap-2">
                      <span>Top Apps</span>
                      <select
                        value={flowSelectedApp}
                        onChange={(e) => setFlowSelectedApp(e.target.value)}
                        className="bg-[#0e1012] border border-gray-700 rounded px-2 py-1 text-xs text-white outline-none"
                        disabled={flowApps.length === 0}
                      >
                        {flowApps.length === 0 ? (
                          <option value="">-</option>
                        ) : (
                          flowApps.map((a) => (
                            <option key={a.app} value={String(a.app || '')}>
                              {String(a.app || '')}
                            </option>
                          ))
                        )}
                      </select>
                    </div>
                    <div className="max-h-64 overflow-y-auto">
                      {flowApps.length === 0 ? (
                        <div className="p-3 text-sm text-gray-400">No app data yet.</div>
                      ) : (
                        flowApps.map((a) => (
                          <button
                            type="button"
                            key={a.app}
                            onClick={() => setFlowSelectedApp(String(a.app || ''))}
                            className={`w-full text-left px-3 py-2 border-b border-gray-700 last:border-b-0 flex items-center justify-between gap-2 hover:bg-white/5 ${String(a.app || '') === String(flowSelectedApp || '') ? 'bg-white/10' : ''}`}
                          >
                            <div className="text-sm font-bold text-gray-200">{a.app}</div>
                            <div className="text-xs text-gray-400">{formatBps(Number(a.bps || 0))}</div>
                          </button>
                        ))
                      )}
                    </div>
                  </div>
                  <div className="border border-gray-700 rounded-lg overflow-hidden">
                    <div className="px-3 py-2 bg-black/30 border-b border-gray-700 text-sm font-bold">Top Flows</div>
                    <div className="max-h-64 overflow-y-auto">
                      {flowFlows.length === 0 ? (
                        <div className="p-3 text-sm text-gray-400">No flow data yet.</div>
                      ) : (
                        flowFlows.map((f, idx) => (
                          <div key={`${f.src_ip}-${f.dst_ip}-${f.src_port}-${f.dst_port}-${idx}`} className="px-3 py-2 border-b border-gray-700 last:border-b-0">
                            <div className="text-sm text-gray-200 font-mono truncate">
                              {f.src_ip}:{f.src_port} → {f.dst_ip}:{f.dst_port}
                            </div>
                            <div className="text-xs text-gray-400 mt-1 flex items-center justify-between">
                              <span>{f.app ? `${f.app} · ` : ''}proto {f.proto}</span>
                              <span>{formatBps(Number(f.bps || 0))}</span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-3 border border-gray-700 rounded-lg overflow-hidden">
                  <div className="px-3 py-2 bg-black/30 border-b border-gray-700 text-sm font-bold flex items-center justify-between gap-2">
                    <span>Selected App Flows</span>
                    <span className="text-xs text-gray-400">{flowSelectedApp || '-'}</span>
                  </div>
                  <div className="max-h-56 overflow-y-auto">
                    {flowAppLoading ? (
                      <div className="p-3 text-sm text-gray-400 flex items-center gap-2">
                        <RefreshCw size={14} className="animate-spin" /> Loading...
                      </div>
                    ) : flowSelectedAppFlows.length === 0 ? (
                      <div className="p-3 text-sm text-gray-400">No flows for selected app.</div>
                    ) : (
                      flowSelectedAppFlows.map((f, idx) => (
                        <div key={`${f.src_ip}-${f.dst_ip}-${f.src_port}-${f.dst_port}-${idx}`} className="px-3 py-2 border-b border-gray-700 last:border-b-0">
                          <div className="text-sm text-gray-200 font-mono truncate">
                            {f.src_ip}:{f.src_port} → {f.dst_ip}:{f.dst_port}
                          </div>
                          <div className="text-xs text-gray-400 mt-1 flex items-center justify-between">
                            <span>proto {f.proto}</span>
                            <span>{formatBps(Number(f.bps || 0))}</span>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </Panel>
          )}

          {endpointGroupPanel.open && (
            <Panel position="top-right" className={`m-4 ${showPathTrace ? 'mt-[520px]' : ''}`}>
              <div className="w-[min(24rem,calc(100vw-2rem))] bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 text-white">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="font-bold flex items-center gap-2">
                    <Layers size={18} className="text-cyan-400" /> Port Endpoints
                  </h3>
                  <button onClick={() => setEndpointGroupPanel({ open: false, loading: false, error: '', group: null, endpoints: [] })}>
                    <XCircle size={18} className="text-gray-500 hover:text-white" />
                  </button>
                </div>

                <div className="text-xs text-gray-300 mb-3">
                  <div className="font-mono">
                    device {endpointGroupPanel.group?.device_id} · port {endpointGroupPanel.group?.port}
                  </div>
                  {typeof endpointGroupPanel.group?.count === 'number' && (
                    <div className="text-gray-400 mt-1">endpoints: {endpointGroupPanel.group.count}</div>
                  )}
                </div>

                {endpointGroupPanel.loading && (
                  <div className="text-sm text-gray-400 flex items-center gap-2">
                    <RefreshCw size={14} className="animate-spin" /> Loading...
                  </div>
                )}

                {!!endpointGroupPanel.error && (
                  <div className="text-sm text-red-400">{endpointGroupPanel.error}</div>
                )}

                {!endpointGroupPanel.loading && !endpointGroupPanel.error && (
                  <div className="max-h-[360px] overflow-y-auto border border-gray-700 rounded-lg">
                    {endpointGroupPanel.endpoints.length === 0 ? (
                      <div className="p-3 text-sm text-gray-400">No endpoints found.</div>
                    ) : (
                      endpointGroupPanel.endpoints.map((ep) => (
                        <div key={ep.endpoint_id} className="p-3 border-b border-gray-700 last:border-b-0">
                          <div className="flex items-center justify-between gap-2">
                            <div className="min-w-0">
                              <div className="text-sm font-bold text-gray-200 truncate">
                                {ep.hostname || ep.ip_address || ep.mac_address}
                              </div>
                              <div className="text-[11px] text-gray-500 font-mono truncate">
                                {ep.mac_address}{ep.ip_address ? ` · ${ep.ip_address}` : ''}{ep.vlan ? ` · vlan ${ep.vlan}` : ''}
                              </div>
                              <div className="text-[11px] text-gray-400 mt-1 truncate">
                                {(ep.endpoint_type || 'unknown').toUpperCase()} · {ep.vendor || 'Unknown'}
                              </div>
                            </div>
                            <div className="flex flex-col items-end gap-1">
                              {ep.private_mac && (
                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-yellow-400 text-black font-bold">Private MAC</span>
                              )}
                              {!!ep.last_seen && (
                                <span className="text-[10px] text-gray-500">{ep.last_seen.slice(0, 19).replace('T', ' ')}</span>
                              )}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            </Panel>
          )}

          {showCandidates && (
            <Panel position="top-left" className="m-4">
              <div className="w-[min(520px,calc(100vw-2rem))] bg-[#1b1d1f] border border-gray-700 rounded-xl shadow-2xl overflow-hidden p-4 animate-slide-in-right text-white">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="font-bold flex items-center gap-2"><Link2 size={18} className="text-amber-400" /> Candidate Links</h3>
                  <button onClick={() => setShowCandidates(false)}><XCircle size={18} className="text-gray-500 hover:text-white" /></button>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-3">
                  <input
                    type="text"
                    value={candidateJobId}
                    onChange={(e) => setCandidateJobId(e.target.value)}
                    placeholder="Filter by discovery job id (optional)"
                    className="flex-1 bg-[#0e1012] border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-amber-500 outline-none font-mono"
                  />
                  <input
                    type="text"
                    value={candidateSearch}
                    onChange={(e) => setCandidateSearch(e.target.value)}
                    placeholder="Search (name/ip/reason)"
                    className="w-full sm:w-44 bg-[#0e1012] border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-amber-500 outline-none"
                  />
                  <select
                    value={candidateStatusFilter}
                    onChange={(e) => setCandidateStatusFilter(e.target.value)}
                    className="w-full sm:w-auto bg-[#0e1012] border border-gray-700 rounded px-2 py-2 text-sm text-white outline-none"
                  >
                    <option value="all">All</option>
                    <option value="unmatched">Unmatched</option>
                    <option value="promoted">Promoted</option>
                    <option value="ignored">Ignored</option>
                  </select>
                  <select
                    value={`${candidateOrderBy}:${candidateOrderDir}`}
                    onChange={(e) => {
                      const [ob, od] = e.target.value.split(':');
                      setCandidateOrderBy(ob);
                      setCandidateOrderDir(od);
                    }}
                    className="w-full sm:w-auto bg-[#0e1012] border border-gray-700 rounded px-2 py-2 text-sm text-white outline-none"
                  >
                    <option value="last_seen:desc">Last Seen ↓</option>
                    <option value="last_seen:asc">Last Seen ↑</option>
                    <option value="confidence:desc">Confidence ↓</option>
                    <option value="confidence:asc">Confidence ↑</option>
                  </select>
                  <button
                    onClick={loadCandidates}
                    disabled={candidateLoading}
                    className="w-full sm:w-auto px-3 py-2 bg-amber-600 hover:bg-amber-500 rounded font-bold text-sm flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    <RefreshCw size={14} className={candidateLoading ? "animate-spin" : ""} />
                    Refresh
                  </button>
                </div>

                <div className="flex items-center justify-between mb-3 text-xs text-gray-300">
                  <label className="flex items-center gap-2 select-none">
                    <input
                      type="checkbox"
                      checked={candidateAutoRefresh}
                      onChange={(e) => setCandidateAutoRefresh(e.target.checked)}
                    />
                    Auto refresh
                  </label>
                  <div className="flex items-center gap-2">
                    <button
                      disabled={selectedCandidateIds.length === 0}
                      onClick={async () => {
                        try {
                          const jobId = candidateJobId ? parseInt(candidateJobId, 10) : null;
                          if (!jobId) {
                            toast.warning("job id is required for bulk promote");
                            return;
                          }
                          const items = selectedCandidateIds.map((id) => {
                            const c = candidates.find((x) => x.id === id);
                            return {
                              candidate_id: id,
                              ip_address: (candidateEdits[id] ?? c?.mgmt_ip ?? '').trim(),
                              hostname: c?.neighbor_name,
                            };
                          });
                          await TopologyService.bulkPromoteCandidates(jobId, items);
                          setCandidates(prev => prev.map(x => selectedCandidateIds.includes(x.id) ? { ...x, status: 'promoted', mgmt_ip: (candidateEdits[x.id] ?? x.mgmt_ip) } : x));
                          navigate('/discovery', { state: { jobId } });
                        } catch (e) {
                          toast.error("Bulk promote failed: " + (e.response?.data?.detail || e.message));
                        }
                      }}
                      className="px-2 py-1 bg-green-600 hover:bg-green-500 rounded font-bold disabled:opacity-50"
                    >
                      Promote selected ({selectedCandidateIds.length})
                    </button>
                    <button
                      disabled={selectedCandidateIds.length === 0}
                      onClick={async () => {
                        try {
                          await TopologyService.bulkIgnoreCandidates(selectedCandidateIds);
                          setCandidates(prev => prev.map(x => selectedCandidateIds.includes(x.id) ? { ...x, status: 'ignored' } : x));
                          setSelectedCandidateIds([]);
                        } catch (e) {
                          toast.error("Bulk ignore failed");
                        }
                      }}
                      className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded font-bold disabled:opacity-50"
                    >
                      Ignore selected
                    </button>
                    <button
                      onClick={() => {
                        if (selectedCandidateIds.length === candidates.length) setSelectedCandidateIds([]);
                        else setSelectedCandidateIds(candidates.map(c => c.id));
                      }}
                      className="px-2 py-1 bg-[#0e1012] border border-gray-700 rounded font-bold"
                    >
                      {selectedCandidateIds.length === candidates.length && candidates.length > 0 ? "Clear" : "Select all"}
                    </button>
                  </div>
                </div>

                <div className="max-h-[420px] overflow-y-auto border border-gray-700 rounded-lg">
                  {candidates.length === 0 && !candidateLoading && (
                    <div className="p-4 text-sm text-gray-400">No candidates.</div>
                  )}
                  {candidates.map((c) => (
                    <div key={c.id} className="p-3 border-b border-gray-700 last:border-b-0">
                      <div className="flex justify-between items-start gap-3">
                        <div className="pt-1">
                          <input
                            type="checkbox"
                            checked={selectedCandidateIds.includes(c.id)}
                            onChange={(e) => {
                              setSelectedCandidateIds((prev) => {
                                if (e.target.checked) return Array.from(new Set([...prev, c.id]));
                                return prev.filter((id) => id !== c.id);
                              });
                            }}
                          />
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-gray-200 truncate">{c.neighbor_name}</div>
                          <div className="text-xs text-gray-400 mt-1">
                            src:{c.source_device_id} {c.local_interface || '?'} → {c.remote_interface || '?'} ({c.protocol || 'UNKNOWN'})
                          </div>
                          <div className="text-xs text-gray-500 mt-1">
                            {c.reason || 'unmatched'} · conf {Number(c.confidence || 0).toFixed(2)} · {c.last_seen || ''}
                          </div>
                        </div>

                        <div className="flex flex-col items-end gap-2">
                          <div className="flex items-center gap-2">
                            <input
                              type="text"
                              value={candidateEdits[c.id] ?? ''}
                              onChange={(e) => setCandidateEdits(prev => ({ ...prev, [c.id]: e.target.value }))}
                              placeholder="mgmt ip"
                              className="w-44 bg-[#0e1012] border border-gray-700 rounded px-2 py-1 text-xs text-white focus:border-amber-500 outline-none font-mono"
                            />
                            <button
                              onClick={async () => {
                                try {
                                  const isOpen = !!candidateRecOpen[c.id];
                                  if (isOpen) {
                                    setCandidateRecOpen(prev => ({ ...prev, [c.id]: false }));
                                    return;
                                  }

                                  setCandidateRecOpen(prev => ({ ...prev, [c.id]: true }));
                                  if (candidateRecommendations[c.id]?.length) return;

                                  setCandidateRecLoading(prev => ({ ...prev, [c.id]: true }));
                                  const res = await TopologyService.getCandidateRecommendations(c.id, { limit: 5 });
                                  setCandidateRecommendations(prev => ({ ...prev, [c.id]: Array.isArray(res.data) ? res.data : [] }));
                                } catch (e) {
                                  toast.error("Failed to load recommendations: " + (e.response?.data?.detail || e.message));
                                  setCandidateRecOpen(prev => ({ ...prev, [c.id]: false }));
                                } finally {
                                  setCandidateRecLoading(prev => ({ ...prev, [c.id]: false }));
                                }
                              }}
                              className="px-2 py-1 bg-[#0e1012] border border-gray-700 hover:border-amber-500 rounded text-xs font-bold"
                              title="추천 후보 보기"
                            >
                              {candidateRecLoading[c.id] ? "..." : "Suggest"}
                            </button>
                            <button
                              onClick={async () => {
                                try {
                                  const payload = {
                                    job_id: candidateJobId ? parseInt(candidateJobId, 10) : (c.discovery_job_id ?? undefined),
                                    ip_address: (candidateEdits[c.id] ?? '').trim(),
                                    hostname: c.neighbor_name,
                                  };
                                  await TopologyService.promoteCandidate(c.id, payload);
                                  setCandidates(prev => prev.map(x => x.id === c.id ? { ...x, status: 'promoted', mgmt_ip: payload.ip_address } : x));
                                  if (payload.job_id) {
                                    navigate('/discovery', { state: { jobId: payload.job_id } });
                                  }
                                } catch (e) {
                                  toast.error("Promote failed: " + (e.response?.data?.detail || e.message));
                                }
                              }}
                              className="px-2 py-1 bg-green-600 hover:bg-green-500 rounded text-xs font-bold flex items-center gap-1"
                            >
                              <CheckCircle size={12} /> Promote
                            </button>
                            <button
                              onClick={async () => {
                                try {
                                  await TopologyService.ignoreCandidate(c.id);
                                  setCandidates(prev => prev.map(x => x.id === c.id ? { ...x, status: 'ignored' } : x));
                                } catch (e) {
                                  toast.error("Ignore failed");
                                }
                              }}
                              className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs font-bold"
                            >
                              Ignore
                            </button>
                          </div>
                          {candidateRecOpen[c.id] && (
                            <div className="w-full">
                              {(candidateRecommendations[c.id]?.length ?? 0) === 0 ? (
                                <div className="text-[11px] text-gray-500 text-right">No suggestions</div>
                              ) : (
                                <div className="flex flex-col gap-1">
                                  {candidateRecommendations[c.id].map((r) => (
                                    <button
                                      key={r.discovered_id}
                                      onClick={async () => {
                                        setCandidateActionError(prev => ({ ...prev, [c.id]: '' }));
                                        try {
                                          const ip = (r.ip_address || '').trim();
                                          if (!ip) return;
                                          setCandidateEdits(prev => ({ ...prev, [c.id]: ip }));
                                          const payload = {
                                            job_id: c.discovery_job_id ?? undefined,
                                            ip_address: ip,
                                            hostname: r.hostname || c.neighbor_name,
                                          };
                                          const promoted = await TopologyService.promoteCandidate(c.id, payload);
                                          const discoveredId = promoted?.data?.discovered_id;
                                          if (discoveredId) {
                                            try {
                                              await DiscoveryService.approveDevice(discoveredId);
                                            } catch (e) {
                                              const msg = e.response?.data?.detail || e.message || "Approve failed";
                                              setCandidateActionError(prev => ({ ...prev, [c.id]: String(msg) }));
                                              setCandidates(prev => prev.map(x => x.id === c.id ? { ...x, status: 'promoted', mgmt_ip: payload.ip_address } : x));
                                              return;
                                            }
                                          }
                                          setCandidates(prev => prev.map(x => x.id === c.id ? { ...x, status: 'approved', mgmt_ip: payload.ip_address } : x));
                                          if (payload.job_id) navigate('/discovery', { state: { jobId: payload.job_id } });
                                        } catch (e) {
                                          const msg = e.response?.data?.detail || e.message || "Promote failed";
                                          setCandidateActionError(prev => ({ ...prev, [c.id]: String(msg) }));
                                        }
                                      }}
                                      className="text-left px-2 py-1 bg-[#0e1012] border border-gray-700 rounded hover:border-amber-500"
                                      title="클릭하면 자동으로 mgmt ip를 채우고 Promote"
                                    >
                                      <div className="flex items-center justify-between gap-2">
                                        <div className="min-w-0">
                                          <div className="text-[11px] text-gray-300 truncate">{r.hostname || r.ip_address}</div>
                                          <div className="text-[10px] text-gray-500 font-mono truncate">{r.ip_address} · {r.vendor || 'Unknown'} · score {Number(r.score || 0).toFixed(2)}</div>
                                        </div>
                                        <div className="text-[10px] text-amber-400 font-bold">Use</div>
                                      </div>
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                          {!!candidateActionError[c.id] && (
                            <div className="text-[11px] text-red-400 text-right max-w-[320px] break-words">
                              {candidateActionError[c.id]}
                            </div>
                          )}
                          <div className="text-xs text-gray-500">{c.status || 'unmatched'}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </Panel>
          )}
        </ReactFlow>

        {/* Tooltip */}
        {tooltip && (
          <div
            className="fixed z-50 bg-black/80 text-white text-xs p-3 rounded-lg shadow-xl backdrop-blur-sm pointer-events-none transform -translate-x-1/2 -translate-y-full mt-[-10px]"
            style={{ left: tooltip.x, top: tooltip.y }}
          >
            <div className="font-bold mb-1 border-b border-gray-600 pb-1 text-yellow-400">
              🔗 {tooltip.label}
            </div>
            <ul className="space-y-0.5">
              {tooltip.content.map((port, idx) => (
                <li key={idx} className="whitespace-nowrap flex items-center gap-2">
                  <span className="w-1 h-1 bg-green-400 rounded-full inline-block"></span>
                  {port}
                </li>
              ))}
            </ul>
          </div>
        )}

      </div>
    </div>
  );
};

export default TopologyPage;
