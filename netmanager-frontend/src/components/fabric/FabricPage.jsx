import React, { useState, useEffect } from 'react';
import { Layers, Server, ArrowRight, CheckCircle, Code, RefreshCw, Box, Play } from 'lucide-react';
import { SDNService, DeviceService } from '../../api/services';
import { useToast } from '../../context/ToastContext';

const FabricPage = () => {
    const { toast } = useToast();
    const [step, setStep] = useState(1);
    const [devices, setDevices] = useState([]);
    const [spines, setSpines] = useState([]);
    const [leafs, setLeafs] = useState([]);
    const [generatedConfigs, setGeneratedConfigs] = useState(null);
    const [loading, setLoading] = useState(false);

    // Params
    const [asn, setAsn] = useState(65000);
    const [vniBase, setVniBase] = useState(10000);

    useEffect(() => {
        fetchDevices();
    }, []);

    const fetchDevices = async () => {
        try {
            const res = await DeviceService.getDevices();
            setDevices(res.data);
        } catch (e) {
            console.error(e);
        }
    };

    const toggleSelection = (id, type) => {
        if (type === 'spine') {
            setSpines(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
            // Ensure not in leaf
            setLeafs(prev => prev.filter(x => x !== id));
        } else {
            setLeafs(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
            // Ensure not in spine
            setSpines(prev => prev.filter(x => x !== id));
        }
    };

    const handleGenerate = async () => {
        setLoading(true);
        try {
            const res = await SDNService.generateFabric({
                spine_ids: spines,
                leaf_ids: leafs,
                asn: asn,
                vni_base: vniBase
            });
            setGeneratedConfigs(res.data);
            setStep(3);
        } catch (e) {
            toast.error("Generation failed: " + e.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012] h-full text-gray-900 dark:text-white animate-fade-in flex flex-col">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <Layers className="text-pink-500" /> Fabric Automation: VXLAN EVPN
                    </h1>
                    <p className="text-sm text-gray-500">Automated Spine-Leaf Fabric Builder</p>
                </div>
                <div className="flex gap-2">
                    {/* Steps Indicator */}
                    {[1, 2, 3].map(s => (
                        <div key={s} className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm ${step >= s ? 'bg-pink-600' : 'bg-gray-800 text-gray-500'}`}>
                            {s}
                        </div>
                    ))}
                </div>
            </div>

            <div className="flex-1 overflow-hidden bg-[#1b1d1f] border border-gray-800 rounded-xl flex flex-col">

                {/* Step 1: Device Selection */}
                {step === 1 && (
                    <div className="p-6 flex-1 flex flex-col">
                        <h2 className="text-lg font-bold mb-4 flex items-center gap-2">
                            <Box size={20} className="text-pink-400" /> Assign Roles
                        </h2>

                        <div className="flex-1 overflow-y-auto grid grid-cols-2 gap-4">
                            {/* Spines Column */}
                            <div className="border border-gray-700 rounded-lg p-4 bg-[#0e1012]">
                                <h3 className="font-bold text-gray-600 dark:text-gray-400 mb-3 border-b border-gray-300 dark:border-gray-700 pb-2">SPINE ({spines.length})</h3>
                                {devices.map(dev => (
                                    <div key={dev.id}
                                        onClick={() => toggleSelection(dev.id, 'spine')}
                                        className={`p-3 mb-2 rounded border cursor-pointer border-gray-700 flex justify-between items-center ${spines.includes(dev.id) ? 'bg-pink-900/30 border-pink-500' : 'bg-gray-800'}`}
                                    >
                                        <div className="flex items-center gap-2">
                                            <Server size={14} />
                                            <span className="text-sm font-bold">{dev.name}</span>
                                        </div>
                                        {spines.includes(dev.id) && <CheckCircle size={14} className="text-pink-500" />}
                                    </div>
                                ))}
                            </div>

                            {/* Leafs Column */}
                            <div className="border border-gray-700 rounded-lg p-4 bg-[#0e1012]">
                                <h3 className="font-bold text-gray-600 dark:text-gray-400 mb-3 border-b border-gray-300 dark:border-gray-700 pb-2">LEAF ({leafs.length})</h3>
                                {devices.map(dev => (
                                    <div key={dev.id}
                                        onClick={() => toggleSelection(dev.id, 'leaf')}
                                        className={`p-3 mb-2 rounded border cursor-pointer border-gray-700 flex justify-between items-center ${leafs.includes(dev.id) ? 'bg-cyan-900/30 border-cyan-500' : 'bg-gray-800'}`}
                                    >
                                        <div className="flex items-center gap-2">
                                            <Server size={14} />
                                            <span className="text-sm font-bold">{dev.name}</span>
                                        </div>
                                        {leafs.includes(dev.id) && <CheckCircle size={14} className="text-cyan-500" />}
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="mt-6 flex justify-end">
                            <button
                                onClick={() => setStep(2)}
                                disabled={spines.length === 0 || leafs.length === 0}
                                className="px-6 py-2 bg-pink-600 hover:bg-pink-500 rounded font-bold transition-colors disabled:opacity-50"
                            >
                                Next: Parameters <ArrowRight size={16} className="inline ml-1" />
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 2: Parameters */}
                {step === 2 && (
                    <div className="p-6 flex-1 flex flex-col justify-center items-center max-w-2xl mx-auto w-full">
                        <h2 className="text-xl font-bold mb-6">Fabric Parameters</h2>

                        <div className="w-full space-y-4">
                            <div>
                                <label className="block text-gray-600 dark:text-gray-400 text-sm mb-1">BGP Autonomous System (ASN)</label>
                                <input
                                    type="number"
                                    value={asn}
                                    onChange={(e) => setAsn(parseInt(e.target.value))}
                                    className="w-full bg-[#0e1012] border border-gray-700 p-3 rounded text-white"
                                />
                            </div>
                            <div>
                                <label className="block text-gray-600 dark:text-gray-400 text-sm mb-1">VNI Base (L2 VNI Start)</label>
                                <input
                                    type="number"
                                    value={vniBase}
                                    onChange={(e) => setVniBase(parseInt(e.target.value))}
                                    className="w-full bg-[#0e1012] border border-gray-700 p-3 rounded text-white"
                                />
                            </div>
                        </div>

                        <div className="mt-8 flex gap-4 w-full">
                            <button onClick={() => setStep(1)} className="flex-1 py-3 border border-gray-700 rounded hover:bg-gray-800">Back</button>
                            <button
                                onClick={handleGenerate}
                                className="flex-1 py-3 bg-pink-600 hover:bg-pink-500 rounded font-bold flex items-center justify-center gap-2"
                            >
                                {loading ? <RefreshCw className="animate-spin" /> : <Code />} Generate Configs
                            </button>
                        </div>
                    </div>
                )}

                {/* Step 3: Preview */}
                {step === 3 && generatedConfigs && (
                    <div className="p-6 flex-1 flex flex-col overflow-hidden">
                        <h2 className="text-lg font-bold mb-4 flex items-center justify-between">
                            <span>Configuration Preview</span>
                            <span className="text-sm bg-green-900/30 text-green-400 px-3 py-1 rounded">Ready to Deploy</span>
                        </h2>

                        <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 gap-4">
                            {Object.entries(generatedConfigs).map(([devId, config]) => (
                                <div key={devId} className="bg-[#0e1012] border border-gray-700 rounded-lg p-4 font-mono text-xs overflow-x-auto">
                                    <div className="text-pink-400 font-bold mb-2"># Device ID: {devId}</div>
                                    <pre className="text-gray-300 whitespace-pre-wrap">{config}</pre>
                                </div>
                            ))}
                        </div>

                        <div className="mt-6 flex justify-end gap-3">
                            <button onClick={() => setStep(2)} className="px-4 py-2 border border-gray-700 rounded hover:bg-gray-800">Back</button>
                            <button
                                onClick={() => toast.info("Configs pushed via ZTP/SSH driver! (Mocked for Demo)")}
                                className="px-6 py-2 bg-green-600 hover:bg-green-500 rounded font-bold flex items-center gap-2"
                            >
                                <Play size={16} fill="currentColor" /> Deploy to Fabric
                            </button>
                        </div>
                    </div>
                )}

            </div>
        </div>
    );
};

export default FabricPage;
