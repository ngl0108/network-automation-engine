import React, { useState, useEffect } from 'react';
import { DeviceService } from '../api/services'; // [수정됨] 경로 1단계 위로 변경
import {
  MapPin, Plus, Edit2, Trash2, Building, RefreshCw, Globe
} from 'lucide-react';
import SiteAddModal from './SiteAddModal';
import { useAuth } from '../context/AuthContext'; // [RBAC]
import { useToast } from '../context/ToastContext';

const SiteListPage = () => {
  const { isOperator, isAdmin } = useAuth(); // [RBAC]
  const { toast } = useToast();
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);

  // 모달 상태
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedSite, setSelectedSite] = useState(null);

  const loadSites = async () => {
    setLoading(true);
    try {
      const res = await DeviceService.getSites();
      setSites(res.data);
    } catch (err) {
      console.error("Failed to load sites", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSites();
  }, []);

  const handleDelete = async (id) => {
    if (!window.confirm("Delete this site? Devices linked to this site must be unlinked first.")) return;
    try {
      await DeviceService.deleteSite(id);
      setSites(prev => prev.filter(s => s.id !== id));
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to delete site");
    }
  };

  const handleAdd = () => {
    setSelectedSite(null);
    setIsModalOpen(true);
  };

  const handleEdit = (site) => {
    setSelectedSite(site);
    setIsModalOpen(true);
  };

  return (
    <div className="p-3 sm:p-4 md:p-6 bg-[#f4f5f9] dark:bg-[#0e1012] h-full flex flex-col animate-fade-in">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Globe className="text-blue-500" /> Site Management
          </h1>
          <p className="text-sm text-gray-500">Define physical locations (Buildings, Data Centers).</p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadSites} className="p-2 bg-white dark:bg-[#1e293b] border border-gray-200 dark:border-gray-700 rounded-lg text-gray-700 dark:text-gray-300">
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          </button>
          {isOperator() && (
            <button onClick={handleAdd} className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold shadow-lg shadow-blue-500/20">
              <Plus size={18} /> Add Site
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {sites.map(site => (
          <div key={site.id} className="bg-white dark:bg-[#1b1d1f] p-5 rounded-xl border border-gray-200 dark:border-gray-800 shadow-sm hover:shadow-md transition-all group">
            <div className="flex justify-between items-start">
              <div className="flex items-center gap-3">
                <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-blue-500">
                  <Building size={24} />
                </div>
                <div>
                  <h3 className="font-bold text-gray-900 dark:text-white text-lg">{site.name}</h3>
                  <span className="text-xs font-mono px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 text-gray-500">
                    {site.type}
                  </span>
                </div>
              </div>
              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                {isOperator() && (
                  <button onClick={() => handleEdit(site)} className="p-2 text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded">
                    <Edit2 size={16} />
                  </button>
                )}
                {isAdmin() && (
                  <button onClick={() => handleDelete(site.id)} className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded">
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            </div>

            <div className="mt-4 space-y-2">
              <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                <MapPin size={14} />
                {site.address || "No Address Defined"}
              </div>
              {(site.latitude && site.longitude) && (
                <div className="text-xs text-gray-400 font-mono ml-6">
                  Lat: {site.latitude}, Lon: {site.longitude}
                </div>
              )}
            </div>
          </div>
        ))}
        {sites.length === 0 && !loading && (
          <div className="col-span-full py-20 text-center text-gray-500">
            No sites configured. Click "Add Site" to get started.
          </div>
        )}
      </div>

      <SiteAddModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSiteAdded={loadSites}
        siteToEdit={selectedSite}
      />
    </div>
  );
};

export default SiteListPage;
