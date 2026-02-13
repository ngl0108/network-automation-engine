import React, { useState, useEffect } from 'react';
import { IssueService } from '../../api/services';
import { useNavigate } from 'react-router-dom';
import {
  Bell, CheckCircle, AlertTriangle, XCircle, Clock, Trash2, RefreshCw,
  Filter, Eye, EyeOff, Server, Shield, Settings, Cpu, Wrench, X
} from 'lucide-react';

const CATEGORIES = [
  { value: '', label: 'All Categories', icon: Filter },
  { value: 'device', label: 'Device', icon: Server },
  { value: 'security', label: 'Security', icon: Shield },
  { value: 'system', label: 'System', icon: Settings },
  { value: 'config', label: 'Configuration', icon: Wrench },
  { value: 'performance', label: 'Performance', icon: Cpu },
];

const SEVERITIES = [
  { value: '', label: 'All Severities' },
  { value: 'critical', label: 'Critical' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
];

const NotificationsPage = () => {
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [categoryFilter, setCategoryFilter] = useState('');
  const [severityFilter, setSeverityFilter] = useState('');
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);

  // Fetch alerts with filters
  const fetchAlerts = async () => {
    setLoading(true);
    try {
      const params = {};
      if (categoryFilter) params.category = categoryFilter;
      if (severityFilter) params.severity = severityFilter;
      if (showUnreadOnly) params.is_read = false;

      const res = await IssueService.getActiveIssues(params);
      setAlerts(Array.isArray(res.data) ? res.data : []);
    } catch (err) {
      console.error("Failed to load alerts:", err);
    } finally {
      setLoading(false);
    }
  };

  // Initial load and polling
  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 10000);
    return () => clearInterval(interval);
  }, [categoryFilter, severityFilter, showUnreadOnly]);

  // Time formatting (UTC -> KST)
  const formatTimeAgo = (dateString) => {
    if (!dateString) return '';
    const now = new Date();
    const past = new Date(new Date(dateString).getTime() + 9 * 60 * 60 * 1000);
    const diffMins = Math.floor((now - past) / 60000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} mins ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)} hours ago`;
    return `${Math.floor(diffMins / 1440)} days ago`;
  };

  // Resolve single alert
  const handleResolve = async (id) => {
    try {
      setAlerts((prev) => prev.filter(alert => alert.id !== id));
      await IssueService.resolveIssue(id);
    } catch (err) {
      console.error("Failed to resolve issue:", err);
      fetchAlerts();
    }
  };

  // Mark as read
  const handleMarkRead = async (id) => {
    try {
      await IssueService.markAsRead(id);
      setAlerts((prev) => prev.map(a => a.id === id ? { ...a, is_read: true } : a));
    } catch (err) {
      console.error("Failed to mark as read:", err);
    }
  };

  // Resolve all
  const handleClearAll = async () => {
    if (window.confirm('All active alarms will be marked as resolved. Continue?')) {
      try {
        setAlerts([]);
        await IssueService.resolveAll();
      } catch (err) {
        console.error("Failed to resolve all:", err);
        fetchAlerts();
      }
    }
  };

  // Mark all as read
  const handleMarkAllRead = async () => {
    try {
      await IssueService.markAllAsRead();
      setAlerts((prev) => prev.map(a => ({ ...a, is_read: true })));
    } catch (err) {
      console.error("Failed to mark all as read:", err);
    }
  };

  // Get category icon
  const getCategoryIcon = (category) => {
    const cat = CATEGORIES.find(c => c.value === category);
    const Icon = cat?.icon || Settings;
    return <Icon size={14} />;
  };

  const unreadCount = alerts.filter(a => !a.is_read).length;

  return (
    <div className="p-6 bg-gray-50 dark:bg-[#0e1012] h-full text-gray-900 dark:text-white animate-fade-in overflow-y-auto custom-scrollbar transition-colors">

      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <div className="relative">
              <Bell className="text-yellow-500" />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
                </span>
              )}
            </div>
            Active Alarms Center
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-500 mt-1">
            Real-time infrastructure incidents.
            <span className="text-gray-500 dark:text-gray-400 ml-1">(Auto-refreshing every 10s)</span>
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={fetchAlerts}
            className="p-2 bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-400 transition-colors"
            title="Refresh Now"
          >
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
          </button>

          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-300 dark:hover:border-blue-500/50 hover:text-blue-600 dark:hover:text-blue-400 rounded-lg transition-all text-sm font-medium text-gray-600 dark:text-gray-400"
            >
              <Eye size={16} /> Mark All Read
            </button>
          )}

          {alerts.length > 0 && (
            <button
              onClick={handleClearAll}
              className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 hover:bg-red-50 dark:hover:bg-red-900/20 hover:border-red-300 dark:hover:border-red-500/50 hover:text-red-600 dark:hover:text-red-500 rounded-lg transition-all text-sm font-medium text-gray-600 dark:text-gray-400"
            >
              <Trash2 size={16} /> Acknowledge All
            </button>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Category Filter */}
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="px-4 py-2 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300 outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
        >
          {CATEGORIES.map(cat => (
            <option key={cat.value} value={cat.value}>{cat.label}</option>
          ))}
        </select>

        {/* Severity Filter */}
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="px-4 py-2 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-700 dark:text-gray-300 outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
        >
          {SEVERITIES.map(sev => (
            <option key={sev.value} value={sev.value}>{sev.label}</option>
          ))}
        </select>

        {/* Unread Only Toggle */}
        <button
          onClick={() => setShowUnreadOnly(!showUnreadOnly)}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium border transition-all ${showUnreadOnly
              ? 'bg-blue-600 text-white border-blue-600 hover:bg-blue-500'
              : 'bg-white dark:bg-[#1b1d1f] text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
        >
          {showUnreadOnly ? <EyeOff size={16} /> : <Eye size={16} />}
          Unread Only
        </button>

        {/* Active Filter Tags */}
        {(categoryFilter || severityFilter || showUnreadOnly) && (
          <button
            onClick={() => { setCategoryFilter(''); setSeverityFilter(''); setShowUnreadOnly(false); }}
            className="flex items-center gap-1 px-3 py-2 bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-lg text-sm hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
          >
            <X size={14} /> Clear Filters
          </button>
        )}
      </div>

      {/* Stats Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 rounded-xl p-4">
          <div className="text-2xl font-bold text-gray-900 dark:text-white">{alerts.length}</div>
          <div className="text-xs text-gray-500 uppercase font-medium">Total Active</div>
        </div>
        <div className="bg-white dark:bg-[#1b1d1f] border border-red-200 dark:border-red-900/50 rounded-xl p-4">
          <div className="text-2xl font-bold text-red-600 dark:text-red-400">{alerts.filter(a => a.severity === 'critical').length}</div>
          <div className="text-xs text-gray-500 uppercase font-medium">Critical</div>
        </div>
        <div className="bg-white dark:bg-[#1b1d1f] border border-orange-200 dark:border-orange-900/50 rounded-xl p-4">
          <div className="text-2xl font-bold text-orange-600 dark:text-orange-400">{alerts.filter(a => a.severity === 'warning').length}</div>
          <div className="text-xs text-gray-500 uppercase font-medium">Warning</div>
        </div>
        <div className="bg-white dark:bg-[#1b1d1f] border border-blue-200 dark:border-blue-900/50 rounded-xl p-4">
          <div className="text-2xl font-bold text-blue-600 dark:text-blue-400">{unreadCount}</div>
          <div className="text-xs text-gray-500 uppercase font-medium">Unread</div>
        </div>
      </div>

      {/* Alert Cards */}
      <div className="space-y-4">
        {loading && alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20">
            <RefreshCw className="animate-spin text-gray-500 mb-2" />
            <p className="text-gray-500">Loading alerts...</p>
          </div>
        ) : alerts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 border-dashed">
            <CheckCircle size={48} className="text-green-500 mb-4 opacity-50" />
            <h3 className="text-xl font-bold text-gray-700 dark:text-gray-300">All Systems Operational</h3>
            <p className="text-gray-500 mt-1">No active alarms detected.</p>
          </div>
        ) : (
          alerts.map((alert) => (
            <div
              key={alert.id}
              className={`relative flex items-start gap-5 p-5 rounded-xl border transition-all hover:translate-x-1 ${alert.severity === 'critical'
                  ? 'bg-red-50 dark:bg-red-950/10 border-red-200 dark:border-red-900/50 hover:bg-red-100 dark:hover:bg-red-900/20'
                  : alert.severity === 'warning'
                    ? 'bg-orange-50 dark:bg-orange-950/10 border-orange-200 dark:border-orange-900/50 hover:bg-orange-100 dark:hover:bg-orange-900/20'
                    : 'bg-blue-50 dark:bg-blue-950/10 border-blue-200 dark:border-blue-900/50 hover:bg-blue-100 dark:hover:bg-blue-900/20'
                } ${!alert.is_read ? 'ring-2 ring-blue-400/30' : ''}`}
            >
              {/* Icon */}
              <div className={`p-3 rounded-full shrink-0 ${alert.severity === 'critical' ? 'bg-red-100 dark:bg-red-500/20 text-red-500' :
                  alert.severity === 'warning' ? 'bg-orange-100 dark:bg-orange-500/20 text-orange-500' :
                    'bg-blue-100 dark:bg-blue-500/20 text-blue-500'
                }`}>
                {alert.severity === 'critical' ? <XCircle size={24} /> :
                  alert.severity === 'warning' ? <AlertTriangle size={24} /> :
                    <Bell size={24} />}
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <div className="flex justify-between items-start gap-4">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className={`text-lg font-bold ${alert.severity === 'critical' ? 'text-red-600 dark:text-red-400' :
                        alert.severity === 'warning' ? 'text-orange-600 dark:text-orange-400' :
                          'text-blue-600 dark:text-blue-400'
                      }`}>
                      {alert.title}
                    </h3>
                    {!alert.is_read && (
                      <span className="px-2 py-0.5 text-[10px] font-bold bg-blue-600 text-white rounded-full uppercase">New</span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="flex items-center gap-1 px-2 py-1 text-[10px] text-gray-500 dark:text-gray-400 font-mono bg-gray-100 dark:bg-[#0e1012] rounded border border-gray-200 dark:border-gray-800">
                      {getCategoryIcon(alert.category)} {alert.category || 'system'}
                    </span>
                    <span className="flex items-center gap-1.5 text-xs text-gray-500 font-mono bg-gray-100 dark:bg-[#0e1012] px-2 py-1 rounded border border-gray-200 dark:border-gray-800">
                      <Clock size={12} /> {formatTimeAgo(alert.created_at)}
                    </span>
                  </div>
                </div>

                <p className="text-gray-700 dark:text-white mt-1 font-medium">{alert.device}</p>
                <p className="text-gray-600 dark:text-gray-400 text-sm mt-0.5">{alert.message}</p>

                {/* Actions */}
                <div className="mt-4 flex gap-3">
                  <button
                    onClick={() => handleResolve(alert.id)}
                    className="px-4 py-1.5 bg-green-600 hover:bg-green-500 text-white text-xs font-bold rounded shadow-lg shadow-green-900/20 transition-colors flex items-center gap-2"
                  >
                    <CheckCircle size={14} /> Resolve
                  </button>
                  {!alert.is_read && (
                    <button
                      onClick={() => handleMarkRead(alert.id)}
                      className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-xs font-bold rounded transition-colors flex items-center gap-2"
                    >
                      <Eye size={14} /> Mark Read
                    </button>
                  )}
                  {alert.device_id && (
                    <button
                      onClick={() => navigate(`/devices/${alert.device_id}`)}
                      className="px-4 py-1.5 bg-gray-100 dark:bg-[#0e1012] hover:bg-gray-200 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-300 text-xs font-medium rounded border border-gray-200 dark:border-gray-700 transition-colors"
                    >
                      Investigate Device
                    </button>
                  )}
                </div>
              </div>

              {/* Left Color Bar */}
              <div className={`absolute left-0 top-0 bottom-0 w-1 rounded-l-xl ${alert.severity === 'critical' ? 'bg-red-500' :
                  alert.severity === 'warning' ? 'bg-orange-500' :
                    'bg-blue-500'
                }`}></div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default NotificationsPage;