import React, { useState, useEffect, useRef } from 'react';
import { DiscoveryService, DeviceService, SettingsService } from '../../api/services';
import { useToast } from '../../context/ToastContext';
import {
    Radar, Play, RefreshCw, CheckCircle, Server, Terminal, AlertTriangle, Plus
} from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';

// ... (imports remain the same)

const DiscoveryPage = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { toast } = useToast();
    const [step, setStep] = useState(1); // 1: Input, 2: Scanning, 3: Results
    const [jobId, setJobId] = useState(null);

    // Input State
    const [scanMode, setScanMode] = useState('cidr'); // 'cidr' | 'seed'
    const [cidr, setCidr] = useState("192.168.1.0/24");
    const [community, setCommunity] = useState("public");
    const [seedDeviceId, setSeedDeviceId] = useState('');
    const [seedIp, setSeedIp] = useState('');
    const [maxDepth, setMaxDepth] = useState(2);

    const [snmpVersion, setSnmpVersion] = useState('v2c');
    const [snmpPort, setSnmpPort] = useState(161);
    const [snmpV3Username, setSnmpV3Username] = useState('');
    const [snmpV3SecurityLevel, setSnmpV3SecurityLevel] = useState('authPriv');
    const [snmpV3AuthProto, setSnmpV3AuthProto] = useState('sha');
    const [snmpV3AuthKey, setSnmpV3AuthKey] = useState('');
    const [snmpV3PrivProto, setSnmpV3PrivProto] = useState('aes');
    const [snmpV3PrivKey, setSnmpV3PrivKey] = useState('');
    const [seedDevices, setSeedDevices] = useState([]);
    const [loadingSeeds, setLoadingSeeds] = useState(false);
    const [generalSettings, setGeneralSettings] = useState({});

    // Job State
    const [jobStatus, setJobStatus] = useState(null);
    const [logs, setLogs] = useState("");
    const [progress, setProgress] = useState(0);

    // Results State
    const [results, setResults] = useState([]);
    const [expanded, setExpanded] = useState({});
    const logEndRef = useRef(null);
    const esRef = useRef(null);

    const parseCidrList = (raw) => {
        const parts = String(raw || '').replaceAll('\n', ',').split(',');
        return parts.map(s => s.trim()).filter(Boolean);
    };

    const ipv4ToInt = (ip) => {
        const s = String(ip || '').trim();
        const m = s.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
        if (!m) return null;
        const octets = [m[1], m[2], m[3], m[4]].map(x => Number(x));
        if (octets.some(o => Number.isNaN(o) || o < 0 || o > 255)) return null;
        return ((octets[0] << 24) >>> 0) + (octets[1] << 16) + (octets[2] << 8) + octets[3];
    };

    const cidrContains = (cidr, ip) => {
        const s = String(cidr || '').trim();
        const m = s.match(/^(.+)\/(\d{1,2})$/);
        if (!m) return false;
        const baseIp = ipv4ToInt(m[1]);
        if (baseIp === null) return false;
        const maskBits = Number(m[2]);
        if (Number.isNaN(maskBits) || maskBits < 0 || maskBits > 32) return false;
        const ipInt = ipv4ToInt(ip);
        if (ipInt === null) return false;
        const mask = maskBits === 0 ? 0 : (0xffffffff << (32 - maskBits)) >>> 0;
        return (baseIp & mask) === (ipInt & mask);
    };

    const checkScopeAllowed = (ip, includeCidrs, excludeCidrs) => {
        const ipStr = String(ip || '').trim();
        if (!ipStr) return { ok: true, reason: '' };
        if (ipv4ToInt(ipStr) === null) return { ok: false, reason: 'IP 형식이 올바르지 않습니다.' };
        const excludes = Array.isArray(excludeCidrs) ? excludeCidrs : [];
        const includes = Array.isArray(includeCidrs) ? includeCidrs : [];
        if (excludes.some(c => cidrContains(c, ipStr))) return { ok: false, reason: 'Exclude CIDR 범위에 포함됩니다.' };
        if (includes.length > 0 && !includes.some(c => cidrContains(c, ipStr))) return { ok: false, reason: 'Include CIDR 범위 밖입니다.' };
        return { ok: true, reason: '' };
    };

    useEffect(() => {
        let cancelled = false;
        const run = async () => {
            try {
                const res = await SettingsService.getGeneral();
                if (cancelled) return;
                setGeneralSettings(res.data || {});
            } catch (e) {
                if (!cancelled) setGeneralSettings({});
            }
        };
        run();
        return () => { cancelled = true; };
    }, []);

    // Poll Job Status
    useEffect(() => {
        let interval;
        if (step === 2 && jobId) {
            interval = setInterval(async () => {
                try {
                    const res = await DiscoveryService.getJobStatus(jobId);
                    setJobStatus(res.data.status);
                    setLogs(res.data.logs);
                    setProgress(res.data.progress);

                    if (res.data.status === 'completed' || res.data.status === 'failed') {
                        clearInterval(interval);
                        if (res.data.status === 'completed') {
                            // Load results automatically after short delay
                            setTimeout(loadResults, 1000);
                        }
                    }
                } catch (err) {
                    console.error("Polling failed", err);
                }
            }, 2000);
        }
        return () => clearInterval(interval);
    }, [step, jobId]);

    useEffect(() => {
        if (step !== 2 || !jobId) return;
        if (esRef.current) {
            try { esRef.current.close(); } catch (e) { void e; }
            esRef.current = null;
        }

        const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
        const url = `${API_BASE_URL}/discovery/jobs/${jobId}/stream`;
        const es = new EventSource(url);
        esRef.current = es;

        es.addEventListener('device', (evt) => {
            try {
                const dev = JSON.parse(evt.data);
                setResults(prev => {
                    const idx = prev.findIndex(x => x.id === dev.id);
                    if (idx >= 0) {
                        const copy = prev.slice();
                        copy[idx] = { ...copy[idx], ...dev };
                        return copy;
                    }
                    return [...prev, dev];
                });
            } catch (e) { void e; }
        });

        es.addEventListener('progress', (evt) => {
            try {
                const p = JSON.parse(evt.data);
                if (typeof p.progress === 'number') setProgress(p.progress);
                if (p.status) setJobStatus(p.status);
            } catch (e) { void e; }
        });

        es.addEventListener('done', () => {
            try { es.close(); } catch (e) { void e; }
            esRef.current = null;
        });

        es.onerror = () => {
            try { es.close(); } catch (e) { void e; }
            esRef.current = null;
        };

        return () => {
            try { es.close(); } catch (e) { void e; }
            esRef.current = null;
        };
    }, [step, jobId]);

    // Auto-scroll logs
    useEffect(() => {
        logEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [logs]);

    useEffect(() => {
        if (step !== 1) return;
        if (scanMode !== 'seed') return;
        let cancelled = false;
        const run = async () => {
            try {
                setLoadingSeeds(true);
                const res = await DeviceService.getAll();
                if (cancelled) return;
                const devices = Array.isArray(res.data) ? res.data : [];
                setSeedDevices(devices);
                if (!seedDeviceId && devices.length > 0) {
                    setSeedDeviceId(String(devices[0].id));
                }
            } catch (e) {
                toast.error('Failed to load devices for seed crawl');
            } finally {
                if (!cancelled) setLoadingSeeds(false);
            }
        };
        run();
        return () => {
            cancelled = true;
        };
    }, [step, scanMode]);

    const buildSnmpPayload = () => {
        const base = { snmp_version: snmpVersion, snmp_port: Number(snmpPort) || 161 };
        if (String(snmpVersion).toLowerCase() !== 'v3') {
            return { ...base, community };
        }
        return {
            ...base,
            community,
            snmp_v3_username: snmpV3Username || null,
            snmp_v3_security_level: snmpV3SecurityLevel || null,
            snmp_v3_auth_proto: snmpV3AuthProto || null,
            snmp_v3_auth_key: snmpV3AuthKey || null,
            snmp_v3_priv_proto: snmpV3PrivProto || null,
            snmp_v3_priv_key: snmpV3PrivKey || null,
        };
    };

    const scopeForMode = () => {
        const discoveryInclude = parseCidrList(generalSettings.discovery_scope_include_cidrs);
        const discoveryExclude = parseCidrList(generalSettings.discovery_scope_exclude_cidrs);
        const preferPrivate = String(generalSettings.discovery_prefer_private ?? 'true').trim().toLowerCase();
        const preferPrivateBool = ['true', '1', 'yes', 'y', 'on'].includes(preferPrivate);

        if (scanMode !== 'seed') {
            return { includeCidrs: discoveryInclude, excludeCidrs: discoveryExclude, preferPrivate: preferPrivateBool, mode: 'discovery' };
        }

        const crawlIncludeRaw = String(generalSettings.neighbor_crawl_scope_include_cidrs || '').trim();
        const crawlExcludeRaw = String(generalSettings.neighbor_crawl_scope_exclude_cidrs || '').trim();
        const crawlPreferRaw = String(generalSettings.neighbor_crawl_prefer_private || '').trim();
        const crawlInclude = crawlIncludeRaw ? parseCidrList(crawlIncludeRaw) : discoveryInclude;
        const crawlExclude = crawlExcludeRaw ? parseCidrList(crawlExcludeRaw) : discoveryExclude;
        const crawlPrefer = crawlPreferRaw
            ? ['true', '1', 'yes', 'y', 'on'].includes(crawlPreferRaw.toLowerCase())
            : preferPrivateBool;
        return { includeCidrs: crawlInclude, excludeCidrs: crawlExclude, preferPrivate: crawlPrefer, mode: 'crawl' };
    };

    const selectedSeedDeviceIp = (() => {
        if (!seedDeviceId) return '';
        const idNum = Number(seedDeviceId);
        const d = seedDevices.find(x => Number(x.id) === idNum);
        return String(d?.ip_address || '').trim();
    })();

    const effectiveSeedIp = scanMode === 'seed' ? (String(seedIp || '').trim() || selectedSeedDeviceIp) : '';
    const currentScope = scopeForMode();
    const seedScopeCheck = scanMode === 'seed'
        ? checkScopeAllowed(effectiveSeedIp, currentScope.includeCidrs, currentScope.excludeCidrs)
        : { ok: true, reason: '' };

    const handleStartScan = async (e) => {
        e.preventDefault();
        try {
            if (scanMode === 'seed') {
                if (!effectiveSeedIp) {
                    toast.error('Seed IP 또는 Seed Device를 선택하세요.');
                    return;
                }
                if (!seedScopeCheck.ok) {
                    toast.error(`Seed 대상이 현재 Scope 밖입니다: ${seedScopeCheck.reason}`);
                    return;
                }
            }
            const snmp = buildSnmpPayload();
            const res = scanMode === 'seed'
                ? await DiscoveryService.startNeighborCrawl({
                    seed_device_id: seedIp ? null : Number(seedDeviceId),
                    seed_ip: seedIp ? String(seedIp).trim() : null,
                    max_depth: Number(maxDepth) || 2,
                    ...snmp
                })
                : await DiscoveryService.startScan({ cidr, ...snmp });
            setJobId(res.data.id);
            setResults([]);
            setExpanded({});
            setStep(2);
            setLogs("Initializing scan job...");
            setProgress(0);
        } catch (err) {
            toast.error("Failed to start scan: " + err.message);
        }
    };

    const loadResults = async () => {
        try {
            const res = await DiscoveryService.getJobResults(jobId);
            setResults(res.data);
            setExpanded({});
            setStep(3);
        } catch (err) {
            toast.error("Failed to load results");
        }
    };

    useEffect(() => {
        const incomingJobId = location.state?.jobId;
        if (!incomingJobId) return;

        const run = async () => {
            try {
                setJobId(incomingJobId);
                const res = await DiscoveryService.getJobResults(incomingJobId);
                setResults(res.data);
                setStep(3);
            } catch (e) {
                toast.error("Failed to load discovery results");
            }
        };
        run();
    }, [location.state]);

    const getIssues = (dev) => Array.isArray(dev?.issues) ? dev.issues : [];

    const getEvidence = (dev) => (dev && typeof dev.evidence === 'object' && dev.evidence !== null) ? dev.evidence : {};

    const toggleExpanded = (id) => {
        setExpanded(prev => ({ ...prev, [id]: !prev?.[id] }));
    };

    const getSeverityStyle = (sev) => {
        const s = String(sev || 'info').toLowerCase();
        if (s === 'error') return 'bg-red-100 text-red-700 border-red-200';
        if (s === 'warn' || s === 'warning') return 'bg-amber-100 text-amber-700 border-amber-200';
        return 'bg-gray-100 text-gray-700 border-gray-200';
    };

    const renderIssuesAndEvidence = (dev) => {
        const issues = getIssues(dev);
        const evidence = getEvidence(dev);
        const openPorts = Array.isArray(evidence?.open_ports) ? evidence.open_ports : [];
        const probe = (evidence && typeof evidence.snmp_probe === 'object' && evidence.snmp_probe !== null) ? evidence.snmp_probe : null;

        return (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                    <div className="font-bold mb-2">Issues</div>
                    {issues.length === 0 ? (
                        <div className="text-sm text-gray-500">No issues detected.</div>
                    ) : (
                        <div className="space-y-2">
                            {issues.map((it, idx) => (
                                <div key={`${it?.code || 'issue'}-${idx}`} className="flex items-start gap-2">
                                    <span className={`px-2 py-0.5 rounded-full text-xs font-bold border ${getSeverityStyle(it?.severity)}`}>
                                        {String(it?.severity || 'info').toUpperCase()}
                                    </span>
                                    <div className="text-sm">
                                        <div className="font-semibold text-gray-900 dark:text-white">{it?.message || it?.code || 'Issue'}</div>
                                        {it?.hint && <div className="text-gray-600 dark:text-gray-400 mt-0.5">{it.hint}</div>}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
                <div className="bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                    <div className="font-bold mb-2">Evidence</div>
                    <div className="text-sm space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-gray-500">Open ports:</span>
                            {openPorts.length > 0 ? (
                                openPorts.slice(0, 20).map((p) => (
                                    <span key={p} className="text-xs font-mono px-2 py-1 rounded bg-white dark:bg-black/30 border border-gray-200 dark:border-gray-700">
                                        {p}
                                    </span>
                                ))
                            ) : (
                                <span className="text-xs text-gray-400">-</span>
                            )}
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-gray-500">SNMP probe:</span>
                            {probe ? (
                                <>
                                    <span className={`text-xs font-mono px-2 py-1 rounded border ${probe.lldp ? 'bg-green-100 text-green-700 border-green-200' : 'bg-gray-100 text-gray-600 border-gray-200'}`}>LLDP {probe.lldp ? 'OK' : 'NO'}</span>
                                    <span className={`text-xs font-mono px-2 py-1 rounded border ${probe.bridge ? 'bg-green-100 text-green-700 border-green-200' : 'bg-gray-100 text-gray-600 border-gray-200'}`}>BRIDGE {probe.bridge ? 'OK' : 'NO'}</span>
                                    <span className={`text-xs font-mono px-2 py-1 rounded border ${probe.qbridge ? 'bg-green-100 text-green-700 border-green-200' : 'bg-gray-100 text-gray-600 border-gray-200'}`}>Q-BRIDGE {probe.qbridge ? 'OK' : 'NO'}</span>
                                </>
                            ) : (
                                <span className="text-xs text-gray-400">-</span>
                            )}
                        </div>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-gray-500">sysObjectID:</span>
                            <span className="text-xs font-mono px-2 py-1 rounded bg-white dark:bg-black/30 border border-gray-200 dark:border-gray-700">
                                {evidence?.snmp_sys_oid || dev?.sys_object_id || '-'}
                            </span>
                            <span className="text-gray-500">SNMP ver:</span>
                            <span className="text-xs font-mono px-2 py-1 rounded bg-white dark:bg-black/30 border border-gray-200 dark:border-gray-700">
                                {evidence?.snmp_version || (typeof evidence?.snmp_mp_model === 'number' ? (evidence.snmp_mp_model === 1 ? 'v2c' : 'v1') : '-') }
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    const needsLowConfidenceConfirm = (dev) => {
        const conf = typeof dev?.vendor_confidence === 'number' ? dev.vendor_confidence : null;
        const lowVendor = conf !== null ? conf < 0.5 : true;
        const snmpUnreachable = dev?.snmp_status !== 'reachable';
        return lowVendor || snmpUnreachable;
    };

    const handleApprove = async (id) => {
        const dev = results.find(r => r.id === id);
        if (dev && needsLowConfidenceConfirm(dev)) {
            const confPct = typeof dev.vendor_confidence === 'number' ? `${Math.round(dev.vendor_confidence * 100)}%` : 'unknown';
            const ok = window.confirm(
                `Low-confidence discovery result.\n\nIP: ${dev.ip_address}\nVendor: ${dev.vendor || 'Unknown'} (${confPct})\nSNMP: ${dev.snmp_status}\n\nAdd to inventory anyway?`
            );
            if (!ok) return;
        }
        try {
            await DiscoveryService.approveDevice(id);
            // Update UI
            setResults(prev => prev.map(dev =>
                dev.id === id ? { ...dev, status: 'approved' } : dev
            ));
        } catch (err) {
            toast.error("Failed to approve device");
        }
    };

    const handleIgnore = async (id) => {
        try {
            await DiscoveryService.ignoreDevice(id);
            setResults(prev => prev.map(dev =>
                dev.id === id ? { ...dev, status: 'ignored' } : dev
            ));
        } catch (err) {
            toast.error("Failed to ignore device");
        }
    };

    const handleApproveAll = async () => {
        const low = results.filter(d => d.status === 'new' && needsLowConfidenceConfirm(d));
        if (low.length > 0) {
            const ok = window.confirm(
                `Approve all new devices includes ${low.length} low-confidence result(s).\n\nProceed anyway?`
            );
            if (!ok) return;
        }
        try {
            await DiscoveryService.approveAll(jobId);
            await loadResults();
        } catch (err) {
            toast.error("Failed to approve all devices");
        }
    };


    return (
        <div className="p-3 sm:p-4 md:p-6 h-full bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white flex flex-col justify-center overflow-hidden">

            {/* Step 1: Input Analysis */}
            {step === 1 && (
                <div className="max-w-2xl mx-auto w-full bg-white dark:bg-[#1b1d1f] p-6 sm:p-8 rounded-2xl shadow-xl border border-gray-200 dark:border-gray-800 animate-scale-in">
                    <div className="flex justify-center mb-6">
                        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-full text-blue-500 animate-pulse">
                            <Radar size={48} />
                        </div>
                    </div>
                    <h2 className="text-2xl font-bold text-center text-gray-900 dark:text-white mb-2">Network Discovery</h2>
                    <div className="flex justify-center mb-4">
                        <div className="inline-flex p-1 rounded-xl bg-gray-100 dark:bg-black/30 border border-gray-200 dark:border-gray-800">
                            <button
                                type="button"
                                onClick={() => setScanMode('cidr')}
                                className={`px-4 py-2 rounded-lg text-sm font-bold transition-colors ${scanMode === 'cidr' ? 'bg-white dark:bg-[#1b1d1f] shadow text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`}
                            >
                                CIDR Scan
                            </button>
                            <button
                                type="button"
                                onClick={() => setScanMode('seed')}
                                className={`px-4 py-2 rounded-lg text-sm font-bold transition-colors ${scanMode === 'seed' ? 'bg-white dark:bg-[#1b1d1f] shadow text-gray-900 dark:text-white' : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'}`}
                            >
                                Seed Crawl
                            </button>
                        </div>
                    </div>
                    <p className="text-center text-gray-500 mb-8">
                        {scanMode === 'seed'
                            ? 'Start from a seed device and crawl neighbors recursively.'
                            : 'Scan a subnet to automatically find and identify devices.'}
                    </p>

                    <div className="mb-6 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-800 rounded-xl p-4">
                        <div className="flex items-center justify-between gap-3">
                            <div className="font-bold text-sm">Current Scope (Read Only)</div>
                            <div className="text-[11px] text-gray-500">
                                {currentScope.mode === 'crawl' ? 'Seed Crawl 적용' : 'CIDR Scan 적용'}
                            </div>
                        </div>
                        <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                            <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-lg p-3">
                                <div className="font-bold text-gray-700 dark:text-gray-200 mb-1">Include CIDRs</div>
                                <div className="text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                                    {currentScope.includeCidrs.length ? currentScope.includeCidrs.join(', ') : '(empty = allow all)'}
                                </div>
                            </div>
                            <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-lg p-3">
                                <div className="font-bold text-gray-700 dark:text-gray-200 mb-1">Exclude CIDRs</div>
                                <div className="text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                                    {currentScope.excludeCidrs.length ? currentScope.excludeCidrs.join(', ') : '(empty)'}
                                </div>
                            </div>
                            <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-lg p-3 sm:col-span-2">
                                <div className="font-bold text-gray-700 dark:text-gray-200 mb-1">Prefer Private</div>
                                <div className="text-gray-600 dark:text-gray-400">{currentScope.preferPrivate ? 'true' : 'false'}</div>
                            </div>
                        </div>
                    </div>

                    <form onSubmit={handleStartScan} className="space-y-4">
                        {scanMode === 'cidr' ? (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Target Network (CIDR)</label>
                                <input
                                    type="text"
                                    value={cidr}
                                    onChange={(e) => setCidr(e.target.value)}
                                    placeholder="e.g. 192.168.1.0/24"
                                    className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                    required
                                />
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Seed IP</label>
                                    <input
                                        type="text"
                                        value={seedIp}
                                        onChange={(e) => setSeedIp(e.target.value)}
                                        placeholder="e.g. 192.168.0.1"
                                        className={`w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all ${seedIp && !seedScopeCheck.ok ? 'border-red-400 dark:border-red-600' : 'border-gray-200 dark:border-gray-700'}`}
                                    />
                                    <div className="text-xs text-gray-500 mt-1">
                                        If set, Seed Device selection is optional.
                                    </div>
                                    {effectiveSeedIp && !seedScopeCheck.ok && (
                                        <div className="mt-2 text-xs font-bold text-red-600 dark:text-red-400 flex items-start gap-2">
                                            <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                                            <div>
                                                Scope 경고: {seedScopeCheck.reason}
                                                <div className="text-[11px] text-gray-600 dark:text-gray-500 font-medium mt-0.5">
                                                    Settings &gt; Auto Discovery Scope에서 Include/Exclude CIDR를 확인하세요.
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Seed Device</label>
                                    <select
                                        value={seedDeviceId}
                                        onChange={(e) => setSeedDeviceId(e.target.value)}
                                        className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                        disabled={loadingSeeds}
                                    >
                                        {seedDevices.length === 0 ? (
                                            <option value="">{loadingSeeds ? 'Loading...' : 'No devices found'}</option>
                                        ) : (
                                            seedDevices.map((d) => (
                                                <option key={d.id} value={String(d.id)}>
                                                    {d.name || d.hostname || `Device ${d.id}`} ({d.ip_address})
                                                </option>
                                            ))
                                        )}
                                    </select>
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Max Depth</label>
                                    <input
                                        type="number"
                                        min={1}
                                        max={6}
                                        value={maxDepth}
                                        onChange={(e) => setMaxDepth(Number(e.target.value))}
                                        className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                    />
                                </div>
                            </div>
                        )}

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SNMP Version</label>
                                <select
                                    value={snmpVersion}
                                    onChange={(e) => setSnmpVersion(e.target.value)}
                                    className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                >
                                    <option value="v2c">v2c</option>
                                    <option value="v3">v3</option>
                                    <option value="v1">v1</option>
                                </select>
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SNMP Port</label>
                                <input
                                    type="number"
                                    min={1}
                                    max={65535}
                                    value={snmpPort}
                                    onChange={(e) => setSnmpPort(Number(e.target.value))}
                                    className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                />
                            </div>
                        </div>

                        {String(snmpVersion).toLowerCase() !== 'v3' ? (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">SNMP Community</label>
                                <input
                                    type="password"
                                    value={community}
                                    onChange={(e) => setCommunity(e.target.value)}
                                    placeholder="public"
                                    className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                />
                            </div>
                        ) : (
                            <div className="space-y-4">
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">v3 Username</label>
                                        <input
                                            type="text"
                                            value={snmpV3Username}
                                            onChange={(e) => setSnmpV3Username(e.target.value)}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                            required
                                        />
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Security Level</label>
                                        <select
                                            value={snmpV3SecurityLevel}
                                            onChange={(e) => setSnmpV3SecurityLevel(e.target.value)}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all"
                                        >
                                            <option value="authPriv">authPriv</option>
                                            <option value="authNoPriv">authNoPriv</option>
                                            <option value="noAuthNoPriv">noAuthNoPriv</option>
                                        </select>
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Auth Protocol</label>
                                        <select
                                            value={snmpV3AuthProto}
                                            onChange={(e) => setSnmpV3AuthProto(e.target.value)}
                                            disabled={snmpV3SecurityLevel === 'noAuthNoPriv'}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all disabled:opacity-60"
                                        >
                                            <option value="sha">SHA</option>
                                            <option value="md5">MD5</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Auth Key</label>
                                        <input
                                            type="password"
                                            value={snmpV3AuthKey}
                                            onChange={(e) => setSnmpV3AuthKey(e.target.value)}
                                            disabled={snmpV3SecurityLevel === 'noAuthNoPriv'}
                                            required={snmpV3SecurityLevel === 'authNoPriv' || snmpV3SecurityLevel === 'authPriv'}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all disabled:opacity-60"
                                        />
                                    </div>
                                </div>

                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Priv Protocol</label>
                                        <select
                                            value={snmpV3PrivProto}
                                            onChange={(e) => setSnmpV3PrivProto(e.target.value)}
                                            disabled={snmpV3SecurityLevel !== 'authPriv'}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all disabled:opacity-60"
                                        >
                                            <option value="aes">AES</option>
                                            <option value="des">DES</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Priv Key</label>
                                        <input
                                            type="password"
                                            value={snmpV3PrivKey}
                                            onChange={(e) => setSnmpV3PrivKey(e.target.value)}
                                            disabled={snmpV3SecurityLevel !== 'authPriv'}
                                            required={snmpV3SecurityLevel === 'authPriv'}
                                            className="w-full px-4 py-2 bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-gray-700 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none transition-all disabled:opacity-60"
                                        />
                                    </div>
                                </div>
                            </div>
                        )}
                        <button
                            type="submit"
                            disabled={scanMode === 'seed' && (!effectiveSeedIp || !seedScopeCheck.ok)}
                            className={`w-full py-3 text-white font-bold rounded-lg shadow-lg shadow-blue-500/30 transition-all flex items-center justify-center gap-2 ${scanMode === 'seed' && (!effectiveSeedIp || !seedScopeCheck.ok) ? 'bg-gray-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-500'}`}
                        >
                            <Play size={20} /> {scanMode === 'seed' ? 'Start Crawl' : 'Start Scan'}
                        </button>
                    </form>
                </div>
            )}

            {/* Step 2: Scanning Progress */}
            {step === 2 && (
                <div className="max-w-3xl mx-auto w-full space-y-6 animate-fade-in">
                    <div className="bg-white dark:bg-[#1b1d1f] p-6 rounded-2xl border border-gray-200 dark:border-gray-800 shadow-lg">
                        <div className="flex items-center justify-between mb-4">
                            <h2 className="text-xl font-bold flex items-center gap-2">
                                <RefreshCw className="animate-spin text-blue-500" /> Scanning Network...
                            </h2>
                            <div className="flex items-center gap-2">
                                <span className="text-xs font-mono bg-gray-100 dark:bg-black/30 px-2 py-1 rounded">Found {results.length}</span>
                                <span className="text-sm font-mono bg-gray-100 dark:bg-black/30 px-2 py-1 rounded">{progress}%</span>
                            </div>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 mb-6 overflow-hidden">
                            <div className="bg-blue-600 h-2.5 rounded-full transition-all duration-500" style={{ width: `${progress}%` }}></div>
                        </div>

                        {/* Terminal Output */}
                        <div className="bg-black rounded-lg p-4 font-mono text-xs h-64 overflow-y-auto custom-scrollbar border border-gray-800 shadow-inner">
                            <pre className="text-green-400 whitespace-pre-wrap">{logs}</pre>
                            <div ref={logEndRef} />
                        </div>
                    </div>

                    {results.length > 0 && (
                        <div className="bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm">
                            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between">
                                <div className="font-bold">Live Results</div>
                                <div className="text-xs text-gray-500">Updates stream while scanning</div>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full text-left">
                                    <thead className="bg-gray-50 dark:bg-[#25282c] border-b border-gray-200 dark:border-gray-700 text-gray-500 font-medium">
                                        <tr>
                                            <th className="px-6 py-3">IP</th>
                                            <th className="px-6 py-3">Hostname</th>
                                            <th className="px-6 py-3">Vendor</th>
                                            <th className="px-6 py-3">Issues</th>
                                            <th className="px-6 py-3">SNMP</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                                        {results.slice(0, 20).flatMap(dev => {
                                            const isOpen = !!expanded?.[dev.id];
                                            return [
                                                (
                                                    <tr key={dev.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                                                        <td className="px-6 py-3 font-mono text-sm">{dev.ip_address}</td>
                                                        <td className="px-6 py-3 font-bold text-gray-900 dark:text-white">{dev.hostname || '-'}</td>
                                                        <td className="px-6 py-3">{dev.vendor || 'Unknown'}</td>
                                                        <td className="px-6 py-3">
                                                            {getIssues(dev).length > 0 || Object.keys(getEvidence(dev)).length > 0 ? (
                                                                <button
                                                                    onClick={() => toggleExpanded(dev.id)}
                                                                    className="text-xs font-bold text-amber-700 dark:text-amber-400 flex items-center gap-1"
                                                                    title="Show details"
                                                                >
                                                                    <AlertTriangle size={12} /> {getIssues(dev).length || 0}
                                                                </button>
                                                            ) : (
                                                                <span className="text-xs text-gray-400">-</span>
                                                            )}
                                                        </td>
                                                        <td className="px-6 py-3">
                                                            {dev.snmp_status === 'reachable' ? (
                                                                <span className="text-green-500 flex items-center gap-1 text-xs"><CheckCircle size={12} /> Reachable</span>
                                                            ) : (
                                                                <span className="text-red-500 flex items-center gap-1 text-xs"><AlertTriangle size={12} /> Unreachable</span>
                                                            )}
                                                        </td>
                                                    </tr>
                                                ),
                                                isOpen ? (
                                                    <tr key={`${dev.id}-details`} className="bg-gray-50/50 dark:bg-black/10">
                                                        <td colSpan={5} className="px-6 py-4">
                                                            {renderIssuesAndEvidence(dev)}
                                                        </td>
                                                    </tr>
                                                ) : null,
                                            ].filter(Boolean);
                                        })}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {jobStatus === 'completed' && (
                        <div className="flex justify-center">
                            <button onClick={loadResults} className="px-6 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg font-bold shadow-lg shadow-green-500/30 animate-bounce">
                                View Results
                            </button>
                        </div>
                    )}
                </div>
            )}

            {/* Step 3: Results Table */}
            {step === 3 && (
                <div className="space-y-6 animate-fade-in h-full flex flex-col">
                    <div className="flex justify-between items-center mb-2">
                        <h2 className="text-2xl font-bold flex items-center gap-2">
                            <CheckCircle className="text-green-500" /> Scan Results
                        </h2>
                        <div className="flex gap-2">
                            <button onClick={() => setStep(1)} className="px-4 py-2 border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">New Scan</button>
                            <button onClick={handleApproveAll} className="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg">Approve All New</button>
                            <button onClick={() => navigate('/devices')} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg">Go to Inventory</button>
                        </div>
                    </div>

                    <div className="flex-1 bg-white dark:bg-[#1b1d1f] rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm flex flex-col">
                        <div className="overflow-y-auto flex-1 custom-scrollbar">
                            <table className="w-full text-left">
                                <thead className="bg-gray-50 dark:bg-[#25282c] border-b border-gray-200 dark:border-gray-700 text-gray-500 font-medium">
                                    <tr>
                                        <th className="px-6 py-4">Status</th>
                                        <th className="px-6 py-4">IP Address</th>
                                        <th className="px-6 py-4">Hostname</th>
                                        <th className="px-6 py-4">Vendor</th>
                                        <th className="px-6 py-4">Confidence</th>
                                        <th className="px-6 py-4">Chassis</th>
                                        <th className="px-6 py-4">Model</th>
                                        <th className="px-6 py-4">Type</th>
                                        <th className="px-6 py-4">Issues</th>
                                        <th className="px-6 py-4">SNMP</th>
                                        <th className="px-6 py-4 text-right">Action</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                                    {results.length === 0 ? (
                                        <tr><td colSpan="11" className="px-6 py-10 text-center text-gray-500">No devices found. Try checking your network connectivity.</td></tr>
                                    ) : results.flatMap(dev => {
                                        const isOpen = !!expanded?.[dev.id];
                                        return [
                                            (
                                                <tr key={dev.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">
                                                    <td className="px-6 py-4">
                                                        {dev.status === 'existing' ? (
                                                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-yellow-100 text-yellow-700 border border-yellow-200">Managed</span>
                                                        ) : dev.status === 'approved' ? (
                                                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-green-100 text-green-700 border border-green-200">Approved</span>
                                                        ) : (
                                                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-700 border border-blue-200">New Found</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4 font-mono text-sm">{dev.ip_address}</td>
                                                    <td className="px-6 py-4 font-bold text-gray-900 dark:text-white">{dev.hostname || '-'}</td>
                                                    <td className="px-6 py-4">{dev.vendor || 'Unknown'}</td>
                                                    <td className="px-6 py-4">
                                                        {typeof dev.vendor_confidence === 'number' ? (
                                                            <span className="text-xs font-mono px-2 py-1 rounded bg-gray-100 dark:bg-black/30 border border-gray-200 dark:border-gray-700">
                                                                {Math.round(dev.vendor_confidence * 100)}%
                                                            </span>
                                                        ) : (
                                                            <span className="text-xs text-gray-400">-</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        {dev.chassis_candidate ? (
                                                            <span className="px-2 py-1 rounded-full text-xs font-bold bg-purple-100 text-purple-700 border border-purple-200">Likely</span>
                                                        ) : (
                                                            <span className="text-xs text-gray-400">-</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4 font-mono text-xs">{dev.model || '-'}</td>
                                                    <td className="px-6 py-4 font-mono text-xs">{dev.device_type || '-'}</td>
                                                    <td className="px-6 py-4">
                                                        {getIssues(dev).length > 0 || Object.keys(getEvidence(dev)).length > 0 ? (
                                                            <button
                                                                onClick={() => toggleExpanded(dev.id)}
                                                                className="text-xs font-bold text-amber-700 dark:text-amber-400 flex items-center gap-1"
                                                                title="Show details"
                                                            >
                                                                <AlertTriangle size={12} /> {getIssues(dev).length || 0}
                                                            </button>
                                                        ) : (
                                                            <span className="text-xs text-gray-400">-</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4">
                                                        {dev.snmp_status === 'reachable' ? (
                                                            <span className="text-green-500 flex items-center gap-1 text-xs"><CheckCircle size={12} /> Reachable</span>
                                                        ) : (
                                                            <span className="text-red-500 flex items-center gap-1 text-xs"><AlertTriangle size={12} /> Unreachable</span>
                                                        )}
                                                    </td>
                                                    <td className="px-6 py-4 text-right">
                                                        {dev.status === 'new' && (
                                                            <div className="flex items-center justify-end gap-2">
                                                                <button
                                                                    onClick={() => handleIgnore(dev.id)}
                                                                    className="px-3 py-1.5 border border-gray-200 dark:border-gray-700 rounded-lg text-xs font-bold hover:bg-gray-100 dark:hover:bg-gray-800"
                                                                >
                                                                    Ignore
                                                                </button>
                                                                <button
                                                                    onClick={() => handleApprove(dev.id)}
                                                                    className={`px-3 py-1.5 text-white rounded-lg text-xs font-bold shadow-md flex items-center gap-1 ${needsLowConfidenceConfirm(dev) ? 'bg-amber-600 hover:bg-amber-500 shadow-amber-500/20' : 'bg-blue-600 hover:bg-blue-500 shadow-blue-500/20'}`}
                                                                >
                                                                    <Plus size={14} /> Add to Inventory
                                                                </button>
                                                                {needsLowConfidenceConfirm(dev) && (
                                                                    <span className="text-xs text-amber-600 dark:text-amber-400 flex items-center gap-1">
                                                                        <AlertTriangle size={12} /> Low confidence
                                                                    </span>
                                                                )}
                                                            </div>
                                                        )}
                                                        {dev.status === 'existing' && (
                                                            <button disabled className="px-3 py-1.5 text-gray-400 bg-gray-100 dark:bg-gray-800 rounded-lg text-xs cursor-not-allowed ml-auto">
                                                                Already Added
                                                            </button>
                                                        )}
                                                        {dev.status === 'approved' && (
                                                            <button disabled className="px-3 py-1.5 text-green-500 bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-900 rounded-lg text-xs cursor-not-allowed ml-auto flex items-center gap-1">
                                                                <CheckCircle size={14} /> Added
                                                            </button>
                                                        )}
                                                        {dev.status === 'ignored' && (
                                                            <button disabled className="px-3 py-1.5 text-gray-500 bg-gray-50 dark:bg-gray-900/10 border border-gray-200 dark:border-gray-800 rounded-lg text-xs cursor-not-allowed ml-auto">
                                                                Ignored
                                                            </button>
                                                        )}
                                                    </td>
                                                </tr>
                                            ),
                                            isOpen ? (
                                                <tr key={`${dev.id}-details`} className="bg-gray-50/50 dark:bg-black/10">
                                                    <td colSpan={11} className="px-6 py-4">
                                                        {renderIssuesAndEvidence(dev)}
                                                    </td>
                                                </tr>
                                            ) : null,
                                        ].filter(Boolean);
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
};

export default DiscoveryPage;


