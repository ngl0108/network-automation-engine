import React, { useState, useEffect, useCallback } from 'react';
import { ZtpService, DeviceService } from '../../api/services';
import { useAuth } from '../../context/AuthContext'; // [RBAC]
import {
    Package, CheckCircle, Clock, AlertCircle, RefreshCw, Plus,
    Trash2, RotateCcw, ChevronRight, Server, Wifi
} from 'lucide-react';

// Status Badge Component
const StatusBadge = ({ status }) => {
    const styles = {
        new: 'bg-yellow-100 text-yellow-700 border-yellow-200',
        ready: 'bg-blue-100 text-blue-700 border-blue-200',
        provisioning: 'bg-purple-100 text-purple-700 border-purple-200',
        completed: 'bg-green-100 text-green-700 border-green-200',
        error: 'bg-red-100 text-red-700 border-red-200',
    };

    const labels = {
        new: 'Pending Approval',
        ready: 'Ready',
        provisioning: 'Provisioning...',
        completed: 'Completed',
        error: 'Error',
    };

    return (
        <span className={`px-2.5 py-1 text-xs font-medium rounded-full border ${styles[status] || styles.new}`}>
            {labels[status] || status}
        </span>
    );
};

// Stat Card Component
const StatCard = ({ icon: Icon, label, value, color }) => (
    <div className="bg-white dark:bg-[#1f2225] rounded-xl p-4 border border-gray-200 dark:border-gray-700 shadow-sm">
        <div className="flex items-center gap-3">
            <div className={`p-2 rounded-lg ${color}`}>
                <Icon size={20} className="text-white" />
            </div>
            <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
                <p className="text-xs text-gray-500">{label}</p>
            </div>
        </div>
    </div>
);

