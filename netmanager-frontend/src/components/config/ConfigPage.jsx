import React, { useState, useEffect } from 'react';
import { DeviceService } from '../../api/services';
import { useAuth } from '../../context/AuthContext'; // [RBAC]
import { useToast } from '../../context/ToastContext';
import {
    FileCode, Save, Plus, Trash2, Play, Server,
    CheckCircle, AlertTriangle, X, RefreshCw, Copy, Layers
} from 'lucide-react';

const ConfigPage = () => {
    const { isOperator, isAdmin } = useAuth(); // [RBAC]
    const { toast } = useToast();

    // --- States ---
    const [templates, setTemplates] = useState([]);
    const [devices, setDevices] = useState([]); // Deployment device list
    const [loading, setLoading] = useState(false);

    // Selected Template (Editing)
    const [selectedTemplate, setSelectedTemplate] = useState(null);
    const [editName, setEditName] = useState("");
    const [editCategory, setEditCategory] = useState("User-Defined");
    const [editVendor, setEditVendor] = useState("any"); // [NEW] Vendor State
    const [editContent, setEditContent] = useState("");

    // Deploy Modal State
    const [isDeployModalOpen, setIsDeployModalOpen] = useState(false);
    const [selectedDeviceIds, setSelectedDeviceIds] = useState([]);
    const [deployResult, setDeployResult] = useState(null);
    const [deploying, setDeploying] = useState(false);

    // Snippet Import Modal State
    const [isSnippetModalOpen, setIsSnippetModalOpen] = useState(false);

    // --- Initial Load ---
    useEffect(() => {
        loadData();
    }, []);

    const loadData = async () => {
        setLoading(true);
        try {
            const [tmplRes, devRes] = await Promise.all([
                DeviceService.getTemplates(),
                DeviceService.getDevices()
            ]);
            setTemplates(tmplRes.data || []);
            setDevices(devRes.data || []);
        } catch (err) {
            console.error("Failed to load config data:", err);
        } finally {
            setLoading(false);
        }
    };

    // --- Template Handlers ---

    // 1. Enter new template creation mode
    const handleCreateNew = () => {
        setSelectedTemplate({ id: 'new' });
        setEditName("New Template");
        setEditCategory("User-Defined");
        setEditVendor("any");
        setEditContent("! -- NetManager Config Template --\nhostname {{ device.name }}\nservice password-encryption\n!");
    };

    // 2. Select Template
    const handleSelectTemplate = (tmpl) => {
        setSelectedTemplate(tmpl);
        setEditName(tmpl.name);
        setEditCategory(tmpl.category || "User-Defined");
        setEditContent(tmpl.content);

        // Parse vendor from tags (Format: "vendor:cisco,v1")
        if (tmpl.tags && tmpl.tags.includes('vendor:')) {
            const tag = tmpl.tags.split(',').find(t => t.startsWith('vendor:'));
            setEditVendor(tag ? tag.split(':')[1] : 'any');
        } else {
            setEditVendor('any');
        }
    };

    // 3. Save (Create or Update)
    const handleSave = async () => {
        if (!editName || !editContent) return toast.warning("Name and Content are required.");
        setLoading(true);

        try {
            // Build tags string
            const tagsList = ["v1"];
            if (editVendor && editVendor !== 'any') {
                tagsList.push(`vendor:${editVendor}`);
            }

            const payload = {
                name: editName,
                category: editCategory,
                content: editContent,
                tags: tagsList.join(',')
            };

            if (selectedTemplate.id === 'new') {
                // Create
                await DeviceService.createTemplate(payload);
                toast.success("Template Created!");
            } else {
                // Update
                if (DeviceService.updateTemplate) {
                    await DeviceService.updateTemplate(selectedTemplate.id, payload);
                    toast.success("Template Updated!");
                } else {
                    toast.warning("Update API is not implemented yet.");
                    return;
                }
            }

            // Refresh list & reset selection
            await loadData();
            setSelectedTemplate(null);
        } catch (err) {
            console.error(err);
            toast.error("Save Failed: " + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    // 4. Delete
    const handleDelete = async () => {
        if (!selectedTemplate || selectedTemplate.id === 'new') return;
        if (!window.confirm("Delete this template?")) return;

        setLoading(true);
        try {
            if (DeviceService.deleteTemplate) {
                await DeviceService.deleteTemplate(selectedTemplate.id);
                toast.success("Template Deleted.");
            } else {
                toast.warning("Delete API is not implemented yet.");
                return;
            }
            await loadData();
            setSelectedTemplate(null);
        } catch (err) {
            console.error(err);
            toast.error("Delete Failed: " + (err.response?.data?.detail || err.message));
        } finally {
            setLoading(false);
        }
    };

    // 5. Merge Snippet (Import Snippet)
    const handleImportSnippet = (snippetContent, snippetName) => {
        const separator = `\n! ========================================\n! [Imported] ${snippetName}\n! ========================================\n`;
        setEditContent(prev => prev + separator + snippetContent + "\n");
        setIsSnippetModalOpen(false);
    };

    // --- Deploy Logic ---

    const handleOpenDeploy = () => {
        if (!selectedTemplate || selectedTemplate.id === 'new') return toast.warning("Please save the template first.");
        setSelectedDeviceIds([]);
        setDeployResult(null);
        setIsDeployModalOpen(true);
    };

    const handleToggleDevice = (id) => {
        // Cannot select after results returned
        if (deployResult) return;

        setSelectedDeviceIds(prev =>
            prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]
        );
    };

    // Execute deployment (API call)
    const handleExecuteDeploy = async () => {
        if (selectedDeviceIds.length === 0) return toast.warning("Select at least one device.");

        setDeploying(true);
        setDeployResult(null);

        try {
            // services.js -> deployTemplate
            const res = await DeviceService.deployTemplate(selectedTemplate.id, selectedDeviceIds);

            // Handle backend response structure (res.data.summary expected)
            const summary = res.data.summary || [];
            setDeployResult(summary);

            if (summary.length === 0) {
                toast.info("Deployment signal sent, but no summary returned.");
                setIsDeployModalOpen(false);
            }
        } catch (err) {
            console.error("Deploy Error:", err);
            toast.error("Deployment Failed: " + (err.response?.data?.detail || err.message));
        } finally {
            setDeploying(false);
        }
    };

    // Template Filter (System vs User)
    const systemTemplates = templates.filter(t => t.category !== 'User-Defined');
    const userTemplates = templates.filter(t => t.category === 'User-Defined');

    return (
        <div className="flex flex-col md:flex-row h-full bg-gray-50 dark:bg-[#0e1012] text-gray-900 dark:text-white transition-colors">

            {/* 1. Left Sidebar: Template List */}
            <div className="w-full md:w-1/4 md:min-w-[280px] border-b md:border-b-0 md:border-r border-gray-200 dark:border-gray-800 flex flex-col bg-white dark:bg-[#15171a] max-h-[45dvh] md:max-h-none">
                <div className="p-4 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center">
                    <h2 className="font-bold flex items-center gap-2 text-lg">
                        <FileCode className="text-blue-500" size={20} /> Templates
                    </h2>
                    {/* [RBAC] Only Network Admin+ can create */}
                    {isOperator() && (
                        <button onClick={handleCreateNew} className="p-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg shadow-lg shadow-blue-500/20 transition-all">
                            <Plus size={18} />
                        </button>
                    )}
                </div>

                <div className="flex-1 overflow-y-auto custom-scrollbar p-4 space-y-6">
                    {/* User Templates */}
                    <div>
                        <h3 className="text-xs font-bold text-gray-500 dark:text-gray-500 uppercase mb-3 flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-blue-500"></span> User Defined ({userTemplates.length})
                        </h3>
                        <div className="space-y-2">
                            {userTemplates.length === 0 && <div className="text-sm text-gray-500 italic pl-4">No templates yet.</div>}
                            {userTemplates.map(tmpl => (
                                <div
                                    key={tmpl.id}
                                    onClick={() => handleSelectTemplate(tmpl)}
                                    className={`p-3 rounded-lg cursor-pointer text-sm flex justify-between items-center group transition-colors
                    ${selectedTemplate?.id === tmpl.id ? 'bg-blue-100 text-blue-600 border border-blue-300 dark:bg-blue-600/20 dark:text-blue-400 dark:border-blue-500/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 border border-transparent'}`}
                                >
                                    <div className="flex flex-col gap-1 w-full overflow-hidden">
                                        <span className="truncate font-medium">{tmpl.name}</span>
                                        {tmpl.tags && tmpl.tags.includes('vendor:') && (
                                            <span className="text-[9px] px-1 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 capitalize w-fit">
                                                {tmpl.tags.split(',').find(t => t.startsWith('vendor:')).split(':')[1]}
                                            </span>
                                        )}
                                    </div>
                                    <span className="text-[10px] bg-gray-200 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-600 dark:text-gray-500 group-hover:bg-gray-300 dark:group-hover:bg-black group-hover:text-gray-800 dark:group-hover:text-gray-300 transition-colors ml-2 shrink-0">
                                        {tmpl.category}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* System Templates */}
                    <div>
                        <h3 className="text-xs font-bold text-gray-500 dark:text-gray-500 uppercase mb-3 flex items-center gap-2">
                            <span className="w-2 h-2 rounded-full bg-purple-500"></span> System / Global ({systemTemplates.length})
                        </h3>
                        <div className="space-y-2">
                            {systemTemplates.length === 0 && <div className="text-sm text-gray-500 italic pl-4">No system templates.</div>}
                            {systemTemplates.map(tmpl => (
                                <div
                                    key={tmpl.id}
                                    onClick={() => handleSelectTemplate(tmpl)}
                                    className={`p-3 rounded-lg cursor-pointer text-sm flex justify-between items-center group transition-colors
                    ${selectedTemplate?.id === tmpl.id ? 'bg-purple-100 text-purple-600 border border-purple-300 dark:bg-purple-600/20 dark:text-purple-400 dark:border-purple-500/30' : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400 border border-transparent'}`}
                                >
                                    <div className="flex flex-col gap-1 w-full overflow-hidden">
                                        <span className="truncate font-medium">{tmpl.name}</span>
                                        {tmpl.tags && tmpl.tags.includes('vendor:') && (
                                            <span className="text-[9px] px-1 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400 capitalize w-fit">
                                                {tmpl.tags.split(',').find(t => t.startsWith('vendor:')).split(':')[1]}
                                            </span>
                                        )}
                                    </div>
                                    <span className="text-[10px] bg-gray-200 dark:bg-gray-800 px-1.5 py-0.5 rounded text-gray-600 dark:text-gray-500 group-hover:bg-gray-300 dark:group-hover:bg-black group-hover:text-gray-800 dark:group-hover:text-gray-300 transition-colors ml-2 shrink-0">
                                        {tmpl.category}
                                    </span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* 2. Main Editor Area */}
            <div className="flex-1 flex flex-col min-w-0 bg-gray-50 dark:bg-[#0e1012]">
                {selectedTemplate ? (
                    <>
                        {/* Toolbar */}
                        <div className="h-16 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between px-3 sm:px-4 md:px-6 bg-white dark:bg-[#15171a]">
                            <div className="flex items-center gap-4 flex-1 mr-4">
                                <input
                                    className="bg-transparent text-lg font-bold text-gray-900 dark:text-white outline-none w-full placeholder-gray-400 dark:placeholder-gray-600 focus:placeholder-gray-500"
                                    value={editName}
                                    onChange={(e) => setEditName(e.target.value)}
                                    placeholder="Template Name..."
                                />
                                {/* Vendor Selection */}
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-gray-500 uppercase font-bold whitespace-nowrap">Vendor:</span>
                                    <select
                                        value={editVendor}
                                        onChange={(e) => setEditVendor(e.target.value)}
                                        className="bg-gray-100 dark:bg-[#202327] border border-gray-300 dark:border-gray-700 rounded text-xs px-2 py-1 text-gray-900 dark:text-gray-300 outline-none focus:border-blue-500"
                                    >
                                        <option value="any">Any / Global</option>
                                        <optgroup label="Global Vendors">
                                            <option value="cisco_ios">Cisco IOS</option>
                                            <option value="cisco_nxos">Cisco NX-OS</option>
                                            <option value="juniper_junos">Juniper</option>
                                            <option value="arista_eos">Arista</option>
                                            <option value="extreme_exos">Extreme</option>
                                            <option value="huawei">Huawei</option>
                                            <option value="hp_procurve">HP</option>
                                            <option value="dell_os10">Dell</option>
                                            <option value="linux">Linux</option>
                                        </optgroup>
                                        <optgroup label="Domestic (Korea)">
                                            <option value="dasan_nos">Dasan</option>
                                            <option value="ubiquoss_l2">Ubiquoss</option>
                                            <option value="handream_sg">Handream</option>
                                            <option value="piolink_pas">Piolink</option>
                                        </optgroup>
                                    </select>
                                </div>
                                {/* Category Selection */}
                                <div className="flex items-center gap-2">
                                    <span className="text-xs text-gray-500 uppercase font-bold whitespace-nowrap">Group:</span>
                                    <select
                                        value={editCategory}
                                        onChange={(e) => setEditCategory(e.target.value)}
                                        className="bg-gray-100 dark:bg-[#202327] border border-gray-300 dark:border-gray-700 rounded text-xs px-2 py-1 text-gray-900 dark:text-gray-300 outline-none focus:border-blue-500"
                                    >
                                        <option value="User-Defined">User Defined</option>
                                        <option value="Global">Global</option>
                                        <option value="Branch">Branch Site</option>
                                        <option value="DC">Data Center</option>
                                        <option value="Switching">Switching</option>
                                        <option value="Routing">Routing</option>
                                        <option value="Security">Security</option>
                                    </select>
                                </div>
                            </div>
                            <div className="flex gap-2">
                                <button
                                    onClick={() => setIsSnippetModalOpen(true)}
                                    className="flex items-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-800 hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 rounded border border-gray-300 dark:border-gray-700 transition-colors text-xs font-bold mr-2"
                                    title="Merge another template into this one"
                                >
                                    <Copy size={14} /> Merge Snippet
                                </button>

                                {selectedTemplate.id !== 'new' && (
                                    <>
                                        {/* [RBAC] Only Admin can delete */}
                                        {isAdmin() && (
                                            <button
                                                onClick={handleDelete}
                                                className="flex items-center gap-2 px-4 py-2 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors text-sm font-medium"
                                            >
                                                <Trash2 size={16} /> Delete
                                            </button>
                                        )}
                                        {/* [RBAC] Network Admin+ can deploy */}
                                        {isOperator() && (
                                            <button
                                                onClick={handleOpenDeploy}
                                                className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded shadow-lg shadow-green-900/20 transition-colors text-sm font-bold"
                                            >
                                                <Play size={16} /> Deploy
                                            </button>
                                        )}
                                    </>
                                )}
                                <button
                                    onClick={handleSave}
                                    disabled={loading}
                                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded shadow-lg shadow-blue-900/20 transition-colors text-sm font-bold disabled:opacity-50"
                                >
                                    {loading ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />}
                                    Save
                                </button>
                            </div>
                        </div>

                        {/* Code Editor */}
                        <div className="flex-1 p-6 relative flex flex-col">
                            <textarea
                                className="flex-1 w-full bg-white dark:bg-[#1b1d1f] text-gray-900 dark:text-gray-300 font-mono text-sm p-6 rounded-xl border border-gray-200 dark:border-gray-800 outline-none resize-none focus:border-blue-500/50 transition-colors leading-relaxed custom-scrollbar shadow-inner"
                                value={editContent}
                                onChange={(e) => setEditContent(e.target.value)}
                                placeholder="# Write your Jinja2 configuration template here...&#10;hostname {{ device.name }}&#10;interface GigabitEthernet1&#10; ip address {{ device.ip_address }} 255.255.255.0"
                                spellCheck="false"
                            />
                            <div className="absolute bottom-4 right-8 flex items-center gap-4 pointer-events-none">
                                <div className="text-xs text-gray-300 dark:text-gray-600 bg-gray-900/80 dark:bg-black/50 px-2 py-1 rounded backdrop-blur">
                                    Variables available: {`{{ hostname }}, {{ management_ip }}, {{ device.model }}`}
                                </div>
                                <div className="text-xs text-blue-300 dark:text-blue-500/50 bg-gray-900/80 dark:bg-black/50 px-2 py-1 rounded backdrop-blur font-bold">
                                    Jinja2 Syntax Supported
                                </div>
                            </div>
                        </div>
                    </>
                ) : (
                    <div className="flex-1 flex flex-col items-center justify-center text-gray-600">
                        <div className="p-8 bg-white dark:bg-[#15171a] rounded-full mb-6 animate-pulse shadow-sm">
                            <FileCode size={64} className="opacity-20 text-blue-500" />
                        </div>
                        <p className="text-xl font-bold text-gray-500 dark:text-gray-400">Select a template to edit</p>
                        <p className="text-sm mt-2 text-gray-400">or create a new one to start building configurations.</p>
                        <button onClick={handleCreateNew} className="mt-8 px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-xl font-bold shadow-lg shadow-blue-500/20 transition-all flex items-center gap-2">
                            <Plus size={18} /> Create First Template
                        </button>
                    </div>
                )}
            </div>

            {/* 3. Deployment Modal */}
            {isDeployModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 dark:bg-black/80 backdrop-blur-sm animate-fade-in">
                    <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-4xl h-[80vh] rounded-2xl border border-gray-200 dark:border-gray-800 shadow-2xl flex flex-col overflow-hidden animate-scale-in">

                        {/* Modal Header */}
                        <div className="p-6 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center bg-gray-50 dark:bg-[#202327]">
                            <div>
                                <h2 className="text-xl font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                    <Play className="text-green-500" /> Deploy Configuration
                                </h2>
                                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                    Applying template <span className="text-blue-500 dark:text-blue-400 font-mono">'{selectedTemplate.name}'</span>
                                </p>
                            </div>
                            <button onClick={() => setIsDeployModalOpen(false)} className="p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors">
                                <X className="text-gray-400 hover:text-gray-900 dark:hover:text-white" />
                            </button>
                        </div>

                        {/* Modal Body */}
                        <div className="flex-1 overflow-hidden flex">

                            {/* Left: Device Selection */}
                            <div className="w-1/2 p-6 border-r border-gray-200 dark:border-gray-800 overflow-y-auto custom-scrollbar">
                                <div className="flex justify-between items-center mb-4">
                                    <h3 className="text-sm font-bold text-gray-500 dark:text-gray-400 uppercase">Target Devices</h3>
                                    <span className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 px-2 py-1 rounded font-bold border border-blue-200 dark:border-blue-500/30">
                                        {selectedDeviceIds.length} Selected
                                    </span>
                                </div>
                                <div className="space-y-2">
                                    {devices.length === 0 && <div className="text-gray-500 text-sm italic">No devices found.</div>}
                                    {devices.map(dev => (
                                        <div
                                            key={dev.id}
                                            onClick={() => !deploying && !deployResult && handleToggleDevice(dev.id)}
                                            className={`flex items-center gap-3 p-3 rounded-lg border transition-all cursor-pointer group
                        ${selectedDeviceIds.includes(dev.id)
                                                    ? 'bg-blue-50 border-blue-200 dark:bg-blue-600/10 dark:border-blue-500/50'
                                                    : 'bg-white dark:bg-[#25282c] border-transparent hover:bg-gray-50 dark:hover:bg-[#2d3136]'
                                                } ${(deploying || deployResult) ? 'pointer-events-none opacity-50' : ''}`}
                                        >
                                            <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors
                        ${selectedDeviceIds.includes(dev.id) ? 'bg-blue-500 border-blue-500' : 'border-gray-300 dark:border-gray-600 group-hover:border-gray-400'}`}>
                                                {selectedDeviceIds.includes(dev.id) && <CheckCircle size={12} className="text-white" />}
                                            </div>
                                            <div>
                                                <div className="text-sm font-bold text-gray-900 dark:text-gray-200">{dev.name}</div>
                                                <div className="text-xs text-gray-500">{dev.ip_address}</div>
                                            </div>
                                            <div className={`ml-auto px-2 py-0.5 rounded text-[10px] uppercase font-bold ${dev.status === 'online' ? 'text-green-600 bg-green-50 dark:text-emerald-500 dark:bg-emerald-500/10' : 'text-red-600 bg-red-50 dark:text-red-500 dark:bg-red-500/10'}`}>
                                                {dev.status}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Right: Execution Log */}
                            <div className="w-1/2 p-6 bg-gray-50 dark:bg-black flex flex-col">
                                <h3 className="text-sm font-bold text-gray-500 dark:text-gray-400 uppercase mb-4 flex items-center gap-2">
                                    <Server size={16} /> Execution Output
                                </h3>
                                <div className="flex-1 bg-white dark:bg-[#0e1012] border border-gray-200 dark:border-gray-800 rounded-lg p-4 font-mono text-xs overflow-y-auto custom-scrollbar">
                                    {!deployResult && !deploying && (
                                        <div className="text-gray-500 dark:text-gray-600 flex flex-col items-center justify-center h-full">
                                            <p>Select devices and click Execute.</p>
                                        </div>
                                    )}
                                    {deploying && (
                                        <div className="text-gray-500 dark:text-gray-400 flex flex-col items-center justify-center h-full gap-3">
                                            <RefreshCw className="animate-spin text-blue-500" size={24} />
                                            <p className="animate-pulse">Deploying configuration...</p>
                                        </div>
                                    )}
                                    {deployResult && (
                                        <div className="space-y-4">
                                            {deployResult.map((res, idx) => (
                                                <div key={idx} className="border-b border-gray-100 dark:border-gray-800 pb-4 last:border-0 animation-fade-in-up" style={{ animationDelay: `${idx * 100}ms` }}>
                                                    <div className="flex items-center gap-2 mb-2">
                                                        {res.status === 'success' ? <CheckCircle size={14} className="text-green-500" /> : <AlertTriangle size={14} className="text-red-500" />}
                                                        <span className="font-bold text-gray-900 dark:text-gray-300">{res.device_name || res.device_id}</span>
                                                        <span className={`text-[10px] px-1.5 rounded uppercase font-bold ${res.status === 'success' ? 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400' : 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400'}`}>
                                                            {res.status}
                                                        </span>
                                                    </div>
                                                    <pre className="text-gray-600 dark:text-gray-400 whitespace-pre-wrap pl-5 border-l-2 border-gray-200 dark:border-gray-800">
                                                        {res.output || res.message || res.error || "No output."}
                                                    </pre>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Modal Footer */}
                        <div className="p-4 border-t border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-[#202327] flex justify-end gap-3">
                            <button
                                onClick={() => setIsDeployModalOpen(false)}
                                disabled={deploying}
                                className="px-6 py-3 text-sm font-bold text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white transition-colors disabled:opacity-50 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg"
                            >
                                Close
                            </button>
                            {!deployResult && (
                                <button
                                    onClick={handleExecuteDeploy}
                                    disabled={deploying || selectedDeviceIds.length === 0}
                                    className={`px-6 py-3 rounded-lg text-sm font-bold text-white flex items-center gap-2 shadow-lg transition-all
                    ${deploying || selectedDeviceIds.length === 0
                                            ? 'bg-gray-400 dark:bg-gray-600 cursor-not-allowed opacity-50'
                                            : 'bg-green-600 hover:bg-green-500 shadow-green-500/20 hover:shadow-green-500/40 transform hover:-translate-y-0.5'}`}
                                >
                                    {deploying ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} />}
                                    {deploying ? 'Deploying...' : 'Execute Deployment'}
                                </button>
                            )}
                        </div>

                    </div>
                </div>
            )}

            {/* 4. Snippet Import Modal (New) */}
            {isSnippetModalOpen && (
                <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 dark:bg-black/80 backdrop-blur-sm animate-fade-in">
                    <div className="bg-white dark:bg-[#1b1d1f] w-full max-w-2xl rounded-2xl border border-gray-200 dark:border-gray-800 shadow-2xl overflow-hidden animate-scale-in">
                        <div className="p-6 border-b border-gray-200 dark:border-gray-800 flex justify-between items-center bg-gray-50 dark:bg-[#202327]">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white flex items-center gap-2">
                                <Layers className="text-purple-500 dark:text-purple-400" /> Merge Snippet
                            </h3>
                            <button onClick={() => setIsSnippetModalOpen(false)}><X className="text-gray-400 hover:text-gray-900 dark:hover:text-white" /></button>
                        </div>
                        <div className="p-6 bg-white dark:bg-[#0e1012] max-h-[60vh] overflow-y-auto custom-scrollbar">
                            <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">Select a template to append to your current configuration:</p>

                            <div className="grid grid-cols-1 gap-2">
                                {templates.map(tmpl => (
                                    <div
                                        key={tmpl.id}
                                        onClick={() => handleImportSnippet(tmpl.content, tmpl.name)}
                                        className="p-4 bg-gray-50 dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-800 hover:border-purple-400 dark:hover:border-purple-500/50 hover:bg-purple-50 dark:hover:bg-purple-900/10 rounded-xl cursor-pointer transition-all group"
                                    >
                                        <div className="flex justify-between items-center">
                                            <div className="font-bold text-gray-900 dark:text-gray-200 group-hover:text-purple-600 dark:group-hover:text-purple-300">{tmpl.name}</div>
                                            <div className="text-[10px] bg-gray-200 dark:bg-gray-800 px-2 py-1 rounded text-gray-600 dark:text-gray-400 border border-gray-300 dark:border-gray-700">{tmpl.category}</div>
                                        </div>
                                        <div className="text-xs text-gray-500 dark:text-gray-600 mt-2 font-mono truncate opacity-60">
                                            {tmpl.content.slice(0, 60)}...
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}

        </div>
    );
};

export default ConfigPage;
