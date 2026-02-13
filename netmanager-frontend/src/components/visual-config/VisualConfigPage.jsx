import React, { useEffect, useMemo, useState } from 'react';
import ReactFlow, { Background, Controls, MiniMap, useEdgesState, useNodesState } from 'reactflow';
import 'reactflow/dist/style.css';
import { VisualConfigService } from '../../api/services';
import { DeviceService } from '../../api/services';
import { CheckCircle, AlertTriangle, Plus, Save, Eye, Play, BookOpen, ClipboardCopy, Clock, RotateCcw, RefreshCw } from 'lucide-react';
import { useToast } from '../../context/ToastContext';

const emptyGraph = { nodes: [], edges: [], viewport: null };

const defaultNodeData = (type) => {
  if (type === 'vlan') return { vlan_id: 10, name: 'Users', svi_ip: '', vrf: '', dhcp_relay: '' };
  if (type === 'interface') return { ports: 'Gi1/0/1', description: '', admin_state: 'up', mode: 'access', access_vlan: 10, native_vlan: 1, allowed_vlans: '10,20' };
  if (type === 'l2_safety') return { ports: 'Gi1/0/1', portfast: true, bpduguard: true, storm_control: '' };
  if (type === 'acl') return { name: 'WEB', entries: [{ action: 'permit', proto: 'tcp', src: 'any', dst: 'host 10.0.0.10', dport: '443' }] };
  if (type === 'ospf') return { process_id: 1, networks: [{ ip: '10.0.0.0', wildcard: '0.0.0.255', area: '0' }] };
  if (type === 'route') return { destination: '0.0.0.0', mask: '0.0.0.0', next_hop: '10.0.0.1' };
  if (type === 'global') return {
    hostname: 'Switch01', banner: '',
    snmp: { communities: [], trap_server: '' },
    ntp: { servers: [] },
    logging: { servers: [], level: 'informational' },
    aaa: { tacacs_servers: [] },
    users: []
  };
  if (type === 'target') return { target_type: 'devices', device_ids: [] };
  return {};
};

const validateGraph = (nodes, edges) => {
  const errorsById = {};

  const pushErr = (id, msg) => {
    errorsById[id] = errorsById[id] || [];
    errorsById[id].push(msg);
  };

  const byType = {};
  for (const n of nodes) {
    byType[n.type] = byType[n.type] || [];
    byType[n.type].push(n);
  }

  if (!byType.target || byType.target.length === 0) {
    errorsById.__global = ['Target 블록이 필요합니다.'];
  }

  for (const n of nodes) {
    const d = n.data || {};
    if (n.type === 'vlan') {
      const vid = Number(d.vlan_id);
      if (!Number.isInteger(vid) || vid < 1 || vid > 4094) pushErr(n.id, 'VLAN ID는 1~4094 정수여야 합니다.');
      if (!String(d.name || '').trim()) pushErr(n.id, 'VLAN Name이 필요합니다.');
    }
    if (n.type === 'interface') {
      if (!String(d.ports || '').trim()) pushErr(n.id, 'Ports가 필요합니다.');
      if (!['up', 'down'].includes(String(d.admin_state || 'up'))) pushErr(n.id, 'Admin state는 up/down이어야 합니다.');
      if (!['access', 'trunk'].includes(String(d.mode || 'access'))) pushErr(n.id, 'Mode는 access/trunk이어야 합니다.');
      if (String(d.mode || 'access') === 'access') {
        const av = Number(d.access_vlan);
        if (!Number.isInteger(av) || av < 1 || av > 4094) pushErr(n.id, 'Access VLAN은 1~4094 정수여야 합니다.');
      }
      if (String(d.mode || 'access') === 'trunk') {
        const nv = Number(d.native_vlan);
        if (!Number.isInteger(nv) || nv < 1 || nv > 4094) pushErr(n.id, 'Native VLAN은 1~4094 정수여야 합니다.');
        if (!String(d.allowed_vlans || '').trim()) pushErr(n.id, 'Allowed VLANs가 필요합니다.');
      }
    }
    if (n.type === 'l2_safety') {
      if (!String(d.ports || '').trim()) pushErr(n.id, 'Ports가 필요합니다.');
    }
    if (n.type === 'acl') {
      if (!String(d.name || '').trim()) pushErr(n.id, 'ACL Name이 필요합니다.');
      if (!Array.isArray(d.entries) || d.entries.length === 0) pushErr(n.id, 'ACL entries가 필요합니다.');
    }
    if (n.type === 'target') {
      if (String(d.target_type || 'devices') !== 'devices') pushErr(n.id, '현재 Target은 devices만 지원합니다.');
      if (!Array.isArray(d.device_ids) || d.device_ids.length === 0) pushErr(n.id, '대상 장비를 1대 이상 선택해야 합니다.');
    }
  }

  for (const e of edges) {
    if (!e.source || !e.target) continue;
    if (e.source === e.target) {
      errorsById.__global = errorsById.__global || [];
      errorsById.__global.push('자기 자신으로 연결된 엣지가 있습니다.');
    }
  }

  return errorsById;
};

const NODE_COLORS = {
  vlan: { border: 'border-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/30', accent: 'text-blue-700', dot: 'bg-blue-500' },
  interface: { border: 'border-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-900/30', accent: 'text-emerald-700', dot: 'bg-emerald-500' },
  l2_safety: { border: 'border-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/30', accent: 'text-amber-700', dot: 'bg-amber-500' },
  acl: { border: 'border-red-400', bg: 'bg-red-50 dark:bg-red-900/30', accent: 'text-red-700', dot: 'bg-red-500' },
  ospf: { border: 'border-orange-400', bg: 'bg-orange-50 dark:bg-orange-900/30', accent: 'text-orange-700', dot: 'bg-orange-500' },
  route: { border: 'border-teal-400', bg: 'bg-teal-50 dark:bg-teal-900/30', accent: 'text-teal-700', dot: 'bg-teal-500' },
  global: { border: 'border-slate-400', bg: 'bg-slate-50 dark:bg-slate-800', accent: 'text-slate-700', dot: 'bg-slate-500' },
  target: { border: 'border-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/30', accent: 'text-purple-700', dot: 'bg-purple-500' },
};

