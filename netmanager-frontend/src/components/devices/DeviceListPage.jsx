import React, { useState, useEffect } from 'react';
import { DeviceService } from '../../api/services';
import { useAuth } from '../../context/AuthContext'; // [RBAC]
import { useToast } from '../../context/ToastContext';
import {
    Search, RefreshCw, Plus, Trash2, Edit2, MapPin, Filter,
    Server, Shield, Wifi, Router, Box, Cloud
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import DeviceAddModal from './DeviceAddModal';

const DeviceListPage = () => {
    const navigate = useNavigate();
    const { isOperator, isAdmin } = useAuth(); // [RBAC] 3-Tier
    const { toast } = useToast();

    const [devices, setDevices] = useState([]);
    const [sites, setSites] = useState([]);
    const [selectedSiteId, setSelectedSiteId] = useState('all');
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');

    // Modal State
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [selectedDevice, setSelectedDevice] = useState(null);

    const loadData = async () => {
        setLoading(true);
        try {
            const [devRes, siteRes] = await Promise.all([
                DeviceService.getAll(),
                DeviceService.getSites()
            ]);
            setDevices(devRes.data);
            setSites(siteRes.data);
        } catch (error) {
            console.error("Failed to fetch data:", error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        loadData();
    }, []);

    const handleDelete = async (e, id) => {
        e.stopPropagation();
        if (!window.confirm("Are you sure you want to delete this device? This action cannot be undone.")) return;
        try {
            await DeviceService.delete(id);
            setDevices(prev => prev.filter(d => d.id !== id));
        } catch (error) {
            console.error(error);
            toast.error("Failed to delete device.");
        }
    };

    const handleEdit = (e, device) => {
        e.stopPropagation();
        setSelectedDevice(device);
        setIsModalOpen(true);
    };

    const handleAdd = () => {
        setSelectedDevice(null);
        setIsModalOpen(true);
    };

    const getDeviceIcon = (type) => {
        switch (type) {
            case 'core': return <Box size={18} className="text-purple-500" />;
            case 'dist': return <Router size={18} className="text-blue-500" />;
            case 'access': return <Server size={18} className="text-green-500" />;
            case 'router': return <Cloud size={18} className="text-orange-500" />;
            case 'ap': return <Wifi size={18} className="text-cyan-500" />;
            default: return <Shield size={18} className="text-gray-500" />;
        }
    };

    const filteredDevices = devices.filter(device => {
        const matchesSearch = device.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
            device.ip_address.includes(searchTerm);
        const matchesSite = selectedSiteId === 'all' || device.site_id === parseInt(selectedSiteId);
        return matchesSearch && matchesSite;
    });

    return (
        <div className="p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012] h-full flex flex-col animate-fade-in relative text-gray-900 dark:text-white transition-colors">

            {/* Header */}
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Device Inventory</h1>
                    <p className="text-sm text-gray-600 dark:text-gray-500">Manage infrastructure nodes and connections.</p>
                </div>
                <div className="flex gap-2">
                    <button onClick={loadData} className="p-2 bg-white dark:bg-[#1e293b] border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors text-gray-700 dark:text-gray-300">
                        <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                    </button>

                    {/* [RBAC] Add Device Button - Network Admin and above only */}
                    {isOperator() && (
                        <button onClick={handleAdd} className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold shadow-lg shadow-blue-500/20 transition-colors">
                            <Plus size={18} /> Add Device
                        </button>
                    )}
                </div>
            </div>

            {/* Search and Filter */}
            <div className="flex gap-4 mb-4">
                <div className="flex-1 bg-white dark:bg-[#1b1d1f] p-4 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm relative">
                    <Search className="absolute left-7 top-6.5 text-gray-500 dark:text-gray-400" size={18} />
                    <input
                        type="text"
                        placeholder="Search by Hostname or IP..."
                        className="w-full pl-10 pr-4 py-2 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500 transition-all"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>

                <div className="bg-white dark:bg-[#1b1d1f] px-4 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm flex items-center min-w-[200px]">
                    <Filter size={18} className="text-gray-500 dark:text-gray-400 mr-2" />
                    <select
                        className="w-full bg-transparent text-sm text-gray-900 dark:text-white outline-none cursor-pointer"
                        value={selectedSiteId}
                        onChange={(e) => setSelectedSiteId(e.target.value)}
                    >
                        <option value="all">All Sites (Global)</option>
                        {sites.map(site => (
                            <option key={site.id} value={site.id}>{site.name}</option>
                        ))}
                    </select>
                </div>
            </div>

            {/* Device Table */}
            <div className="flex-1 bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm overflow-hidden flex flex-col mb-10">
                <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="bg-gray-50 dark:bg-[#25282c] border-b border-gray-200 dark:border-gray-800">
                                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">Device</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">Type</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">Site</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">IP Address</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase">Status</th>
                                <th className="px-6 py-3 text-xs font-semibold text-gray-600 dark:text-gray-500 uppercase text-right">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                            {filteredDevices.map((device) => (
                                <tr
                                    key={device.id}
                                    onClick={() => navigate(`/devices/${device.id}`)}
                                    className="group hover:bg-gray-50 dark:hover:bg-[#25282c] cursor-pointer transition-colors"
                                >
                                    <td className="px-6 py-4 flex items-center gap-3">
                                        {getDeviceIcon(device.device_type)}
                                        <div>
                                            <div className="text-sm font-bold text-gray-900 dark:text-white">{device.name}</div>
                                            <div className="text-xs text-gray-600 dark:text-gray-500">{device.model || 'Unknown Model'}</div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 text-xs font-medium text-gray-600 dark:text-gray-500 uppercase">{device.device_type}</td>
                                    <td className="px-6 py-4">
                                        {device.site_id ? (
                                            <span className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-500 bg-blue-50 dark:bg-blue-900/20 px-2 py-1 rounded w-fit">
                                                <MapPin size={10} />
                                                {sites.find(s => s.id === device.site_id)?.name || 'Unknown Site'}
                                            </span>
                                        ) : (
                                            <span className="text-xs text-gray-500 dark:text-gray-400">-</span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-300 font-mono">{device.ip_address}</td>
                                    <td className="px-6 py-4">
                                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${device.status === 'online' ? 'text-green-600 bg-green-50 dark:bg-green-900/20' : 'text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800'}`}>
                                            {device.status?.toUpperCase() || 'UNKNOWN'}
                                        </span>
                                    </td>
                                    <td className="px-6 py-4 text-right flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                                        {/* [RBAC] Edit Button - Network Admin and above only */}
                                        {isOperator() && (
                                            <button onClick={(e) => handleEdit(e, device)} className="p-2 text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400 transition-colors"><Edit2 size={16} /></button>
                                        )}
                                        {/* [RBAC] Delete Button - Admin only */}
                                        {isAdmin() && (
                                            <button onClick={(e) => handleDelete(e, device.id)} className="p-2 text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 transition-colors"><Trash2 size={16} /></button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                            {filteredDevices.length === 0 && (
                                <tr>
                                    <td colSpan="6" className="px-6 py-10 text-center text-gray-600 dark:text-gray-500">No devices found.</td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            <DeviceAddModal
                isOpen={isModalOpen}
                onClose={() => setIsModalOpen(false)}
                onDeviceAdded={loadData}
                deviceToEdit={selectedDevice}
            />
        </div>
    );
};

export default DeviceListPage;