// Approve Modal Component
const ApproveModal = ({ item, sites, templates, onClose, onApprove }) => {
    const [siteId, setSiteId] = useState('');
    const [templateId, setTemplateId] = useState('');
    const [hostname, setHostname] = useState(item?.target_hostname || `Switch-${item?.serial_number?.slice(-4) || 'XXXX'}`);
    const [loading, setLoading] = useState(false);
    const [useRma, setUseRma] = useState(!!item.suggested_device_id); // Default to RMA if available

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        try {
            if (useRma && item.suggested_device_id) {
                // RMA Swap Mode
                await onApprove(item.id, { swap_with_device_id: item.suggested_device_id });
            } else {
                // Standard Mode
                if (!siteId || !templateId) return;
                await onApprove(item.id, { site_id: parseInt(siteId), template_id: parseInt(templateId), target_hostname: hostname });
            }
            onClose();
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 animate-fade-in">
            <div className="bg-white dark:bg-[#1f2225] rounded-xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
                <div className="p-5 border-b border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Approve Device</h3>
                    <p className="text-sm text-gray-500 mt-1">Assign site and configuration template</p>
                </div>

                <div className="p-5 space-y-4">
                    {/* Device Info */}
                    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
                        <p className="text-xs text-gray-500 mb-1">Serial Number</p>
                        <p className="font-mono font-semibold text-gray-900 dark:text-white">{item?.serial_number}</p>
                        <p className="text-xs text-gray-500 mt-2">Platform: {item?.platform || 'Unknown'}</p>
                    </div>

                    {/* RMA Suggestion Alert */}
                    {item.suggested_device_id && (
                        <div className={`p-4 rounded-lg flex gap-3 cursor-pointer border-2 transition-all ${useRma ? 'bg-indigo-50 border-indigo-500' : 'bg-gray-50 border-transparent hover:bg-gray-100'
                            }`} onClick={() => setUseRma(!useRma)}>
                            <div className={`mt-0.5 p-1 rounded-full ${useRma ? 'bg-indigo-600 text-white' : 'bg-gray-300 text-gray-600'}`}>
                                <RotateCcw size={16} />
                            </div>
                            <div>
                                <h4 className="text-sm font-bold text-gray-900 dark:text-white">RMA Suggestion Found!</h4>
                                <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
                                    Matches location of previous device. <br />
                                    {item.suggestion_reason}
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Standard Form (Hidden if RMA selected) */}
                    {(!useRma || !item.suggested_device_id) && (
                        <div className="space-y-4 animate-fade-in">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Target Hostname</label>
                                <input
                                    type="text"
                                    value={hostname}
                                    onChange={(e) => setHostname(e.target.value)}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Assign to Site</label>
                                <select
                                    value={siteId}
                                    onChange={(e) => setSiteId(e.target.value)}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                                >
                                    <option value="">Select a site...</option>
                                    {sites.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5">Configuration Template</label>
                                <select
                                    value={templateId}
                                    onChange={(e) => setTemplateId(e.target.value)}
                                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                                >
                                    <option value="">Select a template...</option>
                                    {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                                </select>
                            </div>
                        </div>
                    )}
                </div>

                <div className="p-5 bg-gray-50 dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 flex justify-end gap-3">
                    <button onClick={onClose} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg">
                        Cancel
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={loading || (!useRma && (!siteId || !templateId))}
                        className={`px-4 py-2 text-sm text-white rounded-lg hover:opacity-90 disabled:opacity-50 flex items-center gap-2 ${useRma ? 'bg-indigo-600' : 'bg-green-600'}`}
                    >
                        {loading ? <RefreshCw size={14} className="animate-spin" /> : (useRma ? <RotateCcw size={14} /> : <CheckCircle size={14} />)}
                        {useRma ? 'Execute RMA Swap' : 'Approve & Provision'}
                    </button>
                </div>
            </div>
        </div>
    );
};

// Main ZTP Page Component
const ZtpPage = () => {
    const { isOperator, isAdmin } = useAuth(); // [RBAC]

    const [queue, setQueue] = useState([]);
    const [stats, setStats] = useState(null);
    const [sites, setSites] = useState([]);
    const [templates, setTemplates] = useState([]);
    const [loading, setLoading] = useState(true);
    const [filter, setFilter] = useState('all');
    const [selectedItem, setSelectedItem] = useState(null);

    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            const [qRes, sRes, sitesRes, templatesRes] = await Promise.all([
                ZtpService.getQueue(),
                ZtpService.getStats(),
                DeviceService.getSites(),
                DeviceService.getTemplates()
            ]);
            setQueue(qRes.data);
            setStats(sRes.data);
            setSites(sitesRes.data);
            setTemplates(templatesRes.data);
        } catch (err) {
            console.error('Failed to load ZTP data:', err);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { loadData(); }, [loadData]);

    const handleApprove = async (itemId, payload) => {
        await ZtpService.approveDevice(itemId, payload);
        loadData();
    };

    const handleDelete = async (itemId) => {
        if (!window.confirm('Delete this item from the queue?')) return;
        await ZtpService.deleteItem(itemId);
        loadData();
    };

    const handleRetry = async (itemId) => {
        await ZtpService.retryItem(itemId);
        loadData();
    };

    const filteredQueue = filter === 'all' ? queue : queue.filter(q => q.status === filter);

    return (
        <div className="h-full overflow-auto bg-[#f4f5f9] dark:bg-[#0e1012] p-6 animate-fade-in">
            {/* Header */}
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                        <Package className="text-indigo-500" /> Zero Touch Provisioning
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">Automatically onboard new network devices</p>
                </div>
                <button
                    onClick={loadData}
                    className="flex items-center gap-2 px-4 py-2 bg-white dark:bg-[#1f2225] border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 text-sm text-gray-700 dark:text-gray-300"
                >
                    <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Refresh
                </button>
            </div>

            {/* Stats Cards */}
            {stats && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
                    <StatCard icon={Clock} label="Pending Approval" value={stats.pending_approval} color="bg-yellow-500" />
                    <StatCard icon={Server} label="Ready" value={stats.ready_to_provision} color="bg-blue-500" />
                    <StatCard icon={Wifi} label="Provisioning" value={stats.in_progress} color="bg-purple-500" />
                    <StatCard icon={CheckCircle} label="Completed Today" value={stats.completed_today} color="bg-green-500" />
                    <StatCard icon={AlertCircle} label="Errors" value={stats.errors} color="bg-red-500" />
                </div>
            )}

            {/* Filter Tabs */}
            <div className="flex gap-2 mb-4 border-b border-gray-200 dark:border-gray-700 pb-3">
                {['all', 'new', 'ready', 'provisioning', 'completed', 'error'].map(f => (
                    <button
                        key={f}
                        onClick={() => setFilter(f)}
                        className={`px-3 py-1.5 text-sm rounded-full capitalize transition-colors ${filter === f
                            ? 'bg-indigo-600 text-white'
                            : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'
                            }`}
                    >
                        {f === 'all' ? 'All' : f}
                    </button>
                ))}
            </div>

            {/* Queue Table */}
            <div className="bg-white dark:bg-[#1f2225] rounded-xl border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
                <table className="w-full">
                    <thead className="bg-gray-50 dark:bg-gray-800">
                        <tr>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Serial Number</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Platform</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">IP Address</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Status</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Suggestion</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {filteredQueue.length === 0 ? (
                            <tr>
                                <td colSpan={7} className="px-4 py-12 text-center text-gray-400">
                                    {loading ? 'Loading...' : 'No devices in queue. Connect a new device to start ZTP.'}
                                </td>
                            </tr>
                        ) : (
                            filteredQueue.map(item => (
                                <tr key={item.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                                    <td className="px-4 py-3 font-mono text-sm text-gray-900 dark:text-white">{item.serial_number}</td>
                                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{item.platform || '-'}</td>
                                    <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{item.ip_address || '-'}</td>
                                    <td className="px-4 py-3"><StatusBadge status={item.status} /></td>
                                    <td className="px-4 py-3">
                                        {item.suggested_device_id ? (
                                            <div className="flex items-center gap-1.5 text-indigo-600 bg-indigo-50 border border-indigo-100 px-2 py-1 rounded text-xs font-medium w-fit">
                                                <RotateCcw size={12} />
                                                RMA Match Found
                                            </div>
                                        ) : (
                                            <span className="text-gray-400 text-xs">-</span>
                                        )}
                                    </td>
                                    <td className="px-4 py-3 text-right">
                                        <div className="flex justify-end gap-1">
                                            {/* [RBAC] Only Network Admin+ can approve */}
                                            {item.status === 'new' && isOperator() && (
                                                <button
                                                    onClick={() => setSelectedItem(item)}
                                                    className="p-1.5 text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-900/30 rounded-lg"
                                                    title="Approve"
                                                >
                                                    <ChevronRight size={16} />
                                                </button>
                                            )}
                                            {item.status === 'error' && isOperator() && (
                                                <button
                                                    onClick={() => handleRetry(item.id)}
                                                    className="p-1.5 text-orange-600 hover:bg-orange-50 dark:hover:bg-orange-900/30 rounded-lg"
                                                    title="Retry"
                                                >
                                                    <RotateCcw size={16} />
                                                </button>
                                            )}
                                            {/* [RBAC] Only Admin can delete */}
                                            {isAdmin() && (
                                                <button
                                                    onClick={() => handleDelete(item.id)}
                                                    className="p-1.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded-lg"
                                                    title="Delete"
                                                >
                                                    <Trash2 size={16} />
                                                </button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Approve Modal */}
            {selectedItem && (
                <ApproveModal
                    item={selectedItem}
                    sites={sites}
                    templates={templates}
                    onClose={() => setSelectedItem(null)}
                    onApprove={handleApprove}
                />
            )}
        </div>
    );
};

export default ZtpPage;
