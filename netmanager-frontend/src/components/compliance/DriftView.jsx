import React, { useState, useEffect } from 'react';
import { ComplianceService } from '../../api/services';
import { useToast } from '../../context/ToastContext';
import {
    Clock, CheckCircle, AlertTriangle, RefreshCw,
    FileText, ArrowRight, ShieldCheck, History
} from 'lucide-react';

const DriftView = ({ devices }) => {
    const { toast } = useToast();
    const [selectedDevice, setSelectedDevice] = useState(null);
    const [backups, setBackups] = useState([]);
    const [driftResult, setDriftResult] = useState(null);
    const [loading, setLoading] = useState(false);
    const [processing, setProcessing] = useState(false);

    // 장비 선택 시 데이터 로드
    useEffect(() => {
        if (selectedDevice) {
            loadDeviceData(selectedDevice.id);
        }
    }, [selectedDevice]);

    const loadDeviceData = async (deviceId) => {
        setLoading(true);
        try {
            // 1. Load Backups
            const backupRes = await ComplianceService.getBackups(deviceId);
            setBackups(backupRes.data || []);

            // 2. Load Drift Status (Check immediately)
            try {
                const driftRes = await ComplianceService.checkDrift(deviceId);
                setDriftResult(driftRes.data);
            } catch (e) {
                // Golden이 없는 경우 등
                setDriftResult({ status: 'no_golden', message: 'No Golden Config set' });
            }
        } catch (err) {
            console.error("Failed to load drift data", err);
        } finally {
            setLoading(false);
        }
    };

    const handleSetGolden = async (backupId) => {
        if (!window.confirm("Set this backup as current Golden Config?")) return;
        setProcessing(true);
        try {
            await ComplianceService.setGolden(backupId);
            await loadDeviceData(selectedDevice.id); // Reload
        } catch (err) {
            toast.error("Failed to set Golden Config");
        } finally {
            setProcessing(false);
        }
    };

    const handleCheckDrift = async () => {
        if (!selectedDevice) return;
        setProcessing(true);
        try {
            const res = await ComplianceService.checkDrift(selectedDevice.id);
            setDriftResult(res.data);
        } catch (err) {
            toast.error("Drift check failed");
        } finally {
            setProcessing(false);
        }
    };

    // Diff Rendering Helper
    const renderDiff = (diffLines) => {
        if (!diffLines || diffLines.length === 0) return <div className="text-gray-500 italic p-4">No differences found. Configs match exactly!</div>;

        return (
            <div className="font-mono text-xs overflow-x-auto bg-[#1e1e1e] text-gray-300 p-4 rounded-lg shadow-inner h-[500px] overflow-y-auto">
                {diffLines.map((line, idx) => {
                    let style = {};
                    if (line.startsWith('---') || line.startsWith('+++')) style = { color: '#888' };
                    else if (line.startsWith('@@')) style = { color: '#aaa', fontStyle: 'italic' };
                    else if (line.startsWith('+')) style = { backgroundColor: '#1e3a29', color: '#4ade80', display: 'block' }; // Added (Green)
                    else if (line.startsWith('-')) style = { backgroundColor: '#451e1e', color: '#f87171', display: 'block' }; // Removed (Red)

                    return (
                        <div key={idx} style={style} className="whitespace-pre px-1 py-0.5">
                            {line}
                        </div>
                    );
                })}
            </div>
        );
    };

    return (
        <div className="flex h-full gap-6">
            {/* Sidebar: Device List */}
            <div className="w-1/4 min-w-[250px] bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 flex flex-col overflow-hidden">
                <div className="p-4 border-b border-gray-200 dark:border-gray-700 font-bold text-gray-900 dark:text-white flex items-center gap-2">
                    <ShieldCheck size={18} className="text-blue-500" />
                    Target Devices
                </div>
                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                    {devices.map(dev => (
                        <button
                            key={dev.id}
                            onClick={() => setSelectedDevice(dev)}
                            className={`w-full text-left px-4 py-3 rounded-lg flex items-center justify-between transition-colors ${selectedDevice?.id === dev.id
                                    ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
                                    : 'hover:bg-gray-50 dark:hover:bg-gray-800'
                                }`}
                        >
                            <span className="font-medium text-sm text-gray-700 dark:text-gray-200">{dev.name}</span>
                            {/* Status Indicator (Placeholder logic) */}
                            <div className="w-2 h-2 rounded-full bg-gray-300"></div>
                        </button>
                    ))}
                </div>
            </div>

            {/* Main Content */}
            <div className="flex-1 flex flex-col gap-6 overflow-hidden">
                {selectedDevice ? (
                    <>
                        {/* Top: Controls & Summary */}
                        <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shrink-0">
                            <div className="flex justify-between items-start mb-6">
                                <div>
                                    <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                        {selectedDevice.name}
                                        <span className="text-xs font-normal text-gray-500 px-2 py-0.5 bg-gray-100 dark:bg-gray-800 rounded-full">{selectedDevice.ip_address}</span>
                                    </h2>
                                    <p className="text-sm text-gray-500 mt-1">
                                        Last Checked: {driftResult?.last_checked ? new Date(driftResult.last_checked).toLocaleString() : 'Just now'}
                                    </p>
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={handleCheckDrift}
                                        disabled={processing || loading}
                                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg disabled:opacity-50"
                                    >
                                        <RefreshCw size={16} className={processing ? "animate-spin" : ""} />
                                        Run Drift Check
                                    </button>
                                </div>
                            </div>

                            <div className="flex gap-4">
                                {/* Golden Config Card */}
                                <div className="flex-1 p-4 bg-gray-50 dark:bg-black/20 rounded-xl border border-gray-200 dark:border-gray-800">
                                    <div className="flex justify-between items-center mb-2">
                                        <h3 className="font-bold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                                            <ShieldCheck size={16} className="text-yellow-500" /> Golden Config
                                        </h3>
                                        <button className="text-xs text-blue-500 hover:underline">View</button>
                                    </div>
                                    {driftResult?.golden_id ? (
                                        <div className="text-sm">
                                            <div className="font-mono text-xs bg-white dark:bg-black/30 px-2 py-1 rounded border border-gray-200 dark:border-gray-700 w-fit">
                                                ID: #{driftResult.golden_id}
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="text-sm text-red-500 flex items-center gap-1">
                                            <AlertTriangle size={14} /> Not Set
                                        </div>
                                    )}
                                </div>

                                {/* Current Status Card */}
                                <div className="flex-1 p-4 bg-gray-50 dark:bg-black/20 rounded-xl border border-gray-200 dark:border-gray-800">
                                    <h3 className="font-bold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                                        <Clock size={16} className="text-blue-500" /> Current Status
                                    </h3>
                                    {driftResult ? (
                                        <div className={`text-lg font-bold flex items-center gap-2 ${driftResult.status === 'compliant' ? 'text-green-500' : 'text-red-500'}`}>
                                            {driftResult.status === 'compliant' ? <CheckCircle size={20} /> : <AlertTriangle size={20} />}
                                            {driftResult.status === 'compliant' ? 'Compliant' : 'Drift Detected'}
                                        </div>
                                    ) : (
                                        <div className="text-gray-400">Unknown</div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Bottom: Diff Viewer & History */}
                        <div className="flex-1 flex gap-6 overflow-hidden">
                            {/* Left: Backup History (for Golden Selection) */}
                            <div className="w-1/3 bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 flex flex-col overflow-hidden">
                                <div className="p-4 border-b border-gray-200 dark:border-gray-700 font-bold flex items-center gap-2">
                                    <History size={16} /> Config History
                                </div>
                                <div className="flex-1 overflow-y-auto p-2">
                                    {backups.map(backup => (
                                        <div key={backup.id} className="p-3 mb-2 rounded-lg border border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group">
                                            <div className="flex justify-between items-start">
                                                <div>
                                                    <div className="font-mono text-xs text-gray-500">#{backup.id}</div>
                                                    <div className="font-medium text-sm text-gray-900 dark:text-white my-1">
                                                        {new Date(backup.created_at).toLocaleString()}
                                                    </div>
                                                    <div className="text-xs text-gray-500">{backup.size} bytes</div>
                                                </div>
                                                {backup.is_golden && (
                                                    <span className="px-2 py-0.5 bg-yellow-100 text-yellow-700 text-[10px] font-bold rounded-full border border-yellow-200">
                                                        GOLDEN
                                                    </span>
                                                )}
                                            </div>
                                            {!backup.is_golden && (
                                                <button
                                                    onClick={() => handleSetGolden(backup.id)}
                                                    className="mt-2 w-full text-xs py-1.5 bg-gray-100 dark:bg-gray-700 hover:bg-blue-50 dark:hover:bg-blue-900/30 text-gray-600 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 rounded transition-colors hidden group-hover:block"
                                                >
                                                    Set as Golden
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Right: Diff Viewer */}
                            <div className="flex-1 bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 flex flex-col overflow-hidden">
                                <div className="p-4 border-b border-gray-200 dark:border-gray-700 font-bold flex items-center justify-between">
                                    <div className="flex items-center gap-2">
                                        <FileText size={16} /> Configuration Drift Analysis
                                    </div>
                                    {driftResult?.status === 'drift' && (
                                        <span className="text-xs px-2 py-1 bg-red-100 text-red-600 rounded font-bold">
                                            Changes found
                                        </span>
                                    )}
                                </div>
                                <div className="flex-1 bg-[#1e1e1e] overflow-hidden relative">
                                    {driftResult?.diff_lines ? (
                                        renderDiff(driftResult.diff_lines)
                                    ) : (
                                        <div className="flex items-center justify-center h-full text-gray-500">
                                            Select a device and run check to see details
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex items-center justify-center text-gray-400 flex-col gap-4">
                        <ShieldCheck size={48} className="text-gray-200 dark:text-gray-700" />
                        <p>Select a device to manage configuration drift</p>
                    </div>
                )}
            </div>
        </div>
    );
};

export default DriftView;
