import React, { useState, useEffect } from 'react';
import { X, Save, Server, Shield, Globe, Terminal, MapPin } from 'lucide-react';
import { DeviceService } from '../../api/services';
import { useToast } from '../../context/ToastContext';

const DeviceAddModal = ({ isOpen, onClose, onDeviceAdded, deviceToEdit }) => {
  const { toast } = useToast();
  // 기본 폼 상태
  const initialFormState = {
    name: '',
    ip_address: '',
    device_type: 'cisco_ios',
    site_id: '', // [추가] 사이트 ID 초기값 (빈 문자열)
    snmp_community: 'public',
    ssh_username: '',
    ssh_password: '',
    ssh_port: 22,
    enable_password: '',
    polling_interval: 60,
    status_interval: 300,
    auto_provision_template_id: '' // [추가] 자동 배포 템플릿
  };

  const [formData, setFormData] = useState(initialFormState);
  const [sites, setSites] = useState([]);
  const [templates, setTemplates] = useState([]); // [추가] 템플릿 목록
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // [추가] 사이트 목록 불러오기
  const fetchSites = async () => {
    try {
      const res = await DeviceService.getSites(); // API 호출
      setSites(res.data);
    } catch (err) {
      console.error("Failed to fetch sites:", err);
    }
  };

  // [추가] 템플릿 목록 불러오기
  const fetchTemplates = async () => {
    try {
      const res = await DeviceService.getTemplates();
      setTemplates(res.data);
    } catch (err) {
      console.error("Failed to fetch templates:", err);
    }
  };

  // 모달이 열릴 때 or 수정할 장비가 바뀔 때 폼 초기화
  useEffect(() => {
    if (isOpen) {
      setError(null);
      fetchSites();
      fetchTemplates(); // [추가] 템플릿 로드

      if (deviceToEdit) {
        // 수정 모드: 기존 데이터 채우기
        setFormData({
          ...initialFormState,
          ...deviceToEdit,
          site_id: deviceToEdit.site_id || '', // 기존 site_id 매핑
          ssh_password: '', // 보안상 비밀번호는 비워둠 (입력 시에만 변경)
          enable_password: ''
        });
      } else {
        // 추가 모드: 초기화
        setFormData(initialFormState);
      }
    }
  }, [isOpen, deviceToEdit]);

  if (!isOpen) return null;

  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      // 숫자형 데이터 변환 및 site_id 처리
      const payload = {
        ...formData,
        ssh_port: parseInt(formData.ssh_port) || 22,
        polling_interval: parseInt(formData.polling_interval) || 60,
        status_interval: parseInt(formData.status_interval) || 300,
        // 빈 문자열이면 null로, 값이 있으면 숫자로 변환
        site_id: formData.site_id ? parseInt(formData.site_id) : null,
        auto_provision_template_id: formData.auto_provision_template_id ? parseInt(formData.auto_provision_template_id) : null
      };

      // 비밀번호 필드가 비어있으면 전송하지 않음 (수정 시 기존 비번 유지)
      if (deviceToEdit) {
        if (!payload.ssh_password) delete payload.ssh_password;
        if (!payload.enable_password) delete payload.enable_password;

        // [수정 요청] PUT
        await DeviceService.update(deviceToEdit.id, payload);
        toast.success("장비 정보가 수정되었습니다.");
      } else {
        // [생성 요청] POST
        await DeviceService.create(payload);
        toast.success("새 장비가 등록되었습니다.");
      }

      onDeviceAdded(); // 목록 새로고침 트리거
      onClose();       // 모달 닫기
    } catch (err) {
      console.error(err);
      setError(err.response?.data?.detail || "작업 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  // 공통 라벨 스타일
  const labelStyle = "text-xs font-bold text-gray-700 dark:text-gray-400 uppercase";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
      <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-2xl rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-800 overflow-hidden flex flex-col max-h-[90vh]">

        {/* 헤더 */}
        <div className="flex justify-between items-center p-6 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-[#202327]">
          <div>
            <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
              {deviceToEdit ? <Save className="text-blue-500" size={24} /> : <Server className="text-green-500" size={24} />}
              {deviceToEdit ? 'Edit Device' : 'Add New Device'}
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              {deviceToEdit ? 'Update connection details.' : 'Register a new network node to inventory.'}
            </p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors">
            <X size={20} className="text-gray-500 dark:text-gray-400" />
          </button>
        </div>

        {/* 폼 바디 (스크롤 가능) */}
        <div className="p-6 overflow-y-auto custom-scrollbar">
          {error && (
            <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg border border-red-200 dark:border-red-800">
              ⚠️ {error}
            </div>
          )}

          <form id="deviceForm" onSubmit={handleSubmit} className="space-y-6">

            {/* 기본 정보 섹션 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className={labelStyle}>Device Name *</label>
                <input required name="name" value={formData.name} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" placeholder="e.g. Core-Switch-01" />
              </div>
              <div className="space-y-1">
                <label className={labelStyle}>IP Address *</label>
                <input required name="ip_address" value={formData.ip_address} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white font-mono focus:ring-2 focus:ring-blue-500 outline-none" placeholder="192.168.1.1" />
              </div>
              <div className="space-y-1">
                <label className={labelStyle}>Device Type</label>
                <select name="device_type" value={formData.device_type} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none">
                  <optgroup label="Global Vendors">
                    <option value="cisco_ios">Cisco IOS</option>
                    <option value="cisco_xe">Cisco IOS-XE</option>
                    <option value="cisco_nxos">Cisco NX-OS</option>
                    <option value="cisco_wlc">Cisco WLC (Catalyst 9800)</option>
                    <option value="juniper_junos">Juniper Junos</option>
                    <option value="arista_eos">Arista EOS</option>
                    <option value="extreme_exos">Extreme Networks (EXOS)</option>
                    <option value="huawei">Huawei VRP</option>
                    <option value="hp_procurve">HP ProCurve / Aruba</option>
                    <option value="dell_os10">Dell OS10 / Force10</option>
                    <option value="fortinet">Fortinet FortiOS</option>
                    <option value="paloalto_panos">Palo Alto PanOS</option>
                    <option value="linux">Linux Server</option>
                  </optgroup>
                  <optgroup label="Domestic Vendors (Korea)">
                    <option value="dasan_nos">Dasan Networks (NOS)</option>
                    <option value="ubiquoss_l2">Ubiquoss (L2/L3)</option>
                    <option value="handream_sg">HanDreamnet (SG Security)</option>
                    <option value="piolink_pas">Piolink (PAS/L4)</option>
                  </optgroup>
                  <optgroup label="Other">
                    <option value="unknown">Generic / Unknown</option>
                  </optgroup>
                </select>
              </div>

              {/* [추가] Auto Provision Template */}
              <div className="space-y-1">
                <label className={labelStyle}>Auto Provision (Day 0)</label>
                <div className="relative">
                  <Terminal className="absolute left-3 top-3 text-purple-500" size={16} />
                  <select
                    name="auto_provision_template_id"
                    value={formData.auto_provision_template_id}
                    onChange={handleChange}
                    disabled={!!deviceToEdit} // 수정 시에는 ZTP 비활성화가 안전할 수 있음 (선택사항)
                    className="w-full pl-10 p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none appearance-none"
                  >
                    <option value="">-- No Auto Provision --</option>
                    {templates.map(tmpl => (
                      <option key={tmpl.id} value={tmpl.id}>
                        {tmpl.name} (v{tmpl.version})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* [추가] 사이트 선택 드롭다운 */}
              <div className="space-y-1">
                <label className={labelStyle}>Assign Site (Location)</label>
                <div className="relative">
                  <MapPin className="absolute left-3 top-3 text-gray-400" size={16} />
                  <select
                    name="site_id"
                    value={formData.site_id}
                    onChange={handleChange}
                    className="w-full pl-10 p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none appearance-none"
                  >
                    <option value="">-- Global (No Site) --</option>
                    {sites.map(site => (
                      <option key={site.id} value={site.id}>
                        {site.name} ({site.type})
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-1">
                <label className={labelStyle}>SNMP Community</label>
                <div className="relative">
                  <Globe className="absolute left-3 top-3 text-gray-400" size={16} />
                  <input name="snmp_community" value={formData.snmp_community} onChange={handleChange} className="w-full pl-10 p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" placeholder="public" />
                </div>
              </div>
            </div>

            {/* 인증 정보 섹션 */}
            <div className="pt-4 border-t border-gray-100 dark:border-gray-800">
              <h3 className="text-sm font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                <Shield size={16} className="text-indigo-500" /> SSH Credentials
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className={labelStyle}>Username</label>
                  <input name="ssh_username" value={formData.ssh_username} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" placeholder="admin" />
                </div>
                <div className="space-y-1">
                  <label className={labelStyle}>Password</label>
                  <input type="password" name="ssh_password" value={formData.ssh_password} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" placeholder={deviceToEdit ? "(Unchanged)" : "••••••••"} />
                </div>
                <div className="space-y-1">
                  <label className={labelStyle}>Enable Secret</label>
                  <input type="password" name="enable_password" value={formData.enable_password} onChange={handleChange} className="w-full p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" placeholder={deviceToEdit ? "(Unchanged)" : "Optional"} />
                </div>
                <div className="space-y-1">
                  <label className={labelStyle}>SSH Port</label>
                  <div className="relative">
                    <Terminal className="absolute left-3 top-3 text-gray-400" size={16} />
                    <input type="number" name="ssh_port" value={formData.ssh_port} onChange={handleChange} className="w-full pl-10 p-3 bg-gray-50 dark:bg-[#25282c] border border-gray-200 dark:border-gray-700 rounded-lg text-sm text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none" />
                  </div>
                </div>
              </div>
            </div>

          </form>
        </div>

        {/* 푸터 (버튼) */}
        <div className="p-6 border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-[#202327] flex justify-end gap-3">
          <button type="button" onClick={onClose} className="px-5 py-2.5 text-sm font-bold text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors">
            Cancel
          </button>
          <button
            type="submit"
            form="deviceForm"
            disabled={loading}
            className={`px-5 py-2.5 text-sm font-bold text-white rounded-lg shadow-lg flex items-center gap-2 transition-all
              ${loading ? 'bg-blue-400 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-blue-500/20'}`}
          >
            {loading ? (
              <>Processing...</>
            ) : (
              <>{deviceToEdit ? 'Update Changes' : 'Register Device'}</>
            )}
          </button>
        </div>

      </div>
    </div>
  );
};

export default DeviceAddModal;
