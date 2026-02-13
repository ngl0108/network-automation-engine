import React, { useState, useEffect } from 'react';
import { ApprovalService } from '../../api/services';
import { useToast } from '../../context/ToastContext';
import {
    CheckCircle, XCircle, Clock, FileText, User,
    ChevronRight, Filter, Search, ShieldAlert,
    ArrowRight
} from 'lucide-react';

const ApprovalPage = () => {
    const { toast } = useToast();
    const [requests, setRequests] = useState([]);
    const [loading, setLoading] = useState(false);
    const [filterStatus, setFilterStatus] = useState('pending');
    const [selectedReq, setSelectedReq] = useState(null);
    const [comment, setComment] = useState('');
    const [actionLoading, setActionLoading] = useState(false);

    useEffect(() => {
        loadRequests();
    }, [filterStatus]);

    const loadRequests = async () => {
        setLoading(true);
        try {
            const res = await ApprovalService.getRequests({ status: filterStatus });
            setRequests(res.data);
        } catch (err) {
            console.error("Failed to load requests", err);
        } finally {
            setLoading(false);
        }
    };

    const handleAction = async (type) => { // type: 'approve' | 'reject'
        if (!selectedReq) return;
        if (!window.confirm(`Are you sure you want to ${type} this request?`)) return;

        setActionLoading(true);
        try {
            if (type === 'approve') {
                await ApprovalService.approve(selectedReq.id, comment);
            } else {
                await ApprovalService.reject(selectedReq.id, comment);
            }
            setSelectedReq(null);
            setComment('');
            loadRequests();
        } catch (err) {
            toast.error("Action failed: " + (err.response?.data?.detail || err.message));
        } finally {
            setActionLoading(false);
        }
    };

    const statusColors = {
        pending: 'bg-yellow-100 text-yellow-700 border-yellow-200',
        approved: 'bg-green-100 text-green-700 border-green-200',
        rejected: 'bg-red-100 text-red-700 border-red-200',
        cancelled: 'bg-gray-100 text-gray-700 border-gray-200',
    };

    return (
        <div className="p-6 h-full flex flex-col bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white">

            {/* Header */}
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <ShieldAlert className="text-blue-500" /> Approval Center
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">Review and manage change requests</p>
                </div>
                <div className="flex gap-2">
                    {['pending', 'approved', 'rejected', 'all'].map(status => (
                        <button
                            key={status}
                            onClick={() => setFilterStatus(status === 'all' ? null : status)}
                            className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-all ${(status === 'all' && !filterStatus) || filterStatus === status
                                    ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                                    : 'bg-white dark:bg-[#1b1d1f] text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800 border border-gray-200 dark:border-gray-700'
                                }`}
                        >
                            {status}
                        </button>
                    ))}
                </div>
            </div>

            {/* Content Grid */}
            <div className="flex-1 flex gap-6 overflow-hidden">

                {/* Request List */}
                <div className="w-1/3 min-w-[300px] bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 flex flex-col overflow-hidden shadow-sm">
                    <div className="p-4 border-b border-gray-200 dark:border-gray-700 font-bold flex justify-between items-center">
                        <span>Requests</span>
                        <span className="text-xs font-normal text-gray-500">{requests.length} items</span>
                    </div>

                    <div className="flex-1 overflow-y-auto p-2 space-y-2">
                        {loading ? (
                            <div className="p-8 text-center text-gray-400">Loading...</div>
                        ) : requests.length === 0 ? (
                            <div className="p-8 text-center text-gray-400 text-sm">No requests found.</div>
                        ) : (
                            requests.map(req => (
                                <div
                                    key={req.id}
                                    onClick={() => setSelectedReq(req)}
                                    className={`p-4 rounded-xl border cursor-pointer transition-all ${selectedReq?.id === req.id
                                            ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700 ring-1 ring-blue-300 dark:ring-blue-700'
                                            : 'bg-white dark:bg-[#25282c] border-gray-100 dark:border-gray-700 hover:border-blue-200 dark:hover:border-blue-800'
                                        }`}
                                >
                                    <div className="flex justify-between items-start mb-2">
                                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${statusColors[req.status]}`}>
                                            {req.status}
                                        </span>
                                        <span className="text-xs text-gray-400 flex items-center gap-1">
                                            <Clock size={10} /> {new Date(req.created_at).toLocaleDateString()}
                                        </span>
                                    </div>
                                    <h3 className="font-bold text-sm mb-1 line-clamp-1">{req.title}</h3>
                                    <div className="flex items-center gap-2 text-xs text-gray-500">
                                        <User size={12} /> {req.requester_name || `User #${req.requester_id}`}
                                    </div>
                                </div>
                            ))
                        )}
                    </div>
                </div>

                {/* Detail View */}
                <div className="flex-1 bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 flex flex-col overflow-hidden shadow-sm relative">
                    {selectedReq ? (
                        <div className="flex-1 flex flex-col h-full overflow-hidden">
                            {/* Detail Header */}
                            <div className="p-6 border-b border-gray-200 dark:border-gray-700 shrink-0">
                                <div className="flex justify-between items-start">
                                    <div>
                                        <div className="flex items-center gap-2 mb-2">
                                            <span className={`px-2 py-1 rounded-md text-xs font-bold uppercase border ${statusColors[selectedReq.status]}`}>
                                                {selectedReq.status}
                                            </span>
                                            <span className="text-xs text-gray-500">ID: #{selectedReq.id}</span>
                                        </div>
                                        <h2 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">{selectedReq.title}</h2>
                                        <p className="text-gray-600 dark:text-gray-400 text-sm whitespace-pre-wrap">{selectedReq.description || "No description provided."}</p>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">Requested by</div>
                                        <div className="flex items-center justify-end gap-2 text-sm text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-black/20 px-3 py-1.5 rounded-lg border border-gray-100 dark:border-gray-800">
                                            <User size={14} />
                                            {selectedReq.requester_name}
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Payload Viewer */}
                            <div className="flex-1 overflow-y-auto p-6 bg-gray-50/50 dark:bg-black/5">
                                <h3 className="font-bold text-sm text-gray-700 dark:text-gray-300 mb-3 flex items-center gap-2">
                                    <FileText size={16} /> Request Payload
                                </h3>
                                <div className="bg-[#1e1e1e] rounded-lg p-4 font-mono text-xs text-gray-300 overflow-x-auto shadow-inner border border-gray-700">
                                    <pre>{JSON.stringify(selectedReq.payload, null, 2)}</pre>
                                </div>

                                {/* Comments Section */}
                                <div className="mt-6 space-y-4">
                                    {selectedReq.requester_comment && (
                                        <div className="bg-blue-50 dark:bg-blue-900/10 p-4 rounded-xl border border-blue-100 dark:border-blue-900/30">
                                            <div className="text-xs font-bold text-blue-600 dark:text-blue-400 mb-1">Requester Note</div>
                                            <p className="text-sm text-gray-800 dark:text-gray-200">{selectedReq.requester_comment}</p>
                                        </div>
                                    )}
                                    {selectedReq.approver_comment && (
                                        <div className={`p-4 rounded-xl border ${selectedReq.status === 'approved' ? 'bg-green-50 dark:bg-green-900/10 border-green-100 dark:border-green-900/30' : 'bg-red-50 dark:bg-red-900/10 border-red-100 dark:border-red-900/30'}`}>
                                            <div className={`text-xs font-bold mb-1 ${selectedReq.status === 'approved' ? 'text-green-600' : 'text-red-600'}`}>Approver Decision Note</div>
                                            <p className="text-sm text-gray-800 dark:text-gray-200">{selectedReq.approver_comment}</p>
                                            <div className="text-xs text-gray-500 mt-2 text-right">
                                                - {selectedReq.approver_name} at {new Date(selectedReq.decided_at).toLocaleString()}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Action Footer */}
                            {selectedReq.status === 'pending' && (
                                <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-[#1b1d1f] shrink-0">
                                    <div className="mb-3">
                                        <label className="text-xs font-bold text-gray-500 mb-1 block">Approval/Rejection Comment</label>
                                        <textarea
                                            value={comment}
                                            onChange={(e) => setComment(e.target.value)}
                                            placeholder="Enter reason or feedback..."
                                            className="w-full px-3 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none resize-none h-20"
                                        />
                                    </div>
                                    <div className="flex gap-3 justify-end">
                                        <button
                                            onClick={() => handleAction('reject')}
                                            disabled={actionLoading}
                                            className="px-6 py-2 bg-red-50 hover:bg-red-100 text-red-600 font-medium rounded-lg transition-colors border border-red-200 disabled:opacity-50"
                                        >
                                            Reject
                                        </button>
                                        <button
                                            onClick={() => handleAction('approve')}
                                            disabled={actionLoading}
                                            className="px-6 py-2 bg-green-600 hover:bg-green-500 text-white font-medium rounded-lg shadow-lg shadow-green-500/30 transition-all disabled:opacity-50 flex items-center gap-2"
                                        >
                                            {actionLoading ? <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : <CheckCircle size={16} />}
                                            Approve Request
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    ) : (
                        <div className="flex-1 flex flex-col items-center justify-center text-gray-400">
                            <ShieldAlert size={48} className="text-gray-200 dark:text-gray-700 mb-4" />
                            <p>Select a request to view details</p>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ApprovalPage;
