import React, { useState, useEffect } from 'react';
import { ComplianceService, DeviceService, JobService } from '../../api/services';
import { useToast } from '../../context/ToastContext';
import {
    Shield, CheckCircle, XCircle, AlertTriangle, Plus, Trash2,
    Search, RefreshCw, ChevronDown, ChevronRight, FileText, Play
} from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend } from 'recharts';
import DriftView from './DriftView'; // [NEW] Import

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

const CompliancePage = () => {
    const { toast } = useToast();
    const [activeTab, setActiveTab] = useState('dashboard');
    // ... (skip lines) ...

    const [loading, setLoading] = useState(false);
    const [standards, setStandards] = useState([]);
    const [reports, setReports] = useState([]);
    const [devices, setDevices] = useState([]);
    const [exportingReports, setExportingReports] = useState(false);
    const [reportDeviceId, setReportDeviceId] = useState('');

    // Modal States
    const [showStdModal, setShowStdModal] = useState(false);
    const [showRuleModal, setShowRuleModal] = useState(false);
    const [selectedStdId, setSelectedStdId] = useState(null);

    // Data Fetching
    const loadData = async () => {
        setLoading(true);
        try {
            const [stdRes, reportRes, devRes] = await Promise.all([
                ComplianceService.getStandards(),
                ComplianceService.getReports(),
                DeviceService.getAll()
            ]);
            setStandards(stdRes.data || []);
            setReports(reportRes.data || []);
            setDevices(devRes.data || []);
        } catch (err) {
            console.error("Failed to load compliance data", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    // --- Actions ---

    const handleCreateStandard = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const payload = {
            name: formData.get('name'),
            description: formData.get('description'),
            device_family: formData.get('device_family')
        };
        try {
            await ComplianceService.createStandard(payload);
            setShowStdModal(false);
            loadData();
        } catch (err) {
            toast.error("Failed to create standard");
        }
    };

    const handleAddRule = async (e) => {
        e.preventDefault();
        const formData = new FormData(e.target);
        const payload = {
            name: formData.get('name'),
            description: formData.get('description'),
            severity: formData.get('severity'),
            check_type: formData.get('check_type'),
            pattern: formData.get('pattern'),
            remediation: formData.get('remediation')
        };
        try {
            await ComplianceService.addRule(selectedStdId, payload);
            setShowRuleModal(false);
            loadData(); // Refresh to see new rule
        } catch (err) {
            toast.error("Failed to add rule");
        }
    };

    const handleDeleteStandard = async (id) => {
        if (!window.confirm("Delete this standard and all its rules?")) return;
        try {
            await ComplianceService.deleteStandard(id);
            loadData();
        } catch (err) { toast.error("Failed to delete standard"); }
    };

    const handleDeleteRule = async (id) => {
        if (!window.confirm("Delete this rule?")) return;
        try {
            await ComplianceService.deleteRule(id);
            loadData();
        } catch (err) { toast.error("Failed to delete rule"); }
    };

    const handleScan = async () => {
        const targetIds = devices.map(d => d.id); // Scan all for simplicity, or add selection logic
        if (targetIds.length === 0) return toast.warning("No devices to scan");

        setLoading(true);
        try {
            const res = await ComplianceService.runScan({ device_ids: targetIds });
            const jobId = res?.data?.job_id;
            if (!jobId) {
                toast.success("Scan completed successfully");
                loadData();
                return;
            }
            toast.success(`Scan queued (job: ${jobId})`);
            const start = Date.now();
            while (Date.now() - start < 120000) {
                const s = await JobService.getStatus(jobId);
                if (s?.data?.ready) {
                    if (s?.data?.successful) {
                        toast.success("Scan finished");
                    } else {
                        toast.error("Scan failed");
                    }
                    break;
                }
                await new Promise(r => setTimeout(r, 1000));
            }
            loadData();
        } catch (err) {
            toast.error("Scan failed: " + err.message);
        } finally {
            setLoading(false);
        }
    };

    const handleExportReports = async (format) => {
        setExportingReports(true);
        try {
            const params = reportDeviceId ? { format, device_id: reportDeviceId } : { format };
            const res = await ComplianceService.exportReports(params);
            const suffix = reportDeviceId ? `_device_${reportDeviceId}` : '';
            const filename = parseFilename(res.headers?.['content-disposition']) || `compliance_reports${suffix}.${format}`;
            const contentType = res.headers?.['content-type'];
            downloadBlob(res.data, filename, contentType);
            toast.success("다운로드를 시작했습니다.");
        } catch (err) {
            toast.error("내보내기 실패: " + (err.response?.data?.detail || err.message));
        } finally {
            setExportingReports(false);
        }
    };

    // --- Components ---

    const DashboardView = () => {
        const totalReports = reports.length;
        const compliant = reports.filter(r => r.status === 'compliant').length;
        const violations = totalReports - compliant;
        const score = totalReports > 0 ? Math.round((compliant / totalReports) * 100) : 100;

        const pieData = [
            { name: 'Compliant', value: compliant, color: '#10b981' },
            { name: 'Violation', value: violations, color: '#ef4444' }
        ];

        return (
            <div className="space-y-6">
                <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm">
                        <h3 className="text-gray-500 font-medium text-sm uppercase">Overall Compliance</h3>
                        <div className="mt-2 text-4xl font-bold text-gray-900 dark:text-white">{score}%</div>
                        <p className="text-xs text-green-500 mt-1">Based on {totalReports} devices</p>
                    </div>
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm">
                        <h3 className="text-gray-500 font-medium text-sm uppercase">Compliant Devices</h3>
                        <div className="mt-2 text-4xl font-bold text-green-500">{compliant}</div>
                    </div>
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm">
                        <h3 className="text-gray-500 font-medium text-sm uppercase">Devices with Violations</h3>
                        <div className="mt-2 text-4xl font-bold text-red-500">{violations}</div>
                    </div>
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-sm flex items-center justify-center">
                        {/* Scan Button */}
                        <button onClick={handleScan} disabled={loading} className="w-full h-full flex flex-col items-center justify-center gap-2 text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-xl transition-all">
                            <Play size={32} />
                            <span className="font-bold">Run Full Scan</span>
                        </button>
                    </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Chart */}
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 h-80">
                        <h3 className="font-bold text-gray-900 dark:text-white mb-4">Compliance Status Distribution</h3>
                        <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                                <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={5} dataKey="value">
                                    {pieData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Pie>
                                <Tooltip />
                                <Legend />
                            </PieChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Recent Violations List */}
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 h-80 overflow-y-auto custom-scrollbar">
                        <h3 className="font-bold text-gray-900 dark:text-white mb-4">Recent Violations</h3>
                        <div className="space-y-3">
                            {reports.filter(r => r.status === 'violation').slice(0, 5).map(r => (
                                <div key={r.device_id} className="flex items-center justify-between p-3 bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 rounded-lg">
                                    <div className="flex items-center gap-3">
                                        <div className="p-2 bg-red-100 dark:bg-red-900/30 rounded-full text-red-500"><XCircle size={16} /></div>
                                        <div>
                                            <div className="font-medium text-gray-900 dark:text-white">{r.device_name}</div>
                                            <div className="text-xs text-red-500">Compliance Score: {Math.round(r.score)}%</div>
                                        </div>
                                    </div>
                                    <button onClick={() => setActiveTab('reports')} className="text-xs text-gray-500 hover:text-gray-900 dark:hover:text-white">View</button>
                                </div>
                            ))}
                            {reports.filter(r => r.status === 'violation').length === 0 && (
                                <div className="text-center text-gray-500 py-10">No violations found 🎉</div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    const ReportsView = () => {
        const filteredReports = reportDeviceId
            ? reports.filter(r => String(r.device_id) === String(reportDeviceId))
            : reports;
        return (
            <div className="bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 flex justify-between items-center bg-gray-50 dark:bg-[#25282c]">
                    <h3 className="font-bold text-gray-900 dark:text-white">Compliance Reports</h3>
                    <div className="flex items-center gap-2">
                        <select
                            value={reportDeviceId}
                            onChange={(e) => setReportDeviceId(e.target.value)}
                            className="h-8 px-2 text-sm rounded-lg bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-200"
                        >
                            <option value="">All devices</option>
                            {devices
                                .slice()
                                .sort((a, b) => String(a?.name || '').localeCompare(String(b?.name || '')))
                                .map(d => (
                                    <option key={d.id} value={d.id}>{d.name} ({d.ip_address})</option>
                                ))}
                        </select>
                        <button onClick={() => handleExportReports('xlsx')} disabled={exportingReports} className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 rounded-lg text-sm">
                            <FileText size={14} /> Export XLSX
                        </button>
                        <button onClick={() => handleExportReports('pdf')} disabled={exportingReports} className="flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-700 dark:text-gray-200 rounded-lg text-sm">
                            <FileText size={14} /> Export PDF
                        </button>
                        <button onClick={handleScan} disabled={loading} className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-60 text-white rounded-lg text-sm">
                            <Play size={14} /> Run New Scan
                        </button>
                    </div>
                </div>
                <table className="w-full text-left text-sm">
                    <thead className="bg-gray-50 dark:bg-[#25282c] text-gray-500 font-medium border-b border-gray-200 dark:border-gray-700">
                        <tr>
                            <th className="px-6 py-4">Device</th>
                            <th className="px-6 py-4">Status</th>
                            <th className="px-6 py-4">Score</th>
                            <th className="px-6 py-4">Last Checked</th>
                            <th className="px-6 py-4 text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {filteredReports.map(r => (
                            <tr key={r.device_id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50">
                                <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{r.device_name}</td>
                                <td className="px-6 py-4">
                                    <span className={`px-2 py-1 rounded-full text-xs font-bold ${r.status === 'compliant' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}>
                                        {r.status.toUpperCase()}
                                    </span>
                                </td>
                                <td className="px-6 py-4">
                                    <div className="w-24 bg-gray-200 rounded-full h-2 overflow-hidden">
                                        <div className={`h-full ${r.score >= 100 ? 'bg-green-500' : r.score >= 80 ? 'bg-yellow-500' : 'bg-red-500'}`} style={{ width: `${r.score}%` }}></div>
                                    </div>
                                    <span className="text-xs text-gray-500 mt-1 block">{Math.round(r.score)}%</span>
                                </td>
                                <td className="px-6 py-4 text-gray-500">{new Date(r.last_checked).toLocaleString()}</td>
                                <td className="px-6 py-4 text-right">
                                    {/* Details could be a modal, for now simplified */}
                                    <button className="text-blue-500 hover:underline">View Details</button>
                                </td>
                            </tr>
                        ))}
                        {filteredReports.length === 0 && (
                            <tr><td colSpan="5" className="px-6 py-10 text-center text-gray-500">No reports generated yet. Run a scan.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        );
    };

    const StandardsView = () => {
        const [expandedStd, setExpandedStd] = useState(null);

        return (
            <div className="space-y-6">
                <div className="flex justify-end">
                    <button onClick={() => setShowStdModal(true)} className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg">
                        <Plus size={16} /> Create Standard
                    </button>
                </div>

                <div className="space-y-4">
                    {standards.map(std => (
                        <div key={std.id} className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden">
                            <div
                                className="p-4 flex items-center justify-between cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                                onClick={() => setExpandedStd(expandedStd === std.id ? null : std.id)}
                            >
                                <div className="flex items-center gap-4">
                                    {expandedStd === std.id ? <ChevronDown size={20} className="text-gray-400" /> : <ChevronRight size={20} className="text-gray-400" />}
                                    <div>
                                        <h3 className="font-bold text-gray-900 dark:text-white">{std.name}</h3>
                                        <p className="text-xs text-gray-500">{std.description} • {std.device_family}</p>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="text-xs px-2 py-1 bg-gray-100 dark:bg-gray-800 rounded text-gray-500">{std.rules.length} Rules</span>
                                    <button onClick={(e) => { e.stopPropagation(); handleDeleteStandard(std.id); }} className="p-2 hover:bg-red-50 text-gray-400 hover:text-red-500 rounded"><Trash2 size={16} /></button>
                                </div>
                            </div>

                            {/* Rules List */}
                            {expandedStd === std.id && (
                                <div className="border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-black/20 p-4">
                                    <div className="mb-4 flex justify-between items-center">
                                        <h4 className="text-sm font-bold text-gray-700 dark:text-gray-300">Compliance Rules</h4>
                                        <button
                                            onClick={() => { setSelectedStdId(std.id); setShowRuleModal(true); }}
                                            className="text-xs flex items-center gap-1 bg-white dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 px-3 py-1.5 rounded-lg hover:border-blue-500 text-gray-600 dark:text-gray-400"
                                        >
                                            <Plus size={12} /> Add Rule
                                        </button>
                                    </div>

                                    <div className="space-y-2">
                                        {std.rules.map(rule => (
                                            <div key={rule.id} className="flex items-start justify-between p-3 bg-white dark:bg-[#25282c] rounded-lg border border-gray-200 dark:border-gray-700 text-sm">
                                                <div className="flex-1">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <span className={`w-2 h-2 rounded-full ${rule.severity === 'critical' ? 'bg-red-500' : rule.severity === 'warning' ? 'bg-orange-500' : 'bg-blue-500'}`}></span>
                                                        <span className="font-bold text-gray-800 dark:text-gray-200">{rule.name}</span>
                                                        <span className="text-[10px] uppercase bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-500">{rule.check_type}</span>
                                                    </div>
                                                    <p className="text-gray-500 dark:text-gray-400 text-xs mb-2">{rule.description}</p>
                                                    <code className="block bg-gray-100 dark:bg-black/30 p-2 rounded text-xs font-mono text-gray-700 dark:text-gray-300 overflow-x-auto">
                                                        {rule.pattern}
                                                    </code>
                                                </div>
                                                <button onClick={() => handleDeleteRule(rule.id)} className="text-gray-400 hover:text-red-500 ml-4"><Trash2 size={14} /></button>
                                            </div>
                                        ))}
                                        {std.rules.length === 0 && <p className="text-center text-gray-400 text-xs py-2">No rules defined yet.</p>}
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </div>
        );
    };

    return (
        <div className="p-6 h-full flex flex-col bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white overflow-hidden">

            {/* Header */}
            <div className="flex justify-between items-center mb-6 shrink-0">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <Shield className="text-green-500" /> Security Compliance Audit
                    </h1>
                    <p className="text-sm text-gray-500 mt-1">Automated configuration compliance scanning and enforcement</p>
                </div>

                <div className="flex bg-white dark:bg-[#1b1d1f] p-1 rounded-xl border border-gray-200 dark:border-gray-700">
                    {['dashboard', 'reports', 'standards', 'drift'].map(tab => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-all ${activeTab === tab
                                ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/30'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                                }`}
                        >
                            {tab}
                        </button>
                    ))}
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 overflow-y-auto custom-scrollbar">
                {activeTab === 'dashboard' && <DashboardView />}
                {activeTab === 'reports' && <ReportsView />}
                {activeTab === 'standards' && <StandardsView />}
                {activeTab === 'drift' && <DriftView devices={devices} />}
            </div>

            {/* Modals */}
            {showStdModal && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-md rounded-2xl p-6 shadow-2xl animate-scale-in">
                        <h2 className="text-xl font-bold mb-4">Create New Standard</h2>
                        <form onSubmit={handleCreateStandard}>
                            <div className="space-y-4">
                                <input name="name" placeholder="Standard Name" required className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg" />
                                <input name="description" placeholder="Description" className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg" />
                                <select name="device_family" className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg">
                                    <option value="cisco_ios">Cisco IOS</option>
                                    <option value="cisco_nxos">Cisco NX-OS</option>
                                </select>
                            </div>
                            <div className="flex justify-end gap-2 mt-6">
                                <button type="button" onClick={() => setShowStdModal(false)} className="px-4 py-2 text-gray-500 hover:bg-gray-100 rounded-lg">Cancel</button>
                                <button type="submit" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg">Create</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {showRuleModal && (
                <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-lg rounded-2xl p-6 shadow-2xl animate-scale-in">
                        <h2 className="text-xl font-bold mb-4">Add Compliance Rule</h2>
                        <form onSubmit={handleAddRule}>
                            <div className="space-y-4">
                                <input name="name" placeholder="Rule Name" required className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg" />
                                <textarea name="description" placeholder="Description & Rationale" className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg" />

                                <div className="grid grid-cols-2 gap-4">
                                    <select name="severity" className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg">
                                        <option value="critical">Critical</option>
                                        <option value="warning">Warning</option>
                                        <option value="info">Info</option>
                                    </select>
                                    <select name="check_type" className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg">
                                        <option value="simple_match">Must Contain (String)</option>
                                        <option value="absent_match">Must NOT Contain</option>
                                        <option value="regex_match">Regex Match</option>
                                    </select>
                                </div>

                                <div>
                                    <label className="text-xs text-gray-500 mb-1 block ml-1">Pattern to match in config</label>
                                    <textarea name="pattern" placeholder="e.g. service password-encryption" required rows={3} className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg font-mono text-sm" />
                                </div>
                            </div>
                            <div className="flex justify-end gap-2 mt-6">
                                <button type="button" onClick={() => setShowRuleModal(false)} className="px-4 py-2 text-gray-500 hover:bg-gray-100 rounded-lg">Cancel</button>
                                <button type="submit" className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg">Add Rule</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

        </div>
    );
};

export default CompliancePage;
