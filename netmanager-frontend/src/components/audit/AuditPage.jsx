import React, { useState, useEffect } from 'react';
import { SDNService } from '../../api/services';
import {
    Shield, Search, Filter, Clock, User, FileText,
    CheckCircle, AlertTriangle, RefreshCw
} from 'lucide-react';

const AuditPage = () => {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const [actionFilter, setActionFilter] = useState('all');

    const fetchLogs = async () => {
        setLoading(true);
        try {
            // Need to implement getAuditLogs in services.js
            const res = await SDNService.getAuditLogs({ action: actionFilter });
            setLogs(res.data);
        } catch (err) {
            console.error("Failed to fetch logs", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchLogs();
    }, [actionFilter]);

    const getActionBadge = (action) => {
        const colors = {
            CREATE: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
            UPDATE: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
            DELETE: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
            DEPLOY: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
            LOGIN: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
        };
        return (
            <span className={`px-2 py-0.5 rounded textxs font-bold ${colors[action] || 'bg-gray-100 text-gray-600'}`}>
                {action}
            </span>
        );
    };

    return (
        <div className="p-6 bg-[#f4f5f9] dark:bg-[#0e1012] h-full flex flex-col animate-fade-in">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                        <Shield className="text-indigo-500" /> Audit Logs
                    </h1>
                    <p className="text-sm text-gray-500">Track and monitor all system activities and changes.</p>
                </div>
                <button onClick={fetchLogs} className="p-2 bg-white dark:bg-[#1e293b] border border-gray-200 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800">
                    <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                </button>
            </div>

            {/* Filter Bar */}
            <div className="flex gap-2 mb-4 overflow-x-auto pb-2">
                {['all', 'CREATE', 'UPDATE', 'DELETE', 'DEPLOY', 'LOGIN'].map(act => (
                    <button
                        key={act}
                        onClick={() => setActionFilter(act)}
                        className={`px-3 py-1.5 text-sm rounded-full transition-colors whitespace-nowrap ${actionFilter === act
                                ? 'bg-indigo-600 text-white'
                                : 'bg-white dark:bg-[#1f2225] text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-gray-700'
                            }`}
                    >
                        {act === 'all' ? 'All Activities' : act}
                    </button>
                ))}
            </div>

            {/* Logs Table */}
            <div className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden flex-1 flex flex-col">
                <div className="overflow-x-auto overflow-y-auto custom-scrollbar flex-1">
                    <table className="w-full text-left border-collapse">
                        <thead className="bg-gray-50 dark:bg-[#25282c] sticky top-0 z-10">
                            <tr>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Timestamp</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">User</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Action</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Resource</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">Details</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-500 uppercase">IP Addr</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                            {logs.map((log) => (
                                <tr key={log.id} className="hover:bg-gray-50 dark:hover:bg-[#25282c] transition-colors">
                                    <td className="px-6 py-4 text-sm text-gray-500 whitespace-nowrap">
                                        {new Date(log.timestamp).toLocaleString()}
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-2">
                                            <div className="w-6 h-6 rounded-full bg-indigo-100 dark:bg-indigo-900/50 flex items-center justify-center text-xs font-bold text-indigo-600 dark:text-indigo-400">
                                                {log.username?.charAt(0).toUpperCase() || '?'}
                                            </div>
                                            <span className="text-sm font-medium text-gray-900 dark:text-white">{log.username}</span>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        {getActionBadge(log.action)}
                                    </td>
                                    <td className="px-6 py-4">
                                        <div className="text-sm text-gray-900 dark:text-white font-medium">{log.resource_type}</div>
                                        <div className="text-xs text-gray-500">{log.resource_name}</div>
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-300 max-w-xs truncate" title={log.details}>
                                        {log.details || '-'}
                                    </td>
                                    <td className="px-6 py-4 text-xs font-mono text-gray-500">
                                        {log.ip_address || '-'}
                                    </td>
                                </tr>
                            ))}
                            {logs.length === 0 && !loading && (
                                <tr>
                                    <td colSpan={6} className="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
                                        No audit records found.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default AuditPage;
