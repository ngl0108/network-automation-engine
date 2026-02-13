import React, { useState, useEffect } from 'react';
import { DeviceService } from '../api/services';
import {
    Wifi, Users, Radio, Server, Search, RefreshCw,
    ChevronRight, ShieldCheck, Activity, Globe
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const WirelessPage = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const navigate = useNavigate();

    const loadData = async (silent = false) => {
        if (!silent) setLoading(true);
        try {
            const res = await DeviceService.getWirelessOverview();
            setData(res.data);
        } catch (err) {
            console.error("Failed to load wireless data", err);
        } finally {
            if (!silent) setLoading(false);
        }
    };

    useEffect(() => {
        loadData();

        // 5초마다 자동 갱신
        const timer = setInterval(() => {
            loadData(true);
        }, 5000);

        return () => clearInterval(timer);
    }, []);

    if (loading) return <div className="h-full flex items-center justify-center text-gray-400 bg-[#0e1012] animate-pulse">Gathering global wireless telemetry...</div>;
    if (!data) return <div className="p-10 text-center text-red-500 bg-[#0e1012] h-full">Wireless services temporarily unavailable.</div>;

    const filteredAps = data.aps.filter(ap =>
        (ap.name || '').toLowerCase().includes(search.toLowerCase()) ||
        (ap.wlc_name || '').toLowerCase().includes(search.toLowerCase()) ||
        (ap.ip_address || '').includes(search)
    );

    return (
        <div className="p-3 sm:p-4 md:p-6 bg-[#0b0c0e] h-full flex flex-col gap-6 overflow-y-auto animate-fade-in text-white">

            {/* 1. Page Header */}
            <div className="flex justify-between items-end border-b border-gray-800 pb-4">
                <div>
                    <h1 className="text-2xl font-black flex items-center gap-3">
                        <Radio className="text-pink-500" size={28} /> Global Wireless Mobility
                    </h1>
                    <p className="text-xs text-gray-500 mt-1 uppercase tracking-widest font-bold">Comprehensive Control for Mixed Wireless Infrastructure</p>
                </div>
                <button
                    onClick={loadData}
                    className="p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors border border-gray-700 shadow-lg"
                >
                    <RefreshCw size={18} />
                </button>
            </div>

            {/* 2. Global KPIs */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <StatCard icon={<Server className="text-blue-500" />} title="Control Planes" value={data.summary.total_wlc} sub="Active WLCs" />
                <StatCard icon={<Wifi className="text-emerald-500" />} title="Total Access Points" value={data.summary.total_aps} sub="Physical Radios" />
                <StatCard icon={<Globe className="text-indigo-500" />} title="Broadcast SSIDs" value={data.summary.total_wlans} sub="Logical Services" />
                <StatCard icon={<Users className="text-pink-500" />} title="Mobile Clients" value={data.summary.total_clients} sub="Active Sessions" />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* 3. WLAN / SSID Global Status */}
                <div className="lg:col-span-1 bg-[#15171a] border border-gray-800 rounded-2xl overflow-hidden shadow-xl flex flex-col">
                    <div className="p-4 border-b border-gray-800 bg-gray-900/30 flex justify-between items-center">
                        <h3 className="text-sm font-bold text-gray-300 uppercase flex items-center gap-2">
                            <ShieldCheck size={16} className="text-indigo-500" /> Service Directory
                        </h3>
                        <span className="text-[10px] bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded-full font-bold">GLOBAL</span>
                    </div>
                    <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
                        {data.wlans.map((wl, idx) => (
                            <div key={idx} className="p-3 bg-gray-800/40 rounded-xl border border-gray-700/50 hover:border-indigo-500/50 transition-all group">
                                <div className="flex justify-between items-start mb-1">
                                    <span className="text-sm font-bold text-white group-hover:text-indigo-400 transition-colors uppercase">{wl.ssid}</span>
                                    <span className={`text-[9px] font-black px-1.5 py-0.5 rounded ${wl.status === 'UP' ? 'bg-emerald-500 text-white' : 'bg-red-500 text-white'}`}>
                                        {wl.status}
                                    </span>
                                </div>
                                <div className="flex justify-between text-[10px] text-gray-500 font-medium">
                                    <span>ID: {wl.id} • {wl.profile}</span>
                                    <span className="italic">via {wl.wlc_name}</span>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* 4. Global AP Inventory Table */}
                <div className="lg:col-span-2 bg-[#15171a] border border-gray-800 rounded-2xl overflow-hidden shadow-xl flex flex-col">
                    <div className="p-4 border-b border-gray-800 bg-gray-900/30 flex flex-wrap justify-between items-center gap-4">
                        <h3 className="text-sm font-bold text-gray-300 uppercase flex items-center gap-2">
                            <Wifi size={16} className="text-emerald-500" /> AP Radio Inventory
                        </h3>
                        <div className="relative w-full sm:w-64">
                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={14} />
                            <input
                                type="text"
                                placeholder="Search AP Name, IP or Controller..."
                                className="bg-[#0b0c0e] border border-gray-700 rounded-lg pl-9 pr-4 py-1.5 text-xs focus:ring-2 focus:ring-emerald-500 outline-none w-full transition-all"
                                value={search}
                                onChange={(e) => setSearch(e.target.value)}
                            />
                        </div>
                    </div>
                    <div className="flex-1 overflow-x-auto custom-scrollbar">
                        <table className="w-full text-left border-collapse text-xs">
                            <thead className="bg-[#0b0c0e] sticky top-0 z-10 border-b border-gray-800">
                                <tr>
                                    <th className="p-4 font-bold text-gray-500 uppercase tracking-tighter">AP Information</th>
                                    <th className="p-4 font-bold text-gray-500 uppercase tracking-tighter text-center">Status</th>
                                    <th className="p-4 font-bold text-gray-500 uppercase tracking-tighter">Controller</th>
                                    <th className="p-4 font-bold text-gray-500 uppercase tracking-tighter">Management IP</th>
                                    <th className="p-4 font-bold text-gray-500 uppercase tracking-tighter"></th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-800/50">
                                {filteredAps.map((ap, idx) => (
                                    <tr key={idx} className="hover:bg-gray-800/30 transition-colors group">
                                        <td className="p-4">
                                            <div className="flex flex-col">
                                                <span className="font-bold text-gray-200 uppercase">{ap.name || 'Unknown AP'}</span>
                                                <span className="text-[10px] text-gray-500">{ap.model || 'N/A'} • {ap.serial_number || 'N/A'}</span>
                                            </div>
                                        </td>
                                        <td className="p-4 text-center">
                                            <div className="flex justify-center">
                                                <StatusBadge status={ap.status} />
                                            </div>
                                        </td>
                                        <td className="p-4">
                                            <span className="bg-blue-500/10 text-blue-400 px-2 py-1 rounded font-bold">{ap.wlc_name}</span>
                                        </td>
                                        <td className="p-4 font-mono text-gray-400">
                                            {ap.ip_address}
                                        </td>
                                        <td className="p-4 text-right">
                                            <button
                                                onClick={() => navigate(`/devices/${ap.wlc_ip}`)} // This is a bit complex as we need DB ID, skip for now or use IP search
                                                className="p-1.5 hover:bg-gray-700 rounded-lg text-gray-500 hover:text-white transition-all transform hover:scale-110"
                                            >
                                                <ChevronRight size={18} />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    );
};

const StatCard = ({ icon, title, value, sub }) => (
    <div className="bg-[#15171a] border border-gray-800 p-5 rounded-2xl shadow-lg flex items-center gap-5">
        <div className="p-4 bg-gray-900/50 rounded-xl border border-gray-700/50">{icon}</div>
        <div>
            <p className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{title}</p>
            <h3 className="text-2xl font-black text-white">{value}</h3>
            <p className="text-[10px] text-gray-500 italic mt-0.5">{sub}</p>
        </div>
    </div>
);

const StatusBadge = ({ status }) => {
    const s = String(status).toLowerCase();
    const isUp = s.includes('up') || s.includes('reg') || s.includes('online');
    return (
        <span className={`px-2 py-1 rounded text-[9px] font-black uppercase tracking-tighter ${isUp ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20' : 'bg-red-500/10 text-red-500 border border-red-500/20'
            }`}>
            {status || 'Unknown'}
        </span>
    );
};

export default WirelessPage;
