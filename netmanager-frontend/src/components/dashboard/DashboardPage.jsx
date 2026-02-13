import React, { useState, useEffect, useRef } from 'react';
import { DeviceService } from '../../api/services';
import {
  Activity, Server, MapPin, ShieldCheck, AlertOctagon,
  CheckCircle, RefreshCw, LayoutGrid, Wifi, Users, Radio
} from 'lucide-react';
import {
  PieChart, Pie, Cell, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts';
import TrafficChart from './TrafficChart'; // [수정] TrafficChart 컴포넌트 Import

// [추가] 상대 시간 포맷팅 함수
const formatRelativeTime = (isoString) => {
  if (!isoString) return '';
  const date = new Date(isoString);
  const now = new Date();
  const diffInSeconds = Math.floor((now - date) / 1000);

  if (diffInSeconds < 60) return `${diffInSeconds}s ago`;
  if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
  if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
  return `${Math.floor(diffInSeconds / 86400)}d ago`;
};

const DashboardPage = () => {
  const [stats, setStats] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sites, setSites] = useState([]); // [NEW] Sites List
  const [selectedSite, setSelectedSite] = useState(""); // [NEW] Selected Site ID

  // 데이터 자동 갱신을 위한 Ref
  const pollingRef = useRef(null);

  // 1. 데이터 로드 (백그라운드 갱신 지원)
  const loadData = async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const [statsRes, analyticsRes] = await Promise.all([
        DeviceService.getDashboardStats(selectedSite || null), // [FIX] Pass site filter
        DeviceService.getAnalytics('24h')
      ]);

      setStats(statsRes.data);
      setAnalytics(analyticsRes.data);
    } catch (err) {
      console.error("Dashboard Load Error:", err);
    } finally {
      if (isInitial) setLoading(false);
    }
  };

  // 0. 사이트 목록 로드
  useEffect(() => {
    DeviceService.getSites()
      .then(res => setSites(res.data))
      .catch(err => console.error("Failed to load sites", err));
  }, []);

  // 2. 초기 로드 및 5초 주기 Polling
  // selectedSite가 변경될 때마다 Polling을 재설정하여 필터 적용
  useEffect(() => {
    loadData(true);
    pollingRef.current = setInterval(() => {
      loadData(false);
    }, 5000);

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [selectedSite]); // [IMP] Re-run when site changes

  if (loading || !stats || !analytics) return (
    <div className="flex h-full items-center justify-center bg-transparent text-primary-glow font-mono">
      <RefreshCw className="animate-spin mr-2" /> Initializing Dashboard...
    </div>
  );

  const healthScore = stats.health_score || 0;
  const healthColor = healthScore >= 90 ? '#10b981' : healthScore >= 70 ? '#f59e0b' : '#ef4444';

  return (
    <div className="flex flex-col h-full gap-6 animate-fade-in text-gray-900 dark:text-white font-sans pb-6">

      {/* Header with Site Filter */}
      <div className="flex justify-between items-end pb-4 border-b border-gray-200 dark:border-white/5">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>
            <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white/90">
              Network Assurance
            </h1>
          </div>
          <p className="text-xs text-gray-500 pl-4">Real-time Infrastructure Health & Provisioning Status</p>
        </div>
        <div className="flex gap-3 items-center">
          {/* Site Filter */}
          <div className="relative group">
            <select
              value={selectedSite}
              onChange={(e) => setSelectedSite(e.target.value)}
              className="bg-white dark:bg-black/30 border border-gray-300 dark:border-white/10 text-gray-700 dark:text-gray-300 text-xs font-bold rounded-lg px-3 py-2 pl-3 pr-8 focus:outline-none focus:border-primary/50 appearance-none cursor-pointer transition-all hover:bg-gray-50 dark:hover:bg-black/40 hover:border-gray-400 dark:hover:border-white/20"
            >
              <option value="">Global View</option>
              {sites.map(site => (
                <option key={site.id} value={site.id}>{site.name}</option>
              ))}
            </select>
            <MapPin size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none group-hover:text-primary transition-colors" />
          </div>

          <div className="px-3 py-1.5 bg-emerald-50 dark:bg-success/10 border border-emerald-200 dark:border-success/20 rounded-full text-xs font-bold text-emerald-600 dark:text-success flex items-center gap-2 shadow-sm dark:shadow-neon-success">
            <CheckCircle size={14} /> System Healthy
          </div>
          <button onClick={() => loadData(true)} className="p-2 bg-gray-100 dark:bg-white/5 hover:bg-gray-200 dark:hover:bg-white/10 rounded-lg text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors border border-transparent hover:border-gray-300 dark:hover:border-white/10">
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {/* Global Health & Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 items-stretch">

        {/* Health Score Ring */}
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6 flex flex-col items-center justify-center relative min-h-[350px]">
          {/* Gradient Glow */}
          <div className="absolute inset-0 bg-radial-gradient from-primary/5 to-transparent opacity-50 pointer-events-none"></div>

          <h3 className="absolute top-6 left-6 text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider flex items-center gap-2">
            <Activity size={16} className="text-blue-500 dark:text-primary" /> Infrastructure Health
          </h3>
          <div className="w-full h-full max-h-[250px] mt-4 relative z-10">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={[{ value: healthScore }, { value: 100 - healthScore }]}
                  cx="50%" cy="50%"
                  innerRadius={75} outerRadius={95}
                  startAngle={90} endAngle={-270}
                  dataKey="value"
                  stroke="none"
                >
                  <Cell fill={healthColor} />
                  <Cell fill="rgba(255,255,255,0.05)" />
                </Pie>
              </PieChart>
            </ResponsiveContainer>

            {/* Center Text */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none mt-4">
              <span className="text-6xl font-black tracking-tighter drop-shadow-lg" style={{ color: healthColor }}>{healthScore}%</span>
              <span className="text-xs text-gray-500 mt-2 font-mono tracking-widest uppercase">Score</span>
            </div>
          </div>
        </div>

        {/* Inventory Status Grid */}
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6 flex flex-col">
          <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-6 flex items-center gap-2">
            <Server size={16} className="text-blue-500 dark:text-primary" /> Inventory Overview
          </h3>
          <div className="grid grid-cols-2 gap-4 flex-1 content-start">
            <StatusBox label="Sites" value={stats.counts?.sites || 0} icon={MapPin} color="text-primary" />
            <StatusBox label="Nodes" value={stats.counts?.devices || 0} icon={Server} color="text-purple-400" />

            <StatusBox
              label="Active APs"
              value={stats.counts?.wireless_aps || 0}
              icon={Wifi}
              color="text-emerald-400"
            />
            <StatusBox
              label="Clients"
              value={stats.counts?.wireless_clients || 0}
              icon={Users}
              color="text-pink-400"
            />

            <StatusBox
              label="Nodes Reached"
              value={(stats.counts?.online || 0)}
              icon={Activity}
              color="text-green-400"
            />

            <StatusBox
              label="Issues Found"
              value={(stats.counts?.offline || 0) + (stats.counts?.alert || 0)}
              icon={AlertOctagon}
              color="text-red-500"
              alert={(stats.counts?.offline > 0) || (stats.counts?.alert > 0)}
            />
          </div>

          <div className="mt-8 pt-6 border-t border-white/10">
            <div className="flex justify-between items-center mb-2">
              <div className="text-[10px] text-gray-500 uppercase font-black tracking-widest">Config Compliance</div>
              <div className="text-xs font-bold text-blue-300 font-mono">{stats.counts?.compliant || 0}/{stats.counts?.devices || 0} Synced</div>
            </div>
            <div className="w-full bg-black/40 h-1.5 rounded-full overflow-hidden border border-white/5">
              <div
                className="bg-primary h-full rounded-full transition-all duration-1000 shadow-[0_0_10px_#3b82f6]"
                style={{ width: `${stats.counts?.devices ? (stats.counts?.compliant / stats.counts?.devices) * 100 : 0}%` }}
              ></div>
            </div>
          </div>
        </div>

        {/* Priority Issues */}
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6 flex flex-col min-h-[350px]">
          <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <ShieldCheck size={16} className="text-orange-500" /> Priority Alerts
          </h3>
          <div className="flex-1 overflow-y-auto custom-scrollbar space-y-3 pr-2 -mr-2">
            {stats.issues && stats.issues.length > 0 ? (
              stats.issues.map((issue) => (
                <IssueItem
                  key={issue.id}
                  title={issue.title}
                  device={issue.device}
                  severity={issue.severity}
                  time={formatRelativeTime(issue.time)}
                />
              ))
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-600 italic">
                <CheckCircle size={32} className="mb-3 text-white/5" />
                <p className="text-xs">No active issues found.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Performance Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Traffic Chart Component */}
        <div className="lg:col-span-2 overflow-hidden flex flex-col">
          <TrafficChart data={stats.trafficTrend} />
        </div>

        {/* Resource Chart (Real Data) */}
        <div className="bg-white dark:bg-surface/40 backdrop-blur-md border border-gray-200 dark:border-white/5 shadow-sm rounded-2xl p-6 flex flex-col h-[350px]">
          <h3 className="text-sm font-bold text-gray-600 dark:text-gray-400 uppercase tracking-wider mb-2 flex items-center gap-2">
            <Activity size={16} className="text-emerald-500" /> Resource Health (Avg)
          </h3>
          <div className="flex-1 w-full min-h-0 relative">
            {/* Gradient Background for Chart */}
            <div className="absolute inset-0 bg-gradient-to-b from-white/5 to-transparent pointer-events-none rounded-xl"></div>

            {analytics.resourceTrend && analytics.resourceTrend.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={analytics.resourceTrend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
                  <XAxis dataKey="time" stroke="#52525b" fontSize={10} hide />
                  <YAxis domain={[0, 100]} stroke="#52525b" fontSize={10} tick={{ fill: '#9ca3af' }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: 'rgba(20,20,30,0.9)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff', backdropFilter: 'blur(4px)' }}
                    itemStyle={{ fontSize: '12px' }}
                  />
                  <Line type="monotone" dataKey="cpu" stroke="#10b981" strokeWidth={2} dot={false} isAnimationActive={false} shadow="0 0 10px #10b981" />
                  <Line type="monotone" dataKey="memory" stroke="#f59e0b" strokeWidth={2} dot={false} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex items-center justify-center h-full text-xs text-gray-600">
                Waiting for metrics...
              </div>
            )}
          </div>
        </div>
      </div>
    </div >
  );
};

const StatusBox = ({ label, value, icon: Icon, color, alert }) => (
  <div className={`p-4 rounded-xl border transition-all duration-300 group hover:translate-y-[-2px] ${alert ? 'bg-red-50 border-red-200 dark:bg-red-900/10 dark:border-red-500/30' : 'bg-gray-50 dark:bg-black/20 border-gray-100 dark:border-white/5 hover:border-blue-200 dark:hover:border-white/10 hover:bg-white dark:hover:bg-white/5'} flex flex-col justify-between`}>
    <div className="flex justify-between items-start">
      <Icon size={18} className={`${color} opacity-80 group-hover:opacity-100 transition-opacity`} />
      <span className={`text-2xl font-bold font-mono tracking-tight ${alert ? 'text-red-500 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}>{value}</span>
    </div>
    <span className="text-[10px] text-gray-500 uppercase mt-2 font-bold tracking-wider group-hover:text-gray-400 transition-colors">{label}</span>
  </div>
);

const IssueItem = ({ title, device, severity, time }) => {
  const color = severity === 'critical' ? 'bg-danger shadow-neon-danger' : severity === 'warning' ? 'bg-warning' : 'bg-primary';
  return (
    <div className="flex gap-3 p-3 rounded-xl bg-gray-50 dark:bg-black/20 border border-gray-100 dark:border-white/5 hover:border-blue-200 dark:hover:border-white/20 hover:bg-white dark:hover:bg-white/5 transition-all group cursor-pointer shadow-sm dark:shadow-none">
      <div className={`w-1 h-full rounded-full ${color}`}></div>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between">
          <span className="text-xs font-bold text-gray-800 dark:text-gray-200 group-hover:text-blue-600 dark:group-hover:text-white transition-colors">{title}</span>
          <span className="text-[10px] text-gray-500 font-mono">{time}</span>
        </div>
        <div className="text-[11px] text-gray-500 truncate mt-0.5">{device}</div>
      </div>
    </div>
  )
}

export default DashboardPage;