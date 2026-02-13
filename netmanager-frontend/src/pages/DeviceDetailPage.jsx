import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DeviceService } from '../api/services';
import { useAuth } from '../context/AuthContext'; // [RBAC]
import { useToast } from '../context/ToastContext';
import {
  ArrowLeft, Activity, Server, Clock, Cpu,
  CheckCircle, RefreshCw, FileText, Network, Slash, AlertTriangle,
  Search, Filter, ListFilter, Tag, Radio, Users, Wifi, ShieldAlert
} from 'lucide-react';

const parseFilename = (contentDisposition) => {
  const v = contentDisposition || '';
  const m = v.match(/filename="?([^"]+)"?/i);
  return m ? m[1] : null;
};

const downloadBlob = (data, filename, contentType) => {
  const blob = data instanceof Blob ? data : new Blob([data], { type: contentType || 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename || 'download';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

const DeviceDetailPage = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { isOperator } = useAuth(); // [RBAC]
  const { toast } = useToast();

  const [device, setDevice] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [activeTab, setActiveTab] = useState('interfaces'); // interfaces, config
  const [inventory, setInventory] = useState([]);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryTreeOpen, setInventoryTreeOpen] = useState({});
  const [exportingInventory, setExportingInventory] = useState(false);

  // 1. 장비 상세 정보 로드
  const loadDevice = async () => {
    try {
      const res = await DeviceService.getDetail(id);
      setDevice(res.data);
    } catch (err) {
      console.error("Failed to load device detail", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDevice();

    // 5초 주기로 데이터 자동 갱신 (실시간성 확보)
    const timer = setInterval(() => {
      if (!syncing) { // 동기화 중에는 갱신 방해 금지
        loadDevice();
      }
    }, 5000);

    return () => clearInterval(timer);
  }, [id, syncing]);

  useEffect(() => {
    if (activeTab !== 'inventory') return;
    let alive = true;
    const run = async () => {
      setInventoryLoading(true);
      try {
        const res = await DeviceService.getInventory(id);
        if (alive) setInventory(Array.isArray(res.data) ? res.data : []);
      } catch (e) {
        if (alive) setInventory([]);
      } finally {
        if (alive) setInventoryLoading(false);
      }
    };
    run();
    return () => { alive = false; };
  }, [activeTab, id]);

  // 2. 동기화 핸들러 (Sync Handler)
  const handleSync = async () => {
    if (!window.confirm("SSH 접속을 통해 최신 정보를 가져오시겠습니까?")) return;

    setSyncing(true);
    try {
      await DeviceService.syncDevice(id);
      toast.success("동기화가 완료되었습니다.");
      await loadDevice(); // 최신 데이터로 갱신
    } catch (err) {
      console.error(err);
      toast.error("동기화 실패: " + (err.response?.data?.detail || "장비 접속 불가"));
    } finally {
      setSyncing(false);
    }
  };

  const handleExportInventory = async (format) => {
    setExportingInventory(true);
    try {
      const res = await DeviceService.exportInventory(id, format);
      const filename = parseFilename(res.headers?.['content-disposition']) || `inventory_${id}.${format}`;
      const contentType = res.headers?.['content-type'];
      downloadBlob(res.data, filename, contentType);
      toast.success('다운로드를 시작했습니다.');
    } catch (err) {
      toast.error('내보내기 실패: ' + (err.response?.data?.detail || err.message));
    } finally {
      setExportingInventory(false);
    }
  };

  if (loading) return <div className="h-full flex items-center justify-center text-gray-500">Loading device details...</div>;
  if (!device) return <div className="p-10 text-center text-red-500">Device data not available.</div>;

  const isOnline = device.status === 'online';

  // KPI Data (Metrics 배열의 마지막 값 사용)
  const lastMetric = device.metrics && device.metrics.length > 0
    ? device.metrics[device.metrics.length - 1]
    : { cpu_usage: 0, memory_usage: 0 };

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-[#f4f5f9] dark:bg-[#0e1012] h-full flex flex-col animate-fade-in text-gray-900 dark:text-white overflow-y-auto">

      {/* 1. 상단 헤더 영역 */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate(-1)} className="p-2 hover:bg-gray-200 dark:hover:bg-gray-800 rounded-full transition-colors">
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              {device.name}
              {device.hostname && device.hostname !== device.name && (
                <span className="text-sm font-normal text-gray-400">({device.hostname})</span>
              )}
              <span className={`px-2 py-0.5 text-xs rounded-full uppercase border font-bold ${isOnline
                ? 'bg-green-500/10 text-green-500 border-green-500/20'
                : 'bg-red-500/10 text-red-500 border-red-500/20'
                }`}>
                {device.status?.toUpperCase() || 'UNKNOWN'}
              </span>
            </h1>
            <p className="text-sm text-gray-500 flex items-center gap-2 mt-1">
              <span className="font-mono bg-gray-100 dark:bg-gray-800 px-1.5 rounded">{device.ip_address}</span>
              <span>•</span>
              <span>{device.model || 'Unknown Model'}</span>
            </p>
          </div>
        </div>

        {/* 액션 버튼 그룹 */}
        <div className="flex gap-2">
          {isOperator() && (
            <button
              onClick={handleSync}
              disabled={syncing}
              className={`flex items-center gap-2 px-4 py-2 text-white text-sm font-bold rounded-lg transition-all shadow-lg
                ${syncing ? 'bg-indigo-400 cursor-not-allowed' : 'bg-indigo-600 hover:bg-indigo-700 shadow-indigo-500/20'}`}
            >
              <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
              {syncing ? "Syncing..." : "Sync Device"}
            </button>
          )}
        </div>
      </div>

      {/* 2. KPI 카드 그리드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <KpiCard icon={<Cpu className="text-blue-500" />} title="CPU Usage" value={`${lastMetric.cpu_usage}%`} sub="Current Load" />
        <KpiCard icon={<Activity className="text-purple-500" />} title="Memory" value={`${lastMetric.memory_usage}%`} sub="Used" />
        <KpiCard icon={<Clock className="text-green-500" />} title="Uptime" value={device.uptime || "0d 0h"} sub="Since Reboot" />
        <KpiCard icon={<Network className="text-orange-500" />} title="Ports" value={device.interfaces?.length || 0} sub="Total Ports" />
        {device.latest_parsed_data?.wireless && (
          <>
            <KpiCard
              icon={<Wifi className="text-emerald-500" />}
              title="Active APs"
              value={`${device.latest_parsed_data.wireless.up_aps || 0} / ${device.latest_parsed_data.wireless.total_aps || 0}`}
              sub="Registration Status"
            />
            <KpiCard
              icon={<Users className="text-pink-500" />}
              title="Wireless Clients"
              value={device.latest_parsed_data.wireless.total_clients || 0}
              sub="Connected Everywhere"
            />
          </>
        )}
      </div>

      {/* 2.5 Device Info Panel */}
      <div className="bg-white dark:bg-[#1b1d1f] p-4 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm mb-6">
        <h3 className="text-sm font-bold text-gray-500 uppercase mb-3 flex items-center gap-2">
          <Server size={16} /> Device Information
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 text-sm">
          <InfoItem label="Hostname" value={device.hostname || 'Unknown'} />
          <InfoItem label="Model" value={device.model || 'Unknown'} />
          <InfoItem label="OS Version" value={device.os_version || 'Unknown'} />
          <InfoItem label="Serial Number" value={device.serial_number || 'N/A'} />
          <InfoItem label="Device Type" value={device.device_type?.toUpperCase() || 'CISCO_IOS'} />
          <InfoItem label="Site" value={device.site_id ? `Site #${device.site_id}` : 'Unassigned'} />
        </div>
      </div>

      {/* 3. 탭 메뉴 */}
      <div className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden flex flex-col flex-1 min-h-[500px]">
        <div className="flex border-b border-gray-200 dark:border-gray-800">
          <TabBtn active={activeTab === 'interfaces'} onClick={() => setActiveTab('interfaces')} icon={<Server size={16} />} label="Interfaces" />
          {device.latest_parsed_data?.wireless && (
            <TabBtn active={activeTab === 'wireless'} onClick={() => setActiveTab('wireless')} icon={<Radio size={16} />} label="Wireless Summary" />
          )}
          <TabBtn active={activeTab === 'inventory'} onClick={() => setActiveTab('inventory')} icon={<ListFilter size={16} />} label="Inventory" />
          <TabBtn active={activeTab === 'config'} onClick={() => setActiveTab('config')} icon={<FileText size={16} />} label="Running Config" />
        </div>

        {/* 탭 컨텐츠 */}
        <div className="flex-1 overflow-hidden flex flex-col">
          {activeTab === 'interfaces' && (
            <InterfaceTable interfaces={device.interfaces || []} />
          )}

          {activeTab === 'wireless' && device.latest_parsed_data?.wireless && (
            <WirelessSummary data={device.latest_parsed_data.wireless} />
          )}

          {activeTab === 'inventory' && (
            <div className="p-6 flex-1 overflow-auto">
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-bold text-gray-600 dark:text-gray-300">Chassis / Modules (ENTITY-MIB)</div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleExportInventory('xlsx')}
                    disabled={exportingInventory}
                    className="px-3 py-1.5 text-xs font-bold rounded bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    Export XLSX
                  </button>
                  <button
                    onClick={() => handleExportInventory('pdf')}
                    disabled={exportingInventory}
                    className="px-3 py-1.5 text-xs font-bold rounded bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    Export PDF
                  </button>
                  <button
                    onClick={async () => {
                      setInventoryLoading(true);
                      try {
                        const res = await DeviceService.getInventory(id);
                        setInventory(Array.isArray(res.data) ? res.data : []);
                      } finally {
                        setInventoryLoading(false);
                      }
                    }}
                    className="px-3 py-1.5 text-xs font-bold rounded bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-200 dark:hover:bg-gray-700"
                  >
                    <RefreshCw size={14} className={inventoryLoading ? "animate-spin inline mr-2" : "inline mr-2"} />
                    Refresh
                  </button>
                </div>
              </div>

              {inventoryLoading && (
                <div className="text-sm text-gray-500">Loading inventory...</div>
              )}

              {!inventoryLoading && inventory.length === 0 && (
                <div className="text-sm text-gray-500">No inventory data. Run Sync Device, and ensure SNMP community is correct.</div>
              )}

              {!inventoryLoading && inventory.length > 0 && (
                <InventoryTree
                  items={inventory}
                  openMap={inventoryTreeOpen}
                  setOpenMap={setInventoryTreeOpen}
                />
              )}
            </div>
          )}

          {activeTab === 'config' && (
            <div className="p-6 flex-1 overflow-auto">
              <div className="h-full bg-[#282c34] text-gray-300 p-4 rounded-lg font-mono text-xs overflow-auto whitespace-pre leading-relaxed border border-gray-700">
                {device.config_backups && device.config_backups.length > 0
                  ? device.config_backups[device.config_backups.length - 1].raw_config
                  : "// No configuration backup found.\n// Click 'Sync Device' to fetch the latest configuration."}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// --- Sub Components ---

const TabBtn = ({ active, onClick, icon, label }) => (
  <button
    onClick={onClick}
    className={`px-6 py-4 text-sm font-bold flex items-center gap-2 border-b-2 transition-colors ${active ? 'border-indigo-500 text-indigo-600 dark:text-indigo-400' : 'border-transparent text-gray-500 hover:text-gray-700'
      }`}
  >
    {icon} {label}
  </button>
);

const KpiCard = ({ icon, title, value, sub }) => (
  <div className="bg-white dark:bg-[#1b1d1f] p-4 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm flex items-center gap-4">
    <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">{icon}</div>
    <div>
      <p className="text-xs text-gray-500 font-bold uppercase">{title}</p>
      <h3 className="text-xl font-bold text-gray-900 dark:text-white">{value}</h3>
      <p className="text-xs text-gray-400">{sub}</p>
    </div>
  </div>
);

const InfoItem = ({ label, value }) => (
  <div>
    <p className="text-xs text-gray-400 uppercase font-medium">{label}</p>
    <p className="text-gray-900 dark:text-white font-medium truncate" title={value}>{value}</p>
  </div>
);

const InterfaceTable = ({ interfaces }) => {
  const [filter, setFilter] = useState('all'); // all, up, down, admin_down
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all'); // all, physical, virtual, vlan

  const stats = useMemo(() => {
    return {
      total: interfaces.length,
      up: interfaces.filter(i => i.status?.toLowerCase() === 'up').length,
      down: interfaces.filter(i => i.status?.toLowerCase() === 'down').length,
      adminDown: interfaces.filter(i => i.status?.toLowerCase() === 'admin_down').length,
    };
  }, [interfaces]);

  const filteredInterfaces = useMemo(() => {
    return interfaces.filter(iface => {
      const matchStatus = filter === 'all' || iface.status?.toLowerCase() === filter;
      const matchSearch = iface.name.toLowerCase().includes(search.toLowerCase()) ||
        (iface.description && iface.description.toLowerCase().includes(search.toLowerCase()));

      let matchType = true;
      if (typeFilter === 'physical') {
        matchType = /Ethernet|Gigabit|TenGigabit|FastEthernet/i.test(iface.name) && !/Vlan|Loopback|Port-channel/i.test(iface.name);
      } else if (typeFilter === 'vlan') {
        matchType = /Vlan/i.test(iface.name);
      } else if (typeFilter === 'virtual') {
        matchType = /Loopback|Port-channel|Tunnel/i.test(iface.name);
      }

      return matchStatus && matchSearch && matchType;
    });
  }, [interfaces, filter, search, typeFilter]);

  if (interfaces.length === 0) {
    return (
      <div className="p-6 h-full flex flex-col items-center justify-center text-gray-500">
        <Server size={48} className="mb-4 opacity-20" />
        <p>No interface data available. Please sync the device.</p>
      </div>
    );
  }

  const renderStatus = (status) => {
    const s = status?.toLowerCase() || '';
    if (s === 'admin_down') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-500 border border-gray-200 dark:bg-gray-800 dark:border-gray-700">
          <Slash size={10} /> ADMIN DOWN
        </span>
      );
    }
    if (s === 'up') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-green-50 text-green-600 border border-green-200 dark:bg-green-900/20 dark:text-green-400 dark:border-green-800">
          <CheckCircle size={10} /> UP
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold bg-red-50 text-red-600 border border-red-200 dark:bg-red-900/20 dark:text-red-400 dark:border-red-800">
        <AlertTriangle size={10} /> DOWN
      </span>
    );
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 1. Summary Bar */}
      <div className="px-6 py-4 bg-gray-50 dark:bg-[#151719] border-b border-gray-200 dark:border-gray-800 flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">Summary:</span>
          <div className="flex gap-3">
            <span className="text-sm font-bold text-gray-900 dark:text-white">{stats.total} total</span>
            <span className="text-sm font-bold text-green-500">● {stats.up} up</span>
            <span className="text-sm font-bold text-red-500">● {stats.down} down</span>
            <span className="text-sm font-bold text-gray-500">● {stats.adminDown} disabled</span>
          </div>
        </div>

        <div className="h-4 w-px bg-gray-300 dark:bg-gray-700 hidden md:block" />

        <div className="flex-1 flex flex-col lg:flex-row lg:items-center gap-3 lg:gap-4 min-w-0">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
            <input
              type="text"
              placeholder="Search interfaces..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all font-medium"
            />
          </div>

          <div className="flex flex-nowrap overflow-x-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-0.5 shadow-sm">
            <FilterBtn active={filter === 'all'} onClick={() => setFilter('all')} label="All" />
            <FilterBtn active={filter === 'up'} onClick={() => setFilter('up')} label="Up" />
            <FilterBtn active={filter === 'down'} onClick={() => setFilter('down')} label="Down" />
            <FilterBtn active={filter === 'admin_down'} onClick={() => setFilter('admin_down')} label="Disabled" />
          </div>

          <div className="flex flex-nowrap overflow-x-auto bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-0.5 shadow-sm">
            <FilterBtn active={typeFilter === 'all'} onClick={() => setTypeFilter('all')} label="All Types" />
            <FilterBtn active={typeFilter === 'physical'} onClick={() => setTypeFilter('physical')} label="Physical" />
            <FilterBtn active={typeFilter === 'vlan'} onClick={() => setTypeFilter('vlan')} label="VLAN" />
            <FilterBtn active={typeFilter === 'virtual'} onClick={() => setTypeFilter('virtual')} label="Logical" />
          </div>
        </div>
      </div>

      {/* 2. Table Context */}
      <div className="flex-1 overflow-auto p-6 pt-0">
        <table className="w-full text-left border-collapse text-sm">
          <thead className="sticky top-0 bg-white dark:bg-[#1b1d1f] z-10 shadow-[0_1px_0_0_rgba(0,0,0,0.1)] dark:shadow-[0_1px_0_0_rgba(255,255,255,0.05)]">
            <tr>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px] w-48">Interface</th>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px] w-32 text-center">Status</th>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px] w-24 text-center">Mode</th>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px] w-40">Info</th>
              <th className="py-4 px-4 font-bold text-gray-500 uppercase tracking-tighter text-[11px]">Description</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {filteredInterfaces.length > 0 ? filteredInterfaces.map((iface) => (
              <tr key={iface.id} className="hover:bg-gray-50/80 dark:hover:bg-white/[0.02] transition-colors group">
                <td className="py-3.5 px-4">
                  <div className="flex flex-col">
                    <span className="font-mono font-bold text-gray-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors">
                      {iface.name}
                    </span>
                    <span className="text-[10px] text-gray-400 font-medium">
                      {iface.name.toLowerCase().includes('gigabit') ? '1 Gbps' : iface.name.toLowerCase().includes('tengigabit') ? '10 Gbps' : 'N/A'}
                    </span>
                  </div>
                </td>
                <td className="py-3.5 px-4 text-center">
                  {renderStatus(iface.status)}
                </td>
                <td className="py-3.5 px-4 text-center">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${iface.mode === 'trunk' ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' :
                    iface.mode === 'routed' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                      'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
                    }`}>
                    {iface.mode || 'Access'}
                  </span>
                </td>
                <td className="py-3.5 px-4">
                  <div className="font-mono text-xs flex flex-col gap-0.5">
                    {iface.ip_address ? (
                      <span className="text-blue-600 dark:text-blue-400 font-bold">{iface.ip_address}</span>
                    ) : (
                      <span className="text-gray-500 flex items-center gap-1">
                        <Tag size={10} className="opacity-40" />
                        VLAN {iface.vlan || 1}
                      </span>
                    )}
                    {iface.mac_address && (
                      <span className="text-[10px] text-gray-400 opacity-70 truncate max-w-[140px] uppercase">
                        {iface.mac_address}
                      </span>
                    )}
                  </div>
                </td>
                <td className="py-3.5 px-4">
                  <div className="text-gray-600 dark:text-gray-400 italic text-sm truncate max-w-sm" title={iface.description}>
                    {iface.description || <span className="text-gray-300 dark:text-gray-700 not-italic">-</span>}
                  </div>
                </td>
              </tr>
            )) : (
              <tr>
                <td colSpan="5" className="py-20 text-center text-gray-400 italic">
                  No interfaces match the current filter / search criteria.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

const InventoryTree = ({ items, openMap, setOpenMap }) => {
  const nodesById = useMemo(() => {
    const m = new Map();
    for (const it of items) {
      m.set(it.ent_physical_index, { ...it, children: [] });
    }
    for (const it of items) {
      const parentId = it.parent_index;
      if (parentId && m.has(parentId)) {
        m.get(parentId).children.push(m.get(it.ent_physical_index));
      }
    }
    return m;
  }, [items]);

  const roots = useMemo(() => {
    const rootList = [];
    for (const it of items) {
      const parentId = it.parent_index;
      if (!parentId || !nodesById.has(parentId)) {
        rootList.push(nodesById.get(it.ent_physical_index));
      }
    }
    const score = (n) => {
      const cls = String(n.class_name || '').toLowerCase();
      if (cls === 'chassis') return 0;
      if (cls === 'stack') return 1;
      if (cls === 'module') return 2;
      return 3;
    };
    rootList.sort((a, b) => score(a) - score(b) || a.ent_physical_index - b.ent_physical_index);
    return rootList;
  }, [items, nodesById]);

  const toggle = (id) => setOpenMap(prev => ({ ...prev, [id]: !prev[id] }));

  const renderNode = (n, depth) => {
    const hasChildren = (n.children || []).length > 0;
    const isOpen = !!openMap[n.ent_physical_index];
    const label = n.name || n.model_name || n.description || `Index ${n.ent_physical_index}`;
    const cls = n.class_name || n.class_id || '-';
    const secondary = [n.model_name, n.serial_number, n.mfg_name].filter(Boolean).join(' · ');

    return (
      <div key={n.ent_physical_index}>
        <div
          className="flex items-center gap-2 px-3 py-2 border border-gray-200 dark:border-gray-800 rounded-md bg-white dark:bg-[#1b1d1f] hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
          style={{ marginLeft: depth * 14 }}
        >
          <button
            onClick={() => hasChildren && toggle(n.ent_physical_index)}
            className={`w-5 h-5 flex items-center justify-center rounded border ${hasChildren ? 'border-gray-300 dark:border-gray-700 hover:border-indigo-500' : 'border-transparent'}`}
            disabled={!hasChildren}
          >
            {hasChildren ? (isOpen ? '−' : '+') : ''}
          </button>

          <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
            {cls}
          </span>

          <div className="min-w-0 flex-1">
            <div className="font-bold text-sm text-gray-900 dark:text-gray-100 truncate">{label}</div>
            {secondary && <div className="text-xs text-gray-500 dark:text-gray-400 truncate">{secondary}</div>}
          </div>

          <span className="text-[11px] text-gray-400 font-mono">#{n.ent_physical_index}</span>
        </div>

        {hasChildren && isOpen && (
          <div className="mt-2 space-y-2">
            {n.children
              .slice()
              .sort((a, b) => (a.class_id || 999) - (b.class_id || 999) || a.ent_physical_index - b.ent_physical_index)
              .map((c) => renderNode(c, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-2">
      {roots.map((r) => renderNode(r, 0))}
    </div>
  );
};

const FilterBtn = ({ active, onClick, label }) => (
  <button
    onClick={onClick}
    className={`px-3 py-1.5 text-[11px] font-bold rounded-md transition-all ${active
      ? 'bg-indigo-600 text-white shadow-md'
      : 'text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700'
      }`}
  >
    {label}
  </button>
);

const WirelessSummary = ({ data }) => {
  const [search, setSearch] = useState('');

  const apList = data.ap_list || [];
  const wlanList = data.wlan_summary || [];

  const filteredAps = apList.filter(ap =>
    (ap.name || ap.ap_name || '').toLowerCase().includes(search.toLowerCase()) ||
    (ap.ip_address || '').includes(search)
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* 1. Header & Quick Stats */}
      <div className="px-6 py-4 bg-gray-50 dark:bg-[#151719] border-b border-gray-200 dark:border-gray-800 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-6">
          <div className="flex flex-col">
            <span className="text-[10px] text-gray-400 font-bold uppercase">WLANs Configured</span>
            <span className="text-lg font-black text-indigo-500">{wlanList.length} SSIDs</span>
          </div>
          <div className="h-8 w-px bg-gray-300 dark:bg-gray-700" />
          <div className="flex flex-col">
            <span className="text-[10px] text-gray-400 font-bold uppercase">Active Clients</span>
            <span className="text-lg font-black text-pink-500">{data.total_clients} Users</span>
          </div>
        </div>

        <div className="relative w-64">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={14} />
          <input
            type="text"
            placeholder="Search APs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all font-medium"
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6 space-y-8">
        {/* Section 1: WLAN Summary */}
        <div className="space-y-3">
          <h4 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
            <Wifi size={14} className="text-indigo-500" /> SSID / WLAN Status
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {wlanList.map((wl, idx) => (
              <div key={idx} className="bg-white dark:bg-[#1b1d1f] p-3 rounded-lg border border-gray-200 dark:border-gray-800 flex items-center justify-between shadow-sm">
                <div className="flex items-center gap-3">
                  <div className={`p-2 rounded-full ${wl.status === 'UP' || wl.status === 'Enabled' || wl.status === 'online' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-red-500/10 text-red-500'}`}>
                    <Radio size={14} />
                  </div>
                  <div>
                    <p className="text-xs font-bold text-gray-900 dark:text-white">{wl.ssid}</p>
                    <p className="text-[10px] text-gray-400">ID: {wl.id} • {wl.profile}</p>
                  </div>
                </div>
                <span className={`text-[10px] font-black px-1.5 py-0.5 rounded ${(wl.status === 'UP' || wl.status === 'Enabled' || wl.status === 'online') ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'}`}>
                  {wl.status}
                </span>
              </div>
            ))}
            {wlanList.length === 0 && (
              <div className="col-span-full py-4 text-center text-xs text-gray-500 italic bg-gray-50 dark:bg-gray-800/20 rounded-lg">
                No WLAN configurations found.
              </div>
            )}
          </div>
        </div>

        {/* Section 2: AP Inventory */}
        <div className="space-y-3">
          <h4 className="text-xs font-black text-gray-400 uppercase tracking-widest flex items-center gap-2">
            <Server size={14} className="text-indigo-500" /> Access Point Inventory
          </h4>
          <div className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-[720px] w-full text-left border-collapse text-sm">
                <thead className="bg-gray-50/50 dark:bg-gray-800/50">
                  <tr>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase">Host / Name</th>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase text-center">Status</th>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase">Model Details</th>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase">IP / Network</th>
                    <th className="py-3 px-4 font-bold text-gray-500 text-[10px] uppercase">Uptime</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                  {filteredAps.map((ap, idx) => {
                    const name = ap.name || ap.ap_name || 'Unknown';
                    const status = (ap.status || ap.state || '').toLowerCase();
                    const isUp = status.includes('up') || status.includes('reg') || status.includes('online');

                    return (
                      <tr key={idx} className="hover:bg-gray-50/80 dark:hover:bg-white/[0.02]">
                        <td className="py-3 px-4">
                          <div className="flex items-center gap-2 font-bold text-gray-900 dark:text-white">
                            <Radio size={14} className={isUp ? "text-emerald-500" : "text-gray-400"} />
                            {name}
                          </div>
                        </td>
                        <td className="py-3 px-4 text-center">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${isUp ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400' : 'bg-red-50 text-red-600 dark:bg-red-900/20 dark:text-red-400'
                            }`}>
                            {status || 'Unknown'}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          <div className="flex flex-col">
                            <span className="text-xs text-gray-700 dark:text-gray-300 font-medium">{ap.model || 'Cisco AP'}</span>
                            <span className="text-[10px] text-gray-400 font-mono tracking-tighter">SN: {ap.serial_number || 'N/A'}</span>
                          </div>
                        </td>
                        <td className="py-3 px-4">
                          <div className="font-mono text-xs text-blue-600 dark:text-blue-400 flex flex-col">
                            {ap.ip_address || 'N/A'}
                            <span className="text-[9px] text-gray-400 uppercase font-sans">Management</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-xs text-gray-500 uppercase font-medium">
                          {ap.uptime || 'N/A'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DeviceDetailPage;
