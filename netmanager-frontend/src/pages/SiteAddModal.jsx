import React, { useState, useEffect } from 'react';
import { X, Building } from 'lucide-react';
import { DeviceService } from '../api/services';
import { useToast } from '../context/ToastContext';

const SiteAddModal = ({ isOpen, onClose, onSiteAdded, siteToEdit }) => {
  const { toast } = useToast();
  const initialFormState = {
    name: '',
    type: 'Building',
    address: '',
    latitude: '',
    longitude: ''
  };

  const [formData, setFormData] = useState(initialFormState);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (isOpen) {
      if (siteToEdit) {
        setFormData({ ...siteToEdit });
      } else {
        setFormData(initialFormState);
      }
    }
  }, [isOpen, siteToEdit]);

  if (!isOpen) return null;

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      // [수정 포인트] 빈 문자열("")을 null로 변환하여 전송
      const payload = {
        ...formData,
        latitude: formData.latitude ? parseFloat(formData.latitude) : null,
        longitude: formData.longitude ? parseFloat(formData.longitude) : null,
      };

      if (siteToEdit) {
        await DeviceService.updateSite(siteToEdit.id, payload);
      } else {
        await DeviceService.createSite(payload);
      }

      onSiteAdded();
      onClose();
    } catch (err) {
      console.error(err);
      // 에러 메시지를 좀 더 정확하게 표시
      const msg = err.response?.data?.detail || "Failed to save site. Name might be duplicated or invalid data.";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const inputClass = "w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white outline-none focus:ring-2 focus:ring-blue-500";
  const labelClass = "text-xs font-bold text-gray-700 dark:text-gray-400 uppercase mb-1 block";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
      <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-md rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 flex flex-col">

        <div className="flex justify-between items-center p-6 border-b border-gray-100 dark:border-gray-800">
          <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
            <Building className="text-blue-500"/> {siteToEdit ? 'Edit Site' : 'Add Site'}
          </h2>
          <button onClick={onClose}><X className="text-gray-500" /></button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          <div>
            <label className={labelClass}>Site Name *</label>
            <input required name="name" value={formData.name} onChange={handleChange} className={inputClass} placeholder="e.g. HQ Building A" />
          </div>

          <div>
            <label className={labelClass}>Type</label>
            <select name="type" value={formData.type} onChange={handleChange} className={inputClass}>
              <option value="Building">Building</option>
              <option value="DataCenter">Data Center</option>
              <option value="Branch">Branch Office</option>
              <option value="Cloud">Cloud Region</option>
            </select>
          </div>

          <div>
            <label className={labelClass}>Address</label>
            <input name="address" value={formData.address} onChange={handleChange} className={inputClass} placeholder="Seoul, Gangnam-gu..." />
          </div>

          <div className="grid grid-cols-2 gap-4">
             <div>
                <label className={labelClass}>Latitude</label>
                <input type="number" step="any" name="latitude" value={formData.latitude || ''} onChange={handleChange} className={inputClass} placeholder="37.5665" />
             </div>
             <div>
                <label className={labelClass}>Longitude</label>
                <input type="number" step="any" name="longitude" value={formData.longitude || ''} onChange={handleChange} className={inputClass} placeholder="126.9780" />
             </div>
          </div>

          <button type="submit" disabled={loading} className="w-full py-3 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg mt-4">
            {loading ? "Saving..." : "Save Site"}
          </button>
        </form>
      </div>
    </div>
  );
};

export default SiteAddModal;