const NodeCard = ({ title, subtitle, status, nodeType }) => {
  const colors = NODE_COLORS[nodeType] || NODE_COLORS.vlan;
  const borderCls = status === 'error' ? 'border-red-400' : colors.border;
  const bgCls = status === 'error' ? 'bg-red-50' : colors.bg;
  return (
    <div className={`rounded-lg border-2 ${borderCls} ${bgCls} px-3 py-2 shadow-sm min-w-[160px]`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${colors.dot}`} />
          <span className={`font-bold text-sm ${colors.accent}`}>{title}</span>
        </div>
        {status === 'error' ? <AlertTriangle size={14} className="text-red-600" /> : <CheckCircle size={14} className="text-green-600" />}
      </div>
      {subtitle ? <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">{subtitle}</div> : null}
    </div>
  );
};

const VlanNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  return <NodeCard title={`VLAN ${data?.vlan_id ?? '-'}`} subtitle={String(data?.name || '')} status={status} nodeType="vlan" />;
};

const InterfaceNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const mode = String(data?.mode || 'access');
  const sub = mode === 'access' ? `${data?.ports || '-'} / vlan ${data?.access_vlan ?? '-'}` : `${data?.ports || '-'} / trunk`;
  return <NodeCard title="Interface" subtitle={sub} status={status} nodeType="interface" />;
};

const L2SafetyNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const sub = `${data?.ports || '-'} / PF:${data?.portfast ? 'Y' : 'N'} BG:${data?.bpduguard ? 'Y' : 'N'}`;
  return <NodeCard title="L2 Safety" subtitle={sub} status={status} nodeType="l2_safety" />;
};

const AclNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const sub = `${data?.name || '-'} (${Array.isArray(data?.entries) ? data.entries.length : 0} rules)`;
  return <NodeCard title="ACL" subtitle={sub} status={status} nodeType="acl" />;
};

const OspfNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const nets = Array.isArray(data?.networks) ? data.networks.length : 0;
  return <NodeCard title={`OSPF (PID ${data?.process_id ?? '-'})`} subtitle={`${nets} network(s)`} status={status} nodeType="ospf" />;
};

const RouteNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  return <NodeCard title="Static Route" subtitle={`${data?.destination || '0.0.0.0'} → ${data?.next_hop || '-'}`} status={status} nodeType="route" />;
};

const GlobalConfigNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  return <NodeCard title="Global Config" subtitle={data?.hostname || 'System Settings'} status={status} nodeType="global" />;
};

const TargetNode = ({ data }) => {
  const status = data?.__errors?.length ? 'error' : 'ok';
  const sub = `${Array.isArray(data?.device_ids) ? data.device_ids.length : 0}대 선택됨`;
  return <NodeCard title="🎯 Target" subtitle={sub} status={status} nodeType="target" />;
};

const TabButton = ({ active, onClick, children }) => (
  <button
    onClick={onClick}
    className={`px-3 py-2 rounded-lg text-sm font-bold border ${active
      ? 'bg-blue-600 text-white border-blue-600'
      : 'bg-white dark:bg-black/20 text-gray-700 dark:text-gray-200 border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30'
      }`}
  >
    {children}
  </button>
);

export default function VisualConfigPage() {
  const { toast } = useToast();
  const [blueprints, setBlueprints] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedMeta, setSelectedMeta] = useState(null);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [validation, setValidation] = useState({});
  const [devices, setDevices] = useState([]);
  const [preview, setPreview] = useState(null);
  const [deploy, setDeploy] = useState(null);
  const [rightTab, setRightTab] = useState('inspector'); // inspector|preview|deploy|guide
  const [inspectorTab, setInspectorTab] = useState('general'); // general|mgmt|security
  const [historyJobs, setHistoryJobs] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  const loadBlueprints = async () => {
    const res = await VisualConfigService.getBlueprints();
    setBlueprints(res.data || []);
  };

  useEffect(() => {
    loadBlueprints().catch(() => { });
    DeviceService.getDevices().then((res) => setDevices(res.data || [])).catch(() => { });
  }, []);

  const selected = useMemo(() => blueprints.find(b => b.id === selectedId) || null, [blueprints, selectedId]);

  const loadBlueprint = async (id) => {
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.getBlueprint(id);
      setSelectedId(res.data.id);
      setSelectedMeta({ name: res.data.name, description: res.data.description, current_version: res.data.current_version });
      const g = res.data.graph || emptyGraph;
      setNodes(g.nodes || []);
      setEdges(g.edges || []);
      setSelectedNodeId(null);
      setValidation({});
      setPreview(null);
      setDeploy(null);
      setRightTab('inspector');
      setHistoryJobs([]);
      setHistoryLoading(false);
      setTimeout(() => {
        loadHistory(id).catch(() => { });
      }, 0);
    } catch (e) {
      setError('Failed to load blueprint');
    } finally {
      setBusy(false);
    }
  };

  const createBlueprint = async () => {
    const name = newName.trim();
    if (!name) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.createBlueprint({
        name,
        description: newDesc.trim() || null,
        graph: { nodes, edges, viewport: null },
      });
      setNewName('');
      setNewDesc('');
      await loadBlueprints();
      await loadBlueprint(res.data.id);
    } catch (e) {
      setError('Failed to create blueprint');
    } finally {
      setBusy(false);
    }
  };

  const saveVersion = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.createVersion(selectedId, { graph: { nodes, edges, viewport: null } });
      setSelectedMeta({ name: res.data.name, description: res.data.description, current_version: res.data.current_version });
      await loadBlueprints();
      setPreview(null);
      setDeploy(null);
      setRightTab('inspector');
    } catch (e) {
      setError('Failed to save version');
    } finally {
      setBusy(false);
    }
  };

  const deleteBlueprint = async () => {
    if (!selectedId) return;
    const ok = window.confirm('Delete this blueprint?');
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      await VisualConfigService.deleteBlueprint(selectedId);
      setSelectedId(null);
      setSelectedMeta(null);
      setNodes([]);
      setEdges([]);
      setPreview(null);
      setDeploy(null);
      setRightTab('inspector');
      await loadBlueprints();
    } catch (e) {
      setError('Failed to delete blueprint');
    } finally {
      setBusy(false);
    }
  };

  const loadHistory = async (blueprintId = selectedId) => {
    if (!blueprintId) return;
    setHistoryLoading(true);
    try {
      const res = await VisualConfigService.listDeployJobsForBlueprint(blueprintId, { limit: 50, skip: 0 });
      setHistoryJobs(res.data || []);
    } catch (e) {
      setHistoryJobs([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  const nodeTypes = useMemo(() => ({
    vlan: VlanNode,
    interface: InterfaceNode,
    l2_safety: L2SafetyNode,
    acl: AclNode,
    ospf: OspfNode,
    route: RouteNode,
    global: GlobalConfigNode,
    target: TargetNode,
  }), []);

  const addNode = (type) => {
    const id = `${type}-${Date.now()}`;
    const baseX = 200 + Math.round(Math.random() * 240);
    const baseY = 120 + Math.round(Math.random() * 240);
    setNodes((nds) => nds.concat([{ id, type, position: { x: baseX, y: baseY }, data: defaultNodeData(type) }]));
    setSelectedNodeId(id);
  };

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) || null, [nodes, selectedNodeId]);

  const updateSelectedNodeData = (patch) => {
    if (!selectedNodeId) return;
    setNodes((nds) =>
      nds.map((n) => (n.id === selectedNodeId ? { ...n, data: { ...(n.data || {}), ...patch } } : n))
    );
  };

  const runValidate = () => {
    const errs = validateGraph(nodes, edges);
    setValidation(errs);
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: { ...(n.data || {}), __errors: errs[n.id] || [] },
      }))
    );
    if (errs.__global && errs.__global.length) {
      toast.warning(errs.__global.join('\n'));
    }
  };

  const runPreview = async () => {
    if (!selectedId) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.previewBlueprint(selectedId);
      setPreview(res.data);
      setRightTab('preview');
      if (Array.isArray(res.data?.errors) && res.data.errors.length > 0) {
        toast.warning(res.data.errors.join('\n'));
      }
      if (res.data?.errors_by_node_id) {
        const errs = res.data.errors_by_node_id;
        setValidation((prev) => ({ ...prev, ...errs }));
        setNodes((nds) =>
          nds.map((n) => ({
            ...n,
            data: { ...(n.data || {}), __errors: errs[n.id] || [] },
          }))
        );
      }
    } catch (e) {
      setError('Failed to preview');
      setPreview(null);
      toast.error('Failed to preview');
    } finally {
      setBusy(false);
    }
  };

  const runDeploy = async () => {
    if (!selectedId) return;
    const ok = window.confirm('Deploy this blueprint to selected devices?');
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.deployBlueprint(selectedId, { save_backup: true });
      setDeploy({ job_id: res.data.job_id, status: res.data.status, results: res.data.results || [], details: null });
      setRightTab('deploy');
      try {
        const det = await VisualConfigService.getDeployJob(res.data.job_id);
        setDeploy(prev => ({ ...(prev || {}), details: det.data }));
      } catch (e) {
        // ignore
      }
      loadHistory(selectedId).catch(() => { });
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === 'object' && (detail.errors || detail.errors_by_node_id)) {
        if (Array.isArray(detail.errors) && detail.errors.length) toast.error(detail.errors.join('\n'));
        if (detail.errors_by_node_id) {
          const errs = detail.errors_by_node_id;
          setValidation((prev) => ({ ...prev, ...errs }));
          setNodes((nds) =>
            nds.map((n) => ({
              ...n,
              data: { ...(n.data || {}), __errors: errs[n.id] || [] },
            }))
          );
        }
      } else {
        setError('Failed to deploy');
        toast.error('Failed to deploy');
      }
      setDeploy(null);
    } finally {
      setBusy(false);
    }
  };

  const renderInspector = () => {
    if (!selectedNode) {
      return <div className="text-sm text-gray-500">노드를 선택하세요.</div>;
    }
    const t = selectedNode.type;
    const d = selectedNode.data || {};
    const errs = Array.isArray(d.__errors) ? d.__errors : [];

    const header = (
      <div className="mb-3">
        <div className="font-bold text-lg">{t}</div>
        <div className="text-xs text-gray-500">id: {selectedNode.id}</div>
        {errs.length > 0 ? (
          <div className="mt-2 space-y-1">
            {errs.map((e, idx) => (
              <div key={`${idx}-${e}`} className="text-xs text-red-600 flex items-center gap-1">
                <AlertTriangle size={12} /> {e}
              </div>
            ))}
          </div>
        ) : null}
      </div>
    );

    const input = (label, value, onChange, opts = {}) => (
      <div className="space-y-1">
        <div className="text-xs font-bold text-gray-700 dark:text-gray-200">{label}</div>
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20"
          {...opts}
        />
      </div>
    );

    const select = (label, value, onChange, items) => (
      <div className="space-y-1">
        <div className="text-xs font-bold text-gray-700 dark:text-gray-200">{label}</div>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20"
        >
          {items.map((it) => (
            <option key={it.value} value={it.value}>{it.label}</option>
          ))}
        </select>
      </div>
    );

    const checkbox = (label, checked, onChange) => (
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={!!checked} onChange={(e) => onChange(e.target.checked)} />
        <span>{label}</span>
      </label>
    );

    if (t === 'vlan') {
      return (
        <div className="space-y-3">
          {header}
          {input('VLAN ID', String(d.vlan_id ?? ''), (v) => updateSelectedNodeData({ vlan_id: Number(v) }), { inputMode: 'numeric' })}
          {input('Name', String(d.name ?? ''), (v) => updateSelectedNodeData({ name: v }))}
          {input('SVI IP (optional)', String(d.svi_ip ?? ''), (v) => updateSelectedNodeData({ svi_ip: v }))}
          {input('VRF (optional)', String(d.vrf ?? ''), (v) => updateSelectedNodeData({ vrf: v }))}
          {input('DHCP Relay (optional)', String(d.dhcp_relay ?? ''), (v) => updateSelectedNodeData({ dhcp_relay: v }))}
        </div>
      );
    }

    if (t === 'interface') {
      return (
        <div className="space-y-3">
          {header}
          {input('Ports', String(d.ports ?? ''), (v) => updateSelectedNodeData({ ports: v }))}
          {input('Description', String(d.description ?? ''), (v) => updateSelectedNodeData({ description: v }))}
          {select('Admin State', String(d.admin_state || 'up'), (v) => updateSelectedNodeData({ admin_state: v }), [
            { value: 'up', label: 'up' },
            { value: 'down', label: 'down' },
          ])}
          {select('Mode', String(d.mode || 'access'), (v) => updateSelectedNodeData({ mode: v }), [
            { value: 'access', label: 'access' },
            { value: 'trunk', label: 'trunk' },
          ])}
          {String(d.mode || 'access') === 'access' ? (
            input('Access VLAN', String(d.access_vlan ?? ''), (v) => updateSelectedNodeData({ access_vlan: Number(v) }), { inputMode: 'numeric' })
          ) : (
            <div className="space-y-3">
              {input('Native VLAN', String(d.native_vlan ?? ''), (v) => updateSelectedNodeData({ native_vlan: Number(v) }), { inputMode: 'numeric' })}
              {input('Allowed VLANs', String(d.allowed_vlans ?? ''), (v) => updateSelectedNodeData({ allowed_vlans: v }))}
            </div>
          )}
        </div>
      );
    }

    if (t === 'l2_safety') {
      return (
        <div className="space-y-3">
          {header}
          {input('Ports', String(d.ports ?? ''), (v) => updateSelectedNodeData({ ports: v }))}
          <div className="space-y-2">
            {checkbox('portfast', d.portfast, (v) => updateSelectedNodeData({ portfast: v }))}
            {checkbox('bpduguard', d.bpduguard, (v) => updateSelectedNodeData({ bpduguard: v }))}
          </div>
          {input('storm-control (optional)', String(d.storm_control ?? ''), (v) => updateSelectedNodeData({ storm_control: v }))}
        </div>
      );
    }

    if (t === 'acl') {
      const entries = Array.isArray(d.entries) ? d.entries : [];
      const first = entries[0] || { action: 'permit', proto: 'tcp', src: 'any', dst: 'any', dport: '' };
      return (
        <div className="space-y-3">
          {header}
          {input('Name', String(d.name ?? ''), (v) => updateSelectedNodeData({ name: v }))}
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3 space-y-2">
            <div className="text-xs font-bold text-gray-700 dark:text-gray-200">First Entry (MVP)</div>
            {select('Action', String(first.action || 'permit'), (v) => updateSelectedNodeData({ entries: [{ ...first, action: v }] }), [
              { value: 'permit', label: 'permit' },
              { value: 'deny', label: 'deny' },
            ])}
            {input('Proto', String(first.proto || 'tcp'), (v) => updateSelectedNodeData({ entries: [{ ...first, proto: v }] }))}
            {input('Src', String(first.src || 'any'), (v) => updateSelectedNodeData({ entries: [{ ...first, src: v }] }))}
            {input('Dst', String(first.dst || 'any'), (v) => updateSelectedNodeData({ entries: [{ ...first, dst: v }] }))}
            {input('Dst Port', String(first.dport || ''), (v) => updateSelectedNodeData({ entries: [{ ...first, dport: v }] }))}
          </div>
        </div>
      );
    }

    if (t === 'ospf') {
      const nets = Array.isArray(d.networks) ? d.networks : [];
      const first = nets[0] || { ip: '10.0.0.0', wildcard: '0.0.0.255', area: '0' };
      return (
        <div className="space-y-3">
          {header}
          {input('Process ID', String(d.process_id ?? ''), (v) => updateSelectedNodeData({ process_id: Number(v) }), { inputMode: 'numeric' })}
          <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3 space-y-2">
            <div className="text-xs font-bold text-gray-700 dark:text-gray-200">Network (첫번째)</div>
            {input('Network IP', String(first.ip || ''), (v) => updateSelectedNodeData({ networks: [{ ...first, ip: v }] }))}
            {input('Wildcard', String(first.wildcard || ''), (v) => updateSelectedNodeData({ networks: [{ ...first, wildcard: v }] }))}
            {input('Area', String(first.area || ''), (v) => updateSelectedNodeData({ networks: [{ ...first, area: v }] }))}
          </div>
        </div>
      );
    }

    if (t === 'route') {
      return (
        <div className="space-y-3">
          {header}
          {input('Destination', String(d.destination ?? ''), (v) => updateSelectedNodeData({ destination: v }))}
          {input('Mask', String(d.mask ?? ''), (v) => updateSelectedNodeData({ mask: v }))}
          {input('Next Hop', String(d.next_hop ?? ''), (v) => updateSelectedNodeData({ next_hop: v }))}
        </div>
      );
    }

    if (t === 'global') {
      const snmp = d.snmp || { communities: [], trap_server: '' };
      const ntp = d.ntp || { servers: [] };
      const logging = d.logging || { servers: [], level: 'informational' };
      const aaa = d.aaa || { tacacs_servers: [] };
      const users = d.users || []; // array of { username, privilege, secret }

      // Helper to update deeply nested
      const updateSnmp = (patch) => updateSelectedNodeData({ snmp: { ...snmp, ...patch } });
      const updateNtp = (patch) => updateSelectedNodeData({ ntp: { ...ntp, ...patch } });
      const updateLogging = (patch) => updateSelectedNodeData({ logging: { ...logging, ...patch } });
      const updateAaa = (patch) => updateSelectedNodeData({ aaa: { ...aaa, ...patch } });

      return (
        <div className="space-y-3">
          {header}
          <div className="flex border-b border-gray-200 dark:border-gray-800 mb-3">
            <button onClick={() => setInspectorTab('general')} className={`flex-1 py-1 text-xs font-bold border-b-2 ${inspectorTab === 'general' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500'}`}>General</button>
            <button onClick={() => setInspectorTab('mgmt')} className={`flex-1 py-1 text-xs font-bold border-b-2 ${inspectorTab === 'mgmt' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500'}`}>Mgmt</button>
            <button onClick={() => setInspectorTab('security')} className={`flex-1 py-1 text-xs font-bold border-b-2 ${inspectorTab === 'security' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500'}`}>Security</button>
          </div>

          {inspectorTab === 'general' && (
            <div className="space-y-3">
              {input('Hostname', String(d.hostname || ''), (v) => updateSelectedNodeData({ hostname: v }))}
              {input('Domain Name', String(d.domain_name || ''), (v) => updateSelectedNodeData({ domain_name: v }))}
              <div className="space-y-1">
                <div className="text-xs font-bold text-gray-700 dark:text-gray-200">Banner (MOTD/Login)</div>
                <textarea
                  value={d.banner || ''}
                  onChange={(e) => updateSelectedNodeData({ banner: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 text-xs h-20"
                />
              </div>
            </div>
          )}

          {inspectorTab === 'mgmt' && (
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="text-xs font-bold text-blue-600">SNMP</div>
                {/* Simple 1 RO/RW for MVP */}
                {input('Community (RO)', String(snmp.communities.find(c => c.mode === 'ro')?.name || ''), (v) => {
                  const others = snmp.communities.filter(c => c.mode !== 'ro');
                  updateSnmp({ communities: v ? [...others, { name: v, mode: 'ro' }] : others });
                })}
                {input('Community (RW)', String(snmp.communities.find(c => c.mode === 'rw')?.name || ''), (v) => {
                  const others = snmp.communities.filter(c => c.mode !== 'rw');
                  updateSnmp({ communities: v ? [...others, { name: v, mode: 'rw' }] : others });
                })}
                {input('Trap Server', String(snmp.trap_server || ''), (v) => updateSnmp({ trap_server: v }))}
              </div>
              <div className="space-y-2">
                <div className="text-xs font-bold text-blue-600">NTP</div>
                {input('NTP Server (Primary)', String(ntp.servers[0] || ''), (v) => updateNtp({ servers: v ? [v] : [] }))}
              </div>
              <div className="space-y-2">
                <div className="text-xs font-bold text-blue-600">Syslog</div>
                {input('Syslog Server', String(logging.servers[0] || ''), (v) => updateLogging({ servers: v ? [v] : [] }))}
              </div>
            </div>
          )}

          {inspectorTab === 'security' && (
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="text-xs font-bold text-red-600">TACACS+ (AAA)</div>
                {/* Single Server MVP */}
                {input('Server IP', String(aaa.tacacs_servers[0]?.ip || ''), (v) => {
                  const old = aaa.tacacs_servers[0] || { name: 'TACACS1', key: '' };
                  updateAaa({ tacacs_servers: v ? [{ ...old, ip: v }] : [] });
                })}
                {aaa.tacacs_servers[0]?.ip && input('Key', String(aaa.tacacs_servers[0]?.key || ''), (v) => {
                  const old = aaa.tacacs_servers[0];
                  updateAaa({ tacacs_servers: [{ ...old, key: v }] });
                }, { type: 'password' })}
              </div>
              <div className="space-y-2">
                <div className="text-xs font-bold text-red-600">Local Users</div>
                {/* Single User MVP */}
                {input('Username', String(users[0]?.username || ''), (v) => {
                  const old = users[0] || { privilege: 15, secret: '' };
                  updateSelectedNodeData({ users: v ? [{ ...old, username: v }] : [] });
                })}
                {users[0]?.username && input('Secret', String(users[0]?.secret || ''), (v) => {
                  const old = users[0];
                  updateSelectedNodeData({ users: [{ ...old, secret: v }] });
                }, { type: 'password' })}
              </div>
            </div>
          )}
        </div>
      );
    }

    if (t === 'target') {
      const ids = Array.isArray(d.device_ids) ? d.device_ids : [];
      const toggleDevice = (id) => {
        const next = ids.includes(id) ? ids.filter((x) => x !== id) : ids.concat([id]);
        updateSelectedNodeData({ device_ids: next });
      };
      return (
        <div className="space-y-3">
          {header}
          <div className="text-xs text-gray-500">대상 장비 선택</div>
          <div className="max-h-[420px] overflow-y-auto space-y-2">
            {devices.length === 0 ? (
              <div className="text-sm text-gray-500">장비 목록이 없습니다.</div>
            ) : devices.map((dev) => (
              <label key={dev.id} className="flex items-center justify-between gap-2 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20">
                <div className="text-sm">
                  <div className="font-bold">{dev.name || dev.hostname || `Device ${dev.id}`}</div>
                  <div className="text-xs text-gray-500 font-mono">{dev.ip_address} ({dev.device_type || 'unknown'})</div>
                </div>
                <input type="checkbox" checked={ids.includes(dev.id)} onChange={() => toggleDevice(dev.id)} />
              </label>
            ))}
          </div>
        </div>
      );
    }

    return (
      <div className="space-y-3">
        {header}
        <div className="text-sm text-gray-500">지원되지 않는 노드 타입입니다.</div>
      </div>
    );
  };

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success('클립보드에 복사했습니다.');
    } catch (e) {
      toast.error('클립보드 복사에 실패했습니다.');
    }
  };

  const renderPreviewPanel = () => {
    if (!preview) return <div className="text-sm text-gray-500">미리보기를 실행하면 장비별 CLI가 표시됩니다.</div>;
    if (!Array.isArray(preview?.devices) || preview.devices.length === 0) return <div className="text-sm text-gray-500">대상 장비가 없거나 오류가 있습니다.</div>;
    return (
      <div className="space-y-3">
        {preview.devices.map((d) => {
          const text = (d.commands || []).join('\n');
          return (
            <div key={d.device_id} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 overflow-hidden">
              <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between gap-2">
                <div>
                  <div className="font-bold text-sm">{d.name || `Device ${d.device_id}`}</div>
                  <div className="text-xs text-gray-500 font-mono">{d.ip_address} / {d.device_type}</div>
                </div>
                <button
                  onClick={() => copyText(text)}
                  className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30 text-xs font-bold flex items-center gap-2"
                >
                  <ClipboardCopy size={14} /> Copy
                </button>
              </div>
              <pre className="p-3 text-xs overflow-x-auto whitespace-pre-wrap bg-gray-50 dark:bg-black/30">{text}</pre>
            </div>
          );
        })}
      </div>
    );
  };

  const renderDeployPanel = () => {
    if (!deploy) return <div className="text-sm text-gray-500">배포를 실행하면 결과가 저장되고 표시됩니다.</div>;
    const det = deploy.details?.job;
    const summary = det?.summary || null;
    return (
      <div className="space-y-3">
        <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
          <div className="text-sm">
            <span className="font-bold">Job</span> #{deploy.job_id} / <span className="font-mono">{deploy.status}</span>
          </div>
          {summary ? (
            <div className="text-xs text-gray-600 dark:text-gray-400 mt-2">
              total: <span className="font-mono">{summary.total}</span> / success: <span className="font-mono">{summary.success}</span> / failed: <span className="font-mono">{summary.failed}</span>
            </div>
          ) : null}
        </div>

        <div className="space-y-2">
          {(deploy.results || []).map((r) => (
            <div key={r.device_id} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-bold">{r.name || `Device ${r.device_id}`}</div>
                {r.success ? <CheckCircle size={16} className="text-green-600" /> : <AlertTriangle size={16} className="text-red-600" />}
              </div>
              <div className="text-xs text-gray-500 font-mono mt-1">{r.ip_address || '-'}</div>
              {!r.success && r.error ? <div className="text-xs text-red-600 mt-2">{r.error}</div> : null}
            </div>
          ))}
        </div>

        {deploy.details?.results?.length ? (
          <div className="space-y-2">
            <div className="font-bold text-sm">상세 로그</div>
            {deploy.details.results.map((r) => (
              <details key={`log-${r.device_id}`} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 overflow-hidden">
                <summary className="px-3 py-2 cursor-pointer text-sm font-bold">
                  Device {r.device_id} {r.success ? 'SUCCESS' : 'FAILED'}
                </summary>
                <div className="p-3 space-y-3">
                  {r.error ? <div className="text-xs text-red-600">{r.error}</div> : null}
                  <div>
                    <div className="text-xs font-bold mb-1">Rendered Config</div>
                    <pre className="text-xs whitespace-pre-wrap overflow-x-auto bg-gray-50 dark:bg-black/30 p-3 rounded-lg">{r.rendered_config || ''}</pre>
                  </div>
                  <div>
                    <div className="text-xs font-bold mb-1">Output</div>
                    <pre className="text-xs whitespace-pre-wrap overflow-x-auto bg-gray-50 dark:bg-black/30 p-3 rounded-lg">{r.output_log || ''}</pre>
                  </div>
                </div>
              </details>
            ))}
          </div>
        ) : null}
      </div>
    );
  };

  const renderGuidePanel = () => (
    <div className="space-y-3 text-sm">
      <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
        <div className="font-bold mb-2">사용 순서</div>
        <ol className="list-decimal pl-5 space-y-1 text-gray-700 dark:text-gray-200">
          <li>Blueprint 생성 또는 선택</li>
          <li>Blocks에서 Target 추가 후 대상 장비 선택</li>
          <li>VLAN/Interface/L2 Safety/ACL 블록을 추가하고 Inspector에서 값 설정</li>
          <li>검증(Validate)로 필수값/형식 오류 확인</li>
          <li>미리보기(Preview)로 장비별 CLI 확인</li>
          <li>배포(Deploy) 실행 후 결과/로그 확인</li>
        </ol>
      </div>
      <div className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
        <div className="font-bold mb-2">팁</div>
        <div className="space-y-1 text-gray-700 dark:text-gray-200">
          <div>- 노드 클릭 → Inspector에서 설정 변경</div>
          <div>- Target은 필수(대상 장비가 없으면 Preview/Deploy가 실패)</div>
          <div>- Preview는 실제 적용 전 “렌더 결과” 확인용</div>
          <div>- Deploy는 SSH로 장비에 push하며, 기본으로 배포 전 running-config 백업을 저장</div>
        </div>
      </div>
    </div>
  );

  const fmtTs = (ts) => {
    if (!ts) return '-';
    try {
      const d = new Date(ts);
      if (Number.isNaN(d.getTime())) return String(ts);
      return d.toLocaleString();
    } catch {
      return String(ts);
    }
  };

  const loadJobToDeployPanel = async (jobId) => {
    setBusy(true);
    setError('');
    try {
      const det = await VisualConfigService.getDeployJob(jobId);
      const job = det.data?.job;
      const results = (det.data?.results || []).map((r) => ({
        device_id: r.device_id,
        name: null,
        ip_address: null,
        success: !!r.success,
        error: r.error || null,
      }));
      setDeploy({ job_id: jobId, status: job?.status || 'unknown', results, details: det.data });
      setRightTab('deploy');
    } catch (e) {
      setError('Failed to load job');
    } finally {
      setBusy(false);
    }
  };

  const rollbackJob = async (jobId) => {
    const ok = window.confirm('Rollback this job? (best-effort)');
    if (!ok) return;
    setBusy(true);
    setError('');
    try {
      const res = await VisualConfigService.rollbackDeployJob(jobId, { save_backup: true });
      setDeploy({ job_id: res.data.job_id, status: res.data.status, results: res.data.results || [], details: null });
      setRightTab('deploy');
      try {
        const det = await VisualConfigService.getDeployJob(res.data.job_id);
        setDeploy(prev => ({ ...(prev || {}), details: det.data }));
      } catch (e) {
        // ignore
      }
      loadHistory(selectedId).catch(() => { });
    } catch (e) {
      setError('Failed to rollback');
    } finally {
      setBusy(false);
    }
  };

  const renderHistoryPanel = () => {
    if (!selectedId) return <div className="text-sm text-gray-500">Blueprint를 먼저 선택하세요.</div>;
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-bold flex items-center gap-2"><Clock size={16} /> Recent Jobs</div>
          <button
            disabled={historyLoading}
            onClick={() => loadHistory(selectedId)}
            className="px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30 text-xs font-bold flex items-center gap-2 disabled:opacity-60"
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        {historyLoading ? (
          <div className="text-sm text-gray-500">Loading...</div>
        ) : historyJobs.length === 0 ? (
          <div className="text-sm text-gray-500">No jobs yet.</div>
        ) : (
          <div className="space-y-2">
            {historyJobs.map((j) => {
              const type = j?.summary?.type || 'deploy';
              const badge = type === 'rollback' ? 'bg-purple-100 text-purple-700 border-purple-200' : 'bg-blue-100 text-blue-700 border-blue-200';
              const statusBadge = j.status === 'success'
                ? 'bg-green-100 text-green-700 border-green-200'
                : j.status === 'failed'
                  ? 'bg-red-100 text-red-700 border-red-200'
                  : 'bg-gray-100 text-gray-700 border-gray-200';
              return (
                <div key={j.id} className="rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="font-bold text-sm">#{j.id}</div>
                    <div className="flex items-center gap-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold border ${badge}`}>{type}</span>
                      <span className={`px-2 py-0.5 rounded-full text-xs font-bold border ${statusBadge}`}>{j.status}</span>
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 mt-1">{fmtTs(j.created_at)}{j.finished_at ? ` → ${fmtTs(j.finished_at)}` : ''}</div>
                  {j.summary && typeof j.summary === 'object' && j.summary.total != null ? (
                    <div className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                      total: <span className="font-mono">{j.summary.total}</span> / success: <span className="font-mono">{j.summary.success}</span> / failed: <span className="font-mono">{j.summary.failed}</span>
                    </div>
                  ) : null}
                  <div className="flex gap-2 mt-3">
                    <button
                      disabled={busy}
                      onClick={() => loadJobToDeployPanel(j.id)}
                      className="flex-1 px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30 text-sm font-bold"
                    >
                      Open
                    </button>
                    {type === 'deploy' ? (
                      <button
                        disabled={busy}
                        onClick={() => rollbackJob(j.id)}
                        className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-60 text-white text-sm font-bold flex items-center gap-2"
                      >
                        <RotateCcw size={16} /> Rollback
                      </button>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="h-full min-h-0 flex flex-col lg:flex-row">
      <div className="w-full lg:w-80 border-b lg:border-b-0 lg:border-r border-gray-200 dark:border-gray-800 bg-white dark:bg-[#151719] p-4 overflow-y-auto max-h-[45dvh] lg:max-h-none">
        <div className="text-lg font-bold mb-1">Visual Config</div>
        <div className="text-xs text-gray-500 mb-4">블록 조립 → 미리보기 → 배포</div>
        <div className="space-y-2 mb-4">
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New blueprint name"
            className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20"
          />
          <input
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            placeholder="Description (optional)"
            className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 bg-white dark:bg-black/20"
          />
          <button
            disabled={busy || !newName.trim()}
            onClick={createBlueprint}
            className="w-full px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white font-bold"
          >
            Create
          </button>
        </div>

        <div className="flex items-center justify-between mb-2">
          <div className="font-bold">Blueprints</div>
          <button onClick={() => loadBlueprints()} className="text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200">
            Refresh
          </button>
        </div>

        <div className="space-y-2">
          {blueprints.length === 0 ? (
            <div className="text-sm text-gray-500">No blueprints yet.</div>
          ) : (
            blueprints.map((b) => (
              <button
                key={b.id}
                onClick={() => loadBlueprint(b.id)}
                className={`w-full text-left px-3 py-2 rounded-lg border ${selectedId === b.id
                  ? 'border-blue-400 bg-blue-50 dark:bg-blue-900/20'
                  : 'border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/20'
                  }`}
              >
                <div className="font-bold">{b.name}</div>
                <div className="text-xs text-gray-500">v{b.current_version}</div>
              </button>
            ))
          )}
        </div>

        {selected && (
          <div className="mt-6 space-y-2">
            <div className="font-bold">Selected</div>
            <div className="text-sm">{selectedMeta?.name || selected.name}</div>
            <div className="text-xs text-gray-500">Current version: v{selectedMeta?.current_version || selected.current_version}</div>
            <div className="flex gap-2">
              <button
                disabled={busy}
                onClick={saveVersion}
                className="flex-1 px-3 py-2 rounded-lg bg-green-600 hover:bg-green-500 disabled:opacity-60 text-white font-bold"
              >
                Save
              </button>
              <button
                disabled={busy}
                onClick={deleteBlueprint}
                className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/20 text-sm font-bold"
              >
                Delete
              </button>
            </div>
          </div>
        )}

        <div className="mt-6">
          <div className="font-bold mb-2">블록 팔레트</div>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => addNode('target')} className="px-3 py-2 rounded-lg border-2 border-purple-300 bg-purple-50 dark:bg-purple-900/20 hover:bg-purple-100 dark:hover:bg-purple-900/30 text-sm font-bold flex items-center gap-2 col-span-2 text-purple-700">
              <Plus size={16} /> 🎯 Target
            </button>
            <button onClick={() => addNode('vlan')} className="px-3 py-2 rounded-lg border-2 border-blue-300 bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 text-sm font-bold flex items-center gap-2 text-blue-700">
              <Plus size={16} /> VLAN
            </button>
            <button onClick={() => addNode('interface')} className="px-3 py-2 rounded-lg border-2 border-emerald-300 bg-emerald-50 dark:bg-emerald-900/20 hover:bg-emerald-100 text-sm font-bold flex items-center gap-2 text-emerald-700">
              <Plus size={16} /> Interface
            </button>
            <button onClick={() => addNode('l2_safety')} className="px-3 py-2 rounded-lg border-2 border-amber-300 bg-amber-50 dark:bg-amber-900/20 hover:bg-amber-100 text-sm font-bold flex items-center gap-2 text-amber-700">
              <Plus size={16} /> L2 Safety
            </button>
            <button onClick={() => addNode('global')} className="px-3 py-2 rounded-lg border-2 border-slate-300 bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 text-sm font-bold flex items-center gap-2 text-slate-700">
              <Plus size={16} /> Global Config
            </button>
            <button onClick={() => addNode('acl')} className="px-3 py-2 rounded-lg border-2 border-red-300 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 text-sm font-bold flex items-center gap-2 text-red-700">
              <Plus size={16} /> ACL
            </button>
            <button onClick={() => addNode('ospf')} className="px-3 py-2 rounded-lg border-2 border-orange-300 bg-orange-50 dark:bg-orange-900/20 hover:bg-orange-100 text-sm font-bold flex items-center gap-2 text-orange-700">
              <Plus size={16} /> OSPF
            </button>
            <button onClick={() => addNode('route')} className="px-3 py-2 rounded-lg border-2 border-teal-300 bg-teal-50 dark:bg-teal-900/20 hover:bg-teal-100 text-sm font-bold flex items-center gap-2 text-teal-700">
              <Plus size={16} /> Route
            </button>
          </div>
        </div>

        <div className="mt-6">
          <div className="font-bold mb-2">Actions</div>
          <div className="grid grid-cols-2 gap-2">
            <button onClick={runValidate} className="px-3 py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-bold text-sm">
              Validate
            </button>
            <button disabled={!selectedId || busy} onClick={runPreview} className="px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white font-bold text-sm flex items-center justify-center gap-2">
              <Eye size={16} /> Preview
            </button>
            <button disabled={!selectedId || busy} onClick={runDeploy} className="px-3 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 disabled:opacity-60 text-white font-bold text-sm flex items-center justify-center gap-2 col-span-2">
              <Play size={16} /> Deploy
            </button>
          </div>
        </div>

        {validation?.__global?.length ? (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3">
            <div className="font-bold text-sm text-red-700 mb-2">Validation</div>
            <div className="text-xs text-red-700 space-y-1">
              {validation.__global.map((m, idx) => (
                <div key={`${idx}-${m}`} className="flex items-center gap-1">
                  <AlertTriangle size={12} /> {m}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {error && <div className="mt-4 text-sm text-red-600">{error}</div>}
      </div>

      <div className="flex-1 min-h-0 bg-gray-50 dark:bg-[#0f1112] flex flex-col lg:flex-row">
        <div className="flex-1 min-h-[45dvh] lg:min-h-0">
          <div className="h-full">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              nodeTypes={nodeTypes}
              onNodeClick={(_, n) => setSelectedNodeId(n.id)}
              onPaneClick={() => setSelectedNodeId(null)}
              onConnect={(params) => setEdges((eds) => [...eds, { ...params, id: `${params.source}-${params.target}-${Date.now()}` }])}
              fitView
            >
              <Background />
              <MiniMap />
              <Controls />
            </ReactFlow>
          </div>
        </div>

        <div className="w-full lg:w-[380px] border-t lg:border-t-0 lg:border-l border-gray-200 dark:border-gray-800 bg-white dark:bg-[#151719] p-4 overflow-y-auto max-h-[45dvh] lg:max-h-none">
          <div className="flex items-center justify-between gap-2 mb-3">
            <div className="text-lg font-bold">Details</div>
            <button
              onClick={() => setRightTab('guide')}
              className="px-3 py-2 rounded-lg border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-black/30 text-sm font-bold flex items-center gap-2"
            >
              <BookOpen size={16} /> 사용법
            </button>
          </div>

          <div className="flex flex-wrap gap-2 mb-4">
            <TabButton active={rightTab === 'inspector'} onClick={() => setRightTab('inspector')}>Inspector</TabButton>
            <TabButton active={rightTab === 'preview'} onClick={() => setRightTab('preview')}>Preview</TabButton>
            <TabButton active={rightTab === 'deploy'} onClick={() => setRightTab('deploy')}>Deploy</TabButton>
            <TabButton active={rightTab === 'history'} onClick={() => setRightTab('history')}>History</TabButton>
            <TabButton active={rightTab === 'guide'} onClick={() => setRightTab('guide')}>Guide</TabButton>
          </div>

          {rightTab === 'inspector' ? renderInspector() : null}
          {rightTab === 'preview' ? renderPreviewPanel() : null}
          {rightTab === 'deploy' ? renderDeployPanel() : null}
          {rightTab === 'history' ? renderHistoryPanel() : null}
          {rightTab === 'guide' ? renderGuidePanel() : null}
        </div>
      </div>
    </div>
  );
}
