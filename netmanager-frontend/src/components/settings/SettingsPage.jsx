import React, { useState, useEffect, useCallback } from 'react';
import {
  CheckCircle, AlertTriangle, Trash2, X, Lock, Mail, UserPlus, Key,
  RefreshCw, Globe, Users, Shield, Bell, Database, Save, Plus, MoreHorizontal, Download, Upload
} from 'lucide-react';
import { SettingsService, SDNService, DeviceService } from '../../api/services';
import { useAuth } from '../../context/AuthContext'; // [RBAC]
import { useToast } from '../../context/ToastContext';
import { useNavigate } from 'react-router-dom';

const SettingsPage = () => {
  const { user, isAdmin } = useAuth(); // [RBAC]
  const { toast } = useToast();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('general');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [devices, setDevices] = useState([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  // const [currentUser, setCurrentUser] = useState(null); // Removed, use 'user' from context

  // 통합 설정 상태
  const [settings, setSettings] = useState({
    hostname: '',
    contact_email: '',
    timezone: 'UTC',
    language: 'English',
    session_timeout: 30,
    max_login_attempts: 5,
    enable_2fa: false,
    discovery_scope_include_cidrs: '',
    discovery_scope_exclude_cidrs: '',
    discovery_prefer_private: true,
    neighbor_crawl_scope_include_cidrs: '',
    neighbor_crawl_scope_exclude_cidrs: '',
    neighbor_crawl_prefer_private: true,
    auto_discovery_enabled: false,
    auto_discovery_interval_seconds: 1800,
    auto_discovery_mode: 'cidr',
    auto_discovery_cidr: '192.168.1.0/24',
    auto_discovery_seed_ip: '',
    auto_discovery_seed_device_id: '',
    auto_discovery_max_depth: 2,
    auto_discovery_site_id: '',
    auto_discovery_snmp_profile_id: '',
    auto_discovery_snmp_version: 'v2c',
    auto_discovery_snmp_port: 161,
    auto_discovery_refresh_topology: false,
    auto_topology_refresh_max_depth: 2,
    auto_topology_refresh_max_devices: 200,
    auto_topology_refresh_min_interval_seconds: 0.05,
    auto_discovery_last_run_at: '',
    auto_discovery_last_job_id: '',
    auto_discovery_last_job_cidr: '',
    auto_discovery_last_error: '',
    auto_topology_last_run_at: '',
    auto_topology_last_job_id: '',
    auto_topology_last_targets: '',
    auto_topology_last_enqueued_ok: '',
    auto_topology_last_enqueued_fail: '',
    auto_topology_last_error: '',
    auto_approve_enabled: false,
    auto_approve_min_vendor_confidence: 0.8,
    auto_approve_require_snmp_reachable: true,
    auto_approve_block_severities: 'error',
    auto_approve_trigger_topology: false,
    auto_approve_topology_depth: 2,
    auto_approve_trigger_sync: false,
    auto_approve_trigger_monitoring: false,
    smtp_host: '',
    smtp_port: 587,
    smtp_user: '',
    smtp_password: '',
    smtp_from: ''
  });

  // 사용자 관리 상태
  const [users, setUsers] = useState([]);
  const [showUserModal, setShowUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState(null);

  // 1. 초기 데이터 로드 (User is loaded by AuthContext)

  const loadTabData = useCallback(async () => {
    setLoading(true);
    try {
      if (activeTab === 'users') {
        const res = await SDNService.getUsers();
        setUsers(Array.isArray(res.data) ? res.data : []);
      } else if (activeTab !== 'backup') {
        const res = await SettingsService.getGeneral();
        const incoming = { ...(res.data || {}) };
        const truthy = (v) => {
          const s = String(v ?? '').trim().toLowerCase();
          return ['true', '1', 'yes', 'y', 'on'].includes(s);
        };
        if (incoming.discovery_prefer_private !== undefined) incoming.discovery_prefer_private = truthy(incoming.discovery_prefer_private);
        if (incoming.neighbor_crawl_prefer_private !== undefined) incoming.neighbor_crawl_prefer_private = truthy(incoming.neighbor_crawl_prefer_private);
        if (incoming.auto_discovery_enabled !== undefined) incoming.auto_discovery_enabled = truthy(incoming.auto_discovery_enabled);
        if (incoming.auto_discovery_refresh_topology !== undefined) incoming.auto_discovery_refresh_topology = truthy(incoming.auto_discovery_refresh_topology);
        if (incoming.auto_discovery_interval_seconds !== undefined) incoming.auto_discovery_interval_seconds = Number(incoming.auto_discovery_interval_seconds) || 0;
        if (incoming.auto_discovery_max_depth !== undefined) incoming.auto_discovery_max_depth = Number(incoming.auto_discovery_max_depth) || 0;
        if (incoming.auto_discovery_snmp_port !== undefined) incoming.auto_discovery_snmp_port = Number(incoming.auto_discovery_snmp_port) || 161;
        if (incoming.auto_topology_refresh_max_depth !== undefined) incoming.auto_topology_refresh_max_depth = Number(incoming.auto_topology_refresh_max_depth) || 0;
        if (incoming.auto_topology_refresh_max_devices !== undefined) incoming.auto_topology_refresh_max_devices = Number(incoming.auto_topology_refresh_max_devices) || 0;
        if (incoming.auto_topology_refresh_min_interval_seconds !== undefined) incoming.auto_topology_refresh_min_interval_seconds = Number(incoming.auto_topology_refresh_min_interval_seconds) || 0;
        if (incoming.auto_approve_enabled !== undefined) incoming.auto_approve_enabled = truthy(incoming.auto_approve_enabled);
        if (incoming.auto_approve_require_snmp_reachable !== undefined) incoming.auto_approve_require_snmp_reachable = truthy(incoming.auto_approve_require_snmp_reachable);
        if (incoming.auto_approve_trigger_topology !== undefined) incoming.auto_approve_trigger_topology = truthy(incoming.auto_approve_trigger_topology);
        if (incoming.auto_approve_trigger_sync !== undefined) incoming.auto_approve_trigger_sync = truthy(incoming.auto_approve_trigger_sync);
        if (incoming.auto_approve_trigger_monitoring !== undefined) incoming.auto_approve_trigger_monitoring = truthy(incoming.auto_approve_trigger_monitoring);
        if (incoming.auto_approve_min_vendor_confidence !== undefined) {
          const v = Number(incoming.auto_approve_min_vendor_confidence);
          incoming.auto_approve_min_vendor_confidence = Number.isFinite(v) ? v : 0.8;
        }
        if (incoming.auto_approve_topology_depth !== undefined) incoming.auto_approve_topology_depth = Number(incoming.auto_approve_topology_depth) || 0;
        setSettings(prev => ({ ...prev, ...incoming }));
      }
    } catch (err) {
      console.error(`Failed to load ${activeTab} data:`, err);
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    // fetchCurrentUser(); // Removed
    loadTabData();
  }, [loadTabData]);

  useEffect(() => {
    if (activeTab !== 'general') return;
    let cancelled = false;
    const run = async () => {
      try {
        setLoadingDevices(true);
        const res = await DeviceService.getAll();
        if (cancelled) return;
        setDevices(Array.isArray(res.data) ? res.data : []);
      } catch (e) {
        if (!cancelled) setDevices([]);
      } finally {
        if (!cancelled) setLoadingDevices(false);
      }
    };
    run();
    return () => { cancelled = true; };
  }, [activeTab]);

  // 2. 핸들러들
  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setSettings(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      await SettingsService.updateGeneral({ settings });
      toast.success('Settings updated successfully!');
      loadTabData();
    } catch (err) {
      toast.error('Failed to update settings: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  const applyAutoApprovePreset = (preset) => {
    const presets = {
      conservative: {
        auto_approve_enabled: true,
        auto_approve_min_vendor_confidence: 0.9,
        auto_approve_require_snmp_reachable: true,
        auto_approve_block_severities: 'error,warn',
        auto_approve_trigger_topology: false,
        auto_approve_topology_depth: 2,
        auto_approve_trigger_sync: false,
        auto_approve_trigger_monitoring: false,
      },
      balanced: {
        auto_approve_enabled: true,
        auto_approve_min_vendor_confidence: 0.85,
        auto_approve_require_snmp_reachable: true,
        auto_approve_block_severities: 'error',
        auto_approve_trigger_topology: true,
        auto_approve_topology_depth: 2,
        auto_approve_trigger_sync: true,
        auto_approve_trigger_monitoring: true,
      },
      aggressive: {
        auto_approve_enabled: true,
        auto_approve_min_vendor_confidence: 0.7,
        auto_approve_require_snmp_reachable: false,
        auto_approve_block_severities: 'error',
        auto_approve_trigger_topology: true,
        auto_approve_topology_depth: 3,
        auto_approve_trigger_sync: true,
        auto_approve_trigger_monitoring: true,
      },
    };
    const next = presets[String(preset || '').toLowerCase()];
    if (!next) return;
    setSettings(prev => ({ ...prev, ...next }));
    toast.success(`Applied preset: ${String(preset).toUpperCase()}`);
  };

  const openLastDiscoveryJob = () => {
    const raw = String(settings.auto_discovery_last_job_id || '').trim();
    const id = Number(raw);
    if (!Number.isFinite(id) || id <= 0) return;
    navigate('/discovery', { state: { jobId: id } });
  };

  const clearAutoDiscoveryError = async () => {
    setSaving(true);
    try {
      await SettingsService.updateGeneral({ settings: { auto_discovery_last_error: '' } });
      toast.success('Last error cleared.');
      loadTabData();
    } catch (err) {
      toast.error('Failed to clear error: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  const applyAutoDiscoveryPreset = (preset) => {
    const presets = {
      nightly: {
        auto_discovery_enabled: true,
        auto_discovery_interval_seconds: 86400,
        auto_discovery_mode: 'cidr',
        auto_discovery_cidr: '192.168.1.0/24',
        auto_discovery_seed_ip: '',
        auto_discovery_seed_device_id: '',
        auto_discovery_max_depth: 2,
        auto_discovery_snmp_version: 'v2c',
        auto_discovery_snmp_port: 161,
        auto_discovery_refresh_topology: true,
        auto_topology_refresh_max_depth: 2,
        auto_topology_refresh_max_devices: 200,
        auto_topology_refresh_min_interval_seconds: 0.05,
      },
      hourly: {
        auto_discovery_enabled: true,
        auto_discovery_interval_seconds: 3600,
        auto_discovery_mode: 'seed',
        auto_discovery_cidr: '192.168.1.0/24',
        auto_discovery_seed_ip: '',
        auto_discovery_seed_device_id: '',
        auto_discovery_max_depth: 2,
        auto_discovery_snmp_version: 'v2c',
        auto_discovery_snmp_port: 161,
        auto_discovery_refresh_topology: true,
        auto_topology_refresh_max_depth: 2,
        auto_topology_refresh_max_devices: 200,
        auto_topology_refresh_min_interval_seconds: 0.05,
      },
      lab: {
        auto_discovery_enabled: true,
        auto_discovery_interval_seconds: 300,
        auto_discovery_mode: 'seed',
        auto_discovery_cidr: '192.168.1.0/24',
        auto_discovery_seed_ip: '',
        auto_discovery_seed_device_id: '',
        auto_discovery_max_depth: 3,
        auto_discovery_snmp_version: 'v2c',
        auto_discovery_snmp_port: 161,
        auto_discovery_refresh_topology: true,
        auto_topology_refresh_max_depth: 3,
        auto_topology_refresh_max_devices: 500,
        auto_topology_refresh_min_interval_seconds: 0.02,
      },
      off: {
        auto_discovery_enabled: false,
      },
    };
    const next = presets[String(preset || '').toLowerCase()];
    if (!next) return;
    setSettings(prev => ({ ...prev, ...next }));
    toast.success(`Applied preset: ${String(preset).toUpperCase()}`);
  };

  const handleCreateUser = async (userData) => {
    try {
      await SDNService.createUser(userData);
      toast.success('User created!');
      setShowUserModal(false);
      loadTabData();
    } catch (err) {
      toast.error('Failed to create user: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!window.confirm('Are you sure you want to delete this user?')) return;
    try {
      await SDNService.deleteUser(userId);
      toast.success('User deleted.');
      loadTabData();
    } catch (err) {
      toast.error('Failed to delete user: ' + (err.response?.data?.detail || err.message));
    }
  };

  const openAddUserModal = () => {
    setEditingUser(null);
    setShowUserModal(true);
  };

  const handleTestEmail = async () => {
    const email = window.prompt("Enter recipient email address for testing:", settings.smtp_from || "");
    if (!email) return;

    setSaving(true);
    try {
      await SettingsService.sendTestEmail(email);
      toast.success(`Test email sent to ${email}.`);
    } catch (err) {
      toast.error('Failed to send email: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  // const isAdmin = currentUser?.role === 'admin'; // Removed, use isAdmin() function

  return (
    <div className="flex h-full bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white animate-fade-in overflow-hidden font-sans transition-colors duration-300">
      {/* Side Navigation */}
      <aside className="w-64 bg-white dark:bg-[#1b1d1f] border-r border-gray-200 dark:border-gray-800 flex flex-col flex-shrink-0">
        <div className="p-6 border-b border-gray-200 dark:border-gray-800">
          <h1 className="text-xl font-bold flex items-center gap-2">
            <RefreshCw className={`text-blue-500 ${loading ? 'animate-spin' : ''}`} size={20} />
            System Control
          </h1>
          <p className="text-xs text-gray-500 mt-1">Version v2.5.0 Global</p>
        </div>
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto custom-scrollbar">
          <SidebarItem icon={Globe} label="General Settings" active={activeTab === 'general'} onClick={() => setActiveTab('general')} />
          <SidebarItem icon={Users} label="User Management" active={activeTab === 'users'} onClick={() => setActiveTab('users')} />
          <SidebarItem icon={Shield} label="Security & RBAC" active={activeTab === 'security'} onClick={() => setActiveTab('security')} />
          <SidebarItem icon={Key} label="License Management" active={activeTab === 'license'} onClick={() => setActiveTab('license')} />
          <SidebarItem icon={Bell} label="Alert Channels" active={activeTab === 'notifications'} onClick={() => setActiveTab('notifications')} />
          <SidebarItem icon={Database} label="System Backup" active={activeTab === 'backup'} onClick={() => setActiveTab('backup')} />
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="h-16 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between px-8 bg-white dark:bg-[#1b1d1f] flex-shrink-0 z-10 transition-colors">
          <div>
            <h2 className="text-lg font-bold capitalize flex items-center gap-2">
              {activeTab.replace('-', ' ')}
              {!isAdmin() && user && (
                <span className="text-[10px] bg-red-500/10 text-red-500 px-2 py-0.5 rounded border border-red-500/20 uppercase font-black">Read Only</span>
              )}
            </h2>
          </div>

          <div className="flex gap-3">
            {activeTab !== 'users' && activeTab !== 'backup' && (
              <button
                onClick={handleSaveSettings}
                disabled={saving || !isAdmin()} // Call func
                className={`px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-bold rounded-lg flex items-center gap-2 transition-all shadow-lg shadow-blue-900/20
                  ${(saving || !isAdmin()) ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
                Save Changes
              </button>
            )}
            {activeTab === 'users' && isAdmin() && (
              <button
                onClick={openAddUserModal}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-bold rounded-lg flex items-center gap-2 transition-all"
              >
                <UserPlus size={16} /> Add New User
              </button>
            )}
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar bg-gray-50/50 dark:bg-[#202022]">
          <div className="max-w-4xl mx-auto space-y-12 pb-20">
            {activeTab === 'general' && <GeneralSettings settings={settings} onChange={handleChange} disabled={!isAdmin()} onApplyAutoApprovePreset={applyAutoApprovePreset} onApplyAutoDiscoveryPreset={applyAutoDiscoveryPreset} devices={devices} loadingDevices={loadingDevices} onOpenLastDiscoveryJob={openLastDiscoveryJob} onClearAutoDiscoveryError={clearAutoDiscoveryError} onReloadSettings={loadTabData} />}
            {activeTab === 'users' && (
              <UserManagement
                users={users}
                onDelete={handleDeleteUser}
                onAdd={openAddUserModal}
                isAdmin={isAdmin()} // Call func
              />
            )}
            {activeTab === 'security' && <SecuritySettings settings={settings} onChange={handleChange} disabled={!isAdmin()} />}
            {activeTab === 'notifications' && <NotificationSettings settings={settings} onChange={handleChange} onTest={handleTestEmail} disabled={!isAdmin()} />}
            {activeTab === 'license' && <LicenseSettings isAdmin={isAdmin()} />}
            {activeTab === 'backup' && <BackupSettings isAdmin={isAdmin()} />}
          </div>
        </div>
      </main>

      {showUserModal && (
        <UserModal
          onClose={() => setShowUserModal(false)}
          onSubmit={handleCreateUser}
          user={editingUser}
        />
      )}
    </div>
  );
};

// --- Sub-components ---

const GeneralSettings = ({ settings, onChange, disabled, onApplyAutoApprovePreset, onApplyAutoDiscoveryPreset, devices, loadingDevices, onOpenLastDiscoveryJob, onClearAutoDiscoveryError, onReloadSettings }) => (
  <>
    <Section title="Controller Identity" desc="Global identification and regional settings.">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Input label="System Hostname" name="hostname" value={settings.hostname} onChange={onChange} disabled={disabled} />
        <Input label="Contact Email" name="contact_email" value={settings.contact_email} onChange={onChange} disabled={disabled} />
        <Select label="Timezone" name="timezone" value={settings.timezone} onChange={onChange} disabled={disabled} options={['UTC', 'Asia/Seoul', 'America/New_York']} />
        <Select label="System Language" name="language" value={settings.language} onChange={onChange} disabled={disabled} options={['English', 'Korean']} />
      </div>
    </Section>

    <Section title="Auto Discovery Scope" desc="Control where discovery/crawl is allowed to run in production.">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <TextArea
          label="Discovery Include CIDRs"
          name="discovery_scope_include_cidrs"
          value={settings.discovery_scope_include_cidrs}
          onChange={onChange}
          disabled={disabled}
          placeholder="Example: 10.0.0.0/8, 192.168.0.0/16"
        />
        <TextArea
          label="Discovery Exclude CIDRs"
          name="discovery_scope_exclude_cidrs"
          value={settings.discovery_scope_exclude_cidrs}
          onChange={onChange}
          disabled={disabled}
          placeholder="Example: 10.10.10.0/24, 10.10.20.5/32"
        />
        <Toggle
          label="Prefer Private IPs"
          name="discovery_prefer_private"
          checked={!!settings.discovery_prefer_private}
          onChange={onChange}
          disabled={disabled}
          desc="Prioritize RFC1918 hosts first when scanning/crawling."
        />
      </div>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-8">
        <TextArea
          label="Neighbor Crawl Include CIDRs"
          name="neighbor_crawl_scope_include_cidrs"
          value={settings.neighbor_crawl_scope_include_cidrs}
          onChange={onChange}
          disabled={disabled}
          placeholder="Leave empty to use Discovery Include CIDRs"
        />
        <TextArea
          label="Neighbor Crawl Exclude CIDRs"
          name="neighbor_crawl_scope_exclude_cidrs"
          value={settings.neighbor_crawl_scope_exclude_cidrs}
          onChange={onChange}
          disabled={disabled}
          placeholder="Leave empty to use Discovery Exclude CIDRs"
        />
        <Toggle
          label="Prefer Private IPs (Crawl)"
          name="neighbor_crawl_prefer_private"
          checked={!!settings.neighbor_crawl_prefer_private}
          onChange={onChange}
          disabled={disabled}
          desc="Override crawl prioritization. Empty uses Discovery setting."
        />
      </div>
    </Section>

    <Section title="Auto Discovery Scheduler" desc="Run discovery/crawl periodically in production.">
      <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="font-black text-gray-900 dark:text-white">Recommended Presets</div>
            <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">
              Apply a baseline schedule, then Save Changes.
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onApplyAutoDiscoveryPreset?.('nightly')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-50 dark:hover:bg-[#1b1d1f]'} bg-white dark:bg-[#15171a] border-gray-200 dark:border-gray-800`}
            >
              Nightly
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoDiscoveryPreset?.('hourly')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-blue-50 dark:hover:bg-blue-600/10'} bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20`}
            >
              Hourly
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoDiscoveryPreset?.('lab')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-amber-50 dark:hover:bg-amber-500/10'} bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20`}
            >
              Lab
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoDiscoveryPreset?.('off')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-red-50 dark:hover:bg-red-500/10'} bg-red-500/10 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/20`}
            >
              Off
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Toggle
          label="Enable Auto Discovery"
          name="auto_discovery_enabled"
          checked={!!settings.auto_discovery_enabled}
          onChange={onChange}
          disabled={disabled}
          desc="When enabled, server will launch discovery jobs on a schedule."
        />
        <Input
          label="Interval Seconds"
          name="auto_discovery_interval_seconds"
          type="number"
          value={settings.auto_discovery_interval_seconds}
          onChange={onChange}
          disabled={disabled}
          placeholder="1800"
        />
        <Select
          label="Mode"
          name="auto_discovery_mode"
          value={settings.auto_discovery_mode}
          onChange={onChange}
          disabled={disabled}
          options={['cidr', 'seed']}
        />
        {String(settings.auto_discovery_mode || '').toLowerCase() === 'seed' && (
          <SelectRich
            label="Seed Device"
            name="auto_discovery_seed_device_id"
            value={String(settings.auto_discovery_seed_device_id || '')}
            onChangeValue={(v) => onChange({ target: { name: 'auto_discovery_seed_device_id', value: v, type: 'text' } })}
            disabled={disabled || loadingDevices}
            options={[
              { value: '', label: loadingDevices ? 'Loading...' : '(none)' },
              ...(Array.isArray(devices) ? devices.map(d => ({ value: String(d.id), label: `${d.name || d.hostname || `Device ${d.id}`} (${d.ip_address})` })) : []),
            ]}
          />
        )}
        <Input
          label="CIDR Target"
          name="auto_discovery_cidr"
          value={settings.auto_discovery_cidr}
          onChange={onChange}
          disabled={disabled}
          placeholder="192.168.1.0/24"
        />
        <Input
          label="Seed IP"
          name="auto_discovery_seed_ip"
          value={settings.auto_discovery_seed_ip}
          onChange={onChange}
          disabled={disabled}
          placeholder="192.168.0.1"
        />
        {String(settings.auto_discovery_mode || '').toLowerCase() !== 'seed' && (
          <Input
            label="Seed Device ID"
            name="auto_discovery_seed_device_id"
            value={settings.auto_discovery_seed_device_id}
            onChange={onChange}
            disabled={disabled}
            placeholder="(optional)"
          />
        )}
        <Input
          label="Max Depth (Seed)"
          name="auto_discovery_max_depth"
          type="number"
          value={settings.auto_discovery_max_depth}
          onChange={onChange}
          disabled={disabled}
          placeholder="2"
        />
        <Select
          label="SNMP Version"
          name="auto_discovery_snmp_version"
          value={settings.auto_discovery_snmp_version}
          onChange={onChange}
          disabled={disabled}
          options={['v2c', 'v3', 'v1']}
        />
        <Input
          label="SNMP Port"
          name="auto_discovery_snmp_port"
          type="number"
          value={settings.auto_discovery_snmp_port}
          onChange={onChange}
          disabled={disabled}
          placeholder="161"
        />
        <Input
          label="Site ID"
          name="auto_discovery_site_id"
          value={settings.auto_discovery_site_id}
          onChange={onChange}
          disabled={disabled}
          placeholder="(optional)"
        />
        <Input
          label="SNMP Profile ID"
          name="auto_discovery_snmp_profile_id"
          value={settings.auto_discovery_snmp_profile_id}
          onChange={onChange}
          disabled={disabled}
          placeholder="(optional)"
        />
      </div>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-8">
        <Toggle
          label="Refresh Topology After"
          name="auto_discovery_refresh_topology"
          checked={!!settings.auto_discovery_refresh_topology}
          onChange={onChange}
          disabled={disabled}
          desc="After starting an auto discovery job, enqueue topology refresh tasks."
        />
        <Input
          label="Topology Max Depth"
          name="auto_topology_refresh_max_depth"
          type="number"
          value={settings.auto_topology_refresh_max_depth}
          onChange={onChange}
          disabled={disabled}
          placeholder="2"
        />
        <Input
          label="Topology Max Devices"
          name="auto_topology_refresh_max_devices"
          type="number"
          value={settings.auto_topology_refresh_max_devices}
          onChange={onChange}
          disabled={disabled}
          placeholder="200"
        />
        <Input
          label="Topology Min Interval"
          name="auto_topology_refresh_min_interval_seconds"
          type="number"
          value={settings.auto_topology_refresh_min_interval_seconds}
          onChange={onChange}
          disabled={disabled}
          placeholder="0.05"
        />
      </div>

      <div className="mt-8 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="font-black text-gray-900 dark:text-white">Automation Status</div>
            <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">Read-only runtime info.</div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onReloadSettings?.()}
              className="px-3 py-1.5 rounded-xl text-xs font-black border transition-all bg-white dark:bg-[#15171a] border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-[#1b1d1f]"
            >
              Reload
            </button>
            <button
              type="button"
              onClick={() => onOpenLastDiscoveryJob?.()}
              disabled={!settings.auto_discovery_last_job_id}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${!settings.auto_discovery_last_job_id ? 'opacity-60 cursor-not-allowed' : 'hover:bg-blue-50 dark:hover:bg-blue-600/10'} bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20`}
            >
              Open Job
            </button>
            <button
              type="button"
              onClick={() => onClearAutoDiscoveryError?.()}
              disabled={!settings.auto_discovery_last_error || disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${(!settings.auto_discovery_last_error || disabled) ? 'opacity-60 cursor-not-allowed' : 'hover:bg-red-50 dark:hover:bg-red-500/10'} bg-red-500/10 text-red-600 dark:text-red-400 border-red-200 dark:border-red-500/20`}
            >
              Clear Error
            </button>
          </div>
        </div>
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <StatusItem label="Last Run At" value={settings.auto_discovery_last_run_at || '(never)'} />
          <StatusItem label="Last Job ID" value={settings.auto_discovery_last_job_id || '(none)'} />
          <StatusItem label="Last Job CIDR" value={settings.auto_discovery_last_job_cidr || '(none)'} />
          <StatusItem label="Last Error" value={settings.auto_discovery_last_error || '(none)'} />
        </div>

        <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <StatusItem label="Topo Last Run At" value={settings.auto_topology_last_run_at || '(never)'} />
          <StatusItem label="Topo Last Job ID" value={settings.auto_topology_last_job_id || '(none)'} />
          <StatusItem label="Topo Targets" value={settings.auto_topology_last_targets || '(none)'} />
          <StatusItem label="Topo Enqueue OK" value={settings.auto_topology_last_enqueued_ok || '(none)'} />
          <StatusItem label="Topo Enqueue Fail" value={settings.auto_topology_last_enqueued_fail || '(none)'} />
          <StatusItem label="Topo Last Error" value={settings.auto_topology_last_error || '(none)'} />
        </div>
      </div>
    </Section>

    <Section title="Auto Approve Policy" desc="Safely auto-approve only high-confidence discoveries.">
      <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
          <div>
            <div className="font-black text-gray-900 dark:text-white">Recommended Presets</div>
            <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">
              Apply a safe baseline, then Save Changes.
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => onApplyAutoApprovePreset?.('conservative')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-gray-50 dark:hover:bg-[#1b1d1f]'} bg-white dark:bg-[#15171a] border-gray-200 dark:border-gray-800`}
            >
              Conservative
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoApprovePreset?.('balanced')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-blue-50 dark:hover:bg-blue-600/10'} bg-blue-600/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-500/20`}
            >
              Balanced
            </button>
            <button
              type="button"
              onClick={() => onApplyAutoApprovePreset?.('aggressive')}
              disabled={disabled}
              className={`px-3 py-1.5 rounded-xl text-xs font-black border transition-all ${disabled ? 'opacity-60 cursor-not-allowed' : 'hover:bg-amber-50 dark:hover:bg-amber-500/10'} bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-500/20`}
            >
              Aggressive
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Toggle
          label="Enable Auto Approve"
          name="auto_approve_enabled"
          checked={!!settings.auto_approve_enabled}
          onChange={onChange}
          disabled={disabled}
          desc="When enabled, newly discovered devices may be auto-approved after scan/crawl completes."
        />
        <Input
          label="Min Vendor Confidence"
          name="auto_approve_min_vendor_confidence"
          type="number"
          value={settings.auto_approve_min_vendor_confidence}
          onChange={onChange}
          disabled={disabled}
          placeholder="0.8"
        />
        <Toggle
          label="Require SNMP Reachable"
          name="auto_approve_require_snmp_reachable"
          checked={!!settings.auto_approve_require_snmp_reachable}
          onChange={onChange}
          disabled={disabled}
          desc="Only auto-approve when SNMP is reachable."
        />
        <Input
          label="Block Severities"
          name="auto_approve_block_severities"
          value={settings.auto_approve_block_severities}
          onChange={onChange}
          disabled={disabled}
          placeholder="error"
        />
      </div>

      <div className="mt-8 grid grid-cols-1 md:grid-cols-2 gap-8">
        <Toggle
          label="Trigger Topology Refresh"
          name="auto_approve_trigger_topology"
          checked={!!settings.auto_approve_trigger_topology}
          onChange={onChange}
          disabled={disabled}
          desc="After auto-approve, enqueue topology refresh for approved devices."
        />
        <Input
          label="Topology Depth"
          name="auto_approve_topology_depth"
          type="number"
          value={settings.auto_approve_topology_depth}
          onChange={onChange}
          disabled={disabled}
          placeholder="2"
        />
        <Toggle
          label="Trigger SSH Sync"
          name="auto_approve_trigger_sync"
          checked={!!settings.auto_approve_trigger_sync}
          onChange={onChange}
          disabled={disabled}
          desc="After auto-approve, enqueue SSH sync jobs (uses Auto Sync settings)."
        />
        <Toggle
          label="Trigger Monitoring Burst"
          name="auto_approve_trigger_monitoring"
          checked={!!settings.auto_approve_trigger_monitoring}
          onChange={onChange}
          disabled={disabled}
          desc="After auto-approve, run a short monitoring burst to fill traffic state."
        />
      </div>
    </Section>
  </>
);

const UserManagement = ({ users, onDelete, onAdd, isAdmin }) => (
  <Section title="User Directory" desc="View and manage system access. (RBAC Enabled)">
    <div className="flex justify-end mb-4">
      {isAdmin && (
        <button onClick={onAdd} className="bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-2 transition-all">
          <Plus size={14} /> Add User
        </button>
      )}
    </div>
    <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl overflow-x-auto shadow-sm dark:shadow-xl">
      <table className="min-w-[640px] w-full text-left text-sm">
        <thead className="bg-gray-50 dark:bg-[#1b1d1f] text-gray-500 dark:text-gray-400 font-bold border-b border-gray-200 dark:border-gray-800">
          <tr>
            <th className="px-6 py-4">Identity</th>
            <th className="px-6 py-4">Role</th>
            <th className="px-6 py-4">Status</th>
            <th className="px-6 py-4 text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {users.length === 0 ? (
            <tr><td colSpan="4" className="px-6 py-10 text-center text-gray-500 italic">No users found or loading...</td></tr>
          ) : users.map(u => (
            <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-[#1b1d1f] transition-colors group text-gray-700 dark:text-gray-300">
              <td className="px-6 py-4">
                <div className="font-bold text-gray-900 dark:text-gray-200">{u.username}</div>
                <div className="text-[11px] text-gray-600 dark:text-gray-500">{u.full_name || 'N/A'} • {u.email}</div>
              </td>
              <td className="px-6 py-4">
                <span className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider border 
                  ${u.role === 'admin' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                    u.role === 'operator' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                      'bg-gray-500/10 text-gray-600 dark:text-gray-400 border-gray-500/20'}`}>
                  {u.role === 'admin' ? 'Administrator' : u.role === 'operator' ? 'Operator' : 'Viewer'}
                </span>
              </td>
              <td className="px-6 py-4">
                <div className={`flex items-center gap-2 ${u.is_active ? 'text-emerald-500' : 'text-gray-500'}`}>
                  <div className={`w-1.5 h-1.5 rounded-full ${u.is_active ? 'bg-emerald-500 animate-pulse' : 'bg-gray-500'}`} />
                  {u.is_active ? 'Active' : 'Disabled'}
                </div>
              </td>
              <td className="px-6 py-4 text-right">
                <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  {isAdmin && u.username !== 'admin' && (
                    <button onClick={() => onDelete(u.id)} className="p-2 hover:bg-red-100 dark:hover:bg-red-500/10 text-gray-500 hover:text-red-600 dark:hover:text-red-500 rounded-lg transition-all" title="Delete User">
                      <Trash2 size={16} />
                    </button>
                  )}
                  <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 hover:text-gray-900 dark:hover:text-white rounded-lg transition-all">
                    <MoreHorizontal size={16} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </Section>
);

const SecuritySettings = ({ settings, onChange, disabled }) => (
  <Section title="Auth Security" desc="Hardening session and authentication parameters.">
    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
      <Input label="Session Timeout (m)" name="session_timeout" type="number" value={settings.session_timeout} onChange={onChange} disabled={disabled} />
      <Input label="Max Retries" name="max_login_attempts" type="number" value={settings.max_login_attempts} onChange={onChange} disabled={disabled} />

      <div className="md:col-span-2 flex items-center justify-between p-5 bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 rounded-2xl shadow-sm">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-blue-500/10 rounded-xl text-blue-500">
            <Shield size={24} />
          </div>
          <div>
            <div className="font-bold text-gray-900 dark:text-white">Multi-Factor Authentication (MFA)</div>
            <div className="text-xs text-gray-500">Enable mandatory 2FA for all Administrative accounts.</div>
          </div>
        </div>
        <label className="relative inline-flex items-center cursor-pointer">
          <input type="checkbox" name="enable_2fa" checked={settings.enable_2fa} onChange={onChange} disabled={disabled} className="sr-only peer" />
          <div className="w-12 h-6 bg-gray-700 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
        </label>
      </div>
    </div>
  </Section>
);

const NotificationSettings = ({ settings, onChange, onTest, disabled }) => (
  <Section title="Alert Channels" desc="SMTP and SNMP notification delivery configuration.">
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-2">
          <Input label="SMTP Server" name="smtp_host" value={settings.smtp_host} onChange={onChange} disabled={disabled} placeholder="e.g. smtp.gmail.com" />
        </div>
        <Input label="Port" name="smtp_port" type="number" value={settings.smtp_port} onChange={onChange} disabled={disabled} />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Input label="Username" name="smtp_user" value={settings.smtp_user} onChange={onChange} disabled={disabled} />
        <Input label="Password" name="smtp_password" type="password" value={settings.smtp_password} onChange={onChange} disabled={disabled} />
      </div>
      <div className="flex gap-4 items-end">
        <div className="flex-1">
          <Input label="Sender Address (From)" name="smtp_from" value={settings.smtp_from} onChange={onChange} disabled={disabled} placeholder="netmanager@domain.com" />
        </div>
        <button
          onClick={onTest}
          disabled={disabled}
          className="px-4 py-3 bg-gray-800 hover:bg-gray-700 text-gray-200 rounded-xl transition-colors font-bold text-sm border border-gray-700 h-[50px] flex items-center gap-2"
        >
          <Mail size={16} /> Test Email
        </button>
      </div>
    </div>
  </Section>
);

const BackupSettings = ({ isAdmin }) => {
  const { toast } = useToast();
  return (
    <Section title="Data Resiliency" desc="Snapshot management and disaster recovery.">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <BackupCard title="Database Backup" icon={Download} color="blue" onClick={() => isAdmin && toast.info('Backup starting...')} active={isAdmin} />
        <BackupCard title="Restore Environment" icon={Upload} color="emerald" onClick={() => isAdmin && toast.info('Restore feature coming soon')} active={isAdmin} />
      </div>
    </Section>
  );
};

const LicenseSettings = ({ isAdmin }) => {
  const { toast } = useToast();
  const [licenseData, setLicenseData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [newKey, setNewKey] = useState("");

  const fetchLicense = async () => {
    try {
      // Mock API call - in real implementation, create GET /api/v1/license
      // Here we simulate checking the file or status
      // For now, let's use a mock response or try to imply from device count limits
      setLicenseData({
        status: "Active",
        customer: "Demo User",
        expiration: "2026-12-31",
        max_devices: 100,
        features: ["ZTP", "Fabric", "Monitoring"]
      });
    } catch (e) {
      setLicenseData({ status: "Invalid", customer: "Unknown" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchLicense(); }, []);

  const handleUpload = () => {
    if (!newKey) return toast.warning("Please enter a license key.");
    // Call API to save license key
    toast.success("License key updated! (Simulation)");
  };

  return (
    <Section title="Subscription & License" desc="Manage product activation and limits.">
      <div className="grid grid-cols-1 gap-6">
        <div className={`p-6 border rounded-2xl flex items-center justify-between ${licenseData?.status === 'Active' ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-red-500/5 border-red-500/20'}`}>
          <div className="flex items-center gap-4">
            <div className={`p-3 rounded-xl ${licenseData?.status === 'Active' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
              <Key size={24} />
            </div>
            <div>
              <div className="text-lg font-bold text-gray-900 dark:text-white mb-1">
                NetManager Enterprise
                <span className={`ml-2 text-xs px-2 py-0.5 rounded border uppercase ${licenseData?.status === 'Active' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
                  {licenseData?.status || "Unknown"}
                </span>
              </div>
              <div className="text-sm text-gray-500">
                Licensed to <span className="text-gray-700 dark:text-gray-300 font-bold">{licenseData?.customer || "..."}</span> • Expires {licenseData?.expiration}
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-2xl font-black text-gray-900 dark:text-white">{licenseData?.max_devices || 0}</div>
            <div className="text-xs text-gray-600 dark:text-gray-500 uppercase font-bold">Max Devices</div>
          </div>
        </div>

        {isAdmin && (
          <div className="bg-[#15171a] p-6 rounded-2xl border border-gray-800 space-y-4">
            <h4 className="font-bold text-white flex items-center gap-2"><Upload size={16} /> Update License Key</h4>
            <textarea
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              className="w-full h-32 bg-gray-100 dark:bg-black/30 border border-gray-300 dark:border-gray-800 rounded-xl p-4 text-xs font-mono text-gray-700 dark:text-gray-400 focus:outline-none focus:border-blue-500"
              placeholder="Paste your new license key string here..."
            />
            <div className="flex justify-end">
              <button onClick={handleUpload} className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-lg text-sm">
                Activate New License
              </button>
            </div>
          </div>
        )}
      </div>
    </Section>
  );
};


const UserModal = ({ onClose, onSubmit }) => {
  const [formData, setFormData] = useState({
    username: '', email: '', password: '', full_name: '', role: 'viewer', is_active: true
  });

  return (
    <div className="fixed inset-0 bg-black/50 dark:bg-black/80 backdrop-blur-sm z-[100] flex items-center justify-center p-4">
      <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-md rounded-2xl border border-gray-200 dark:border-gray-800 shadow-2xl animate-scale-in">
        <div className="flex justify-between items-center p-6 border-b border-gray-800">
          <h3 className="text-xl font-bold flex items-center gap-2"><Plus size={20} className="text-blue-500" /> Create User</h3>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-full text-gray-500 hover:text-gray-900 dark:hover:text-white transition-colors"><X size={20} /></button>
        </div>
        <div className="p-6 space-y-4">
          <Input label="Username" value={formData.username} onChange={(e) => setFormData({ ...formData, username: e.target.value })} />
          <Input label="Email Address" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} type="email" />
          <Input label="Full Name" value={formData.full_name} onChange={(e) => setFormData({ ...formData, full_name: e.target.value })} />
          <Input label="Password" value={formData.password} onChange={(e) => setFormData({ ...formData, password: e.target.value })} type="password" />
          <Select label="System Role" value={formData.role} onChange={(e) => setFormData({ ...formData, role: e.target.value })} options={['viewer', 'editor', 'admin']} />
        </div>
        <div className="p-6 border-t border-gray-800 flex gap-3">
          <button onClick={onClose} className="flex-1 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-xl font-bold transition-all">Cancel</button>
          <button onClick={() => onSubmit(formData)} className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold shadow-lg shadow-blue-900/40 transition-all">Create Account</button>
        </div>
      </div>
    </div>
  );
};

const SidebarItem = ({ icon: Icon, label, active, onClick }) => (
  <button onClick={onClick} className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-semibold transition-all group ${active ? 'bg-blue-50/80 dark:bg-blue-600/10 text-blue-600 dark:text-blue-400 border border-blue-200 dark:border-blue-500/20 shadow-sm' : 'text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-900 dark:hover:text-gray-200 border border-transparent'}`}>
    <Icon size={18} className={active ? 'text-blue-600 dark:text-blue-500' : 'text-gray-500 dark:text-gray-600 group-hover:text-gray-700 dark:group-hover:text-gray-400'} />
    {label}
  </button>
);

const Section = ({ title, desc, children }) => (
  <div className="animate-fade-in-up">
    <div className="mb-6 flex flex-col gap-1">
      <h3 className="text-xl font-black text-gray-900 dark:text-white tracking-tight">{title}</h3>
      <p className="text-xs text-gray-600 dark:text-gray-500 font-medium">{desc}</p>
    </div>
    {children}
  </div>
);

const Input = ({ label, name, value, onChange, type = "text", placeholder, disabled }) => (
  <div className="flex flex-col gap-2">
    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest flex items-center gap-1.5">
      {type === 'password' && <Lock size={10} />}
      {type === 'email' && <Mail size={10} />}
      {label}
    </label>
    <input
      type={type} name={name} value={value || ''} onChange={onChange} placeholder={placeholder} disabled={disabled}
      className={`w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-200 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all placeholder-gray-400 dark:placeholder-gray-700
        ${disabled ? 'opacity-60 bg-gray-100 dark:bg-gray-900 cursor-not-allowed' : ''}`}
    />
  </div>
);

const Select = ({ label, name, value, onChange, options, disabled }) => (
  <div className="flex flex-col gap-2">
    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{label}</label>
    <select
      name={name} value={value} onChange={onChange} disabled={disabled}
      className={`w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-200 focus:outline-none focus:border-blue-500 transition-all cursor-pointer appearance-none
        ${disabled ? 'opacity-60 bg-gray-100 dark:bg-gray-900 cursor-not-allowed' : ''}`}
    >
      {options.map(opt => <option key={opt} value={opt}>{opt}</option>)}
    </select>
  </div>
);

const SelectRich = ({ label, name, value, onChangeValue, options, disabled }) => (
  <div className="flex flex-col gap-2">
    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{label}</label>
    <select
      name={name}
      value={value}
      onChange={(e) => onChangeValue?.(e.target.value)}
      disabled={disabled}
      className={`w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-200 focus:outline-none focus:border-blue-500 transition-all cursor-pointer appearance-none
        ${disabled ? 'opacity-60 bg-gray-100 dark:bg-gray-900 cursor-not-allowed' : ''}`}
    >
      {(options || []).map(opt => <option key={String(opt.value)} value={opt.value}>{opt.label}</option>)}
    </select>
  </div>
);

const TextArea = ({ label, name, value, onChange, placeholder, disabled }) => (
  <div className="flex flex-col gap-2">
    <label className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{label}</label>
    <textarea
      name={name}
      value={value || ''}
      onChange={onChange}
      placeholder={placeholder}
      disabled={disabled}
      rows={5}
      className={`w-full bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3 text-sm text-gray-900 dark:text-gray-200 focus:outline-none focus:border-blue-500 focus:ring-4 focus:ring-blue-500/10 transition-all placeholder-gray-400 dark:placeholder-gray-700 resize-y
        ${disabled ? 'opacity-60 bg-gray-100 dark:bg-gray-900 cursor-not-allowed' : ''}`}
    />
  </div>
);

const Toggle = ({ label, name, checked, onChange, disabled, desc }) => (
  <div className="flex flex-col gap-2">
    <div className="flex items-center justify-between gap-4 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3">
      <div className="min-w-0">
        <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{label}</div>
        {desc && <div className="text-[11px] text-gray-600 dark:text-gray-500 mt-1">{desc}</div>}
      </div>
      <label className={`relative inline-flex items-center cursor-pointer ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}>
        <input type="checkbox" name={name} checked={!!checked} onChange={onChange} disabled={disabled} className="sr-only peer" />
        <div className="w-11 h-6 bg-gray-200 dark:bg-gray-800 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-500/10 rounded-full peer peer-checked:bg-blue-600 transition-colors"></div>
        <div className="absolute left-1 top-1 bg-white w-4 h-4 rounded-full transition-transform peer-checked:translate-x-5"></div>
      </label>
    </div>
  </div>
);

const StatusItem = ({ label, value }) => (
  <div className="bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-xl px-4 py-3">
    <div className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{label}</div>
    <div className="mt-1 text-sm font-bold text-gray-900 dark:text-gray-200 break-all">{String(value ?? '')}</div>
  </div>
);

const BackupCard = ({ title, icon: Icon, color, onClick, active }) => (
  <div
    onClick={onClick}
    className={`p-6 bg-white dark:bg-[#15171a] border border-gray-200 dark:border-gray-800 rounded-2xl transition-all flex items-center gap-5 group
      ${active ? `hover:border-${color}-500/50 cursor-pointer shadow-sm hover:shadow-md` : 'opacity-40 cursor-not-allowed'}`}
  >
    <div className={`p-4 bg-${color}-500/10 text-${color}-500 rounded-2xl group-hover:scale-110 transition-transform`}>
      <Icon size={28} />
    </div>
    <div>
      <div className="font-black text-gray-900 dark:text-white">{title}</div>
      <div className="text-[11px] text-gray-500 mt-1">Full system state capture</div>
    </div>
  </div>
);

export default SettingsPage;
