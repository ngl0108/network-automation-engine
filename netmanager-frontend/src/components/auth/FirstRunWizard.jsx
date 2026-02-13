import React, { useState } from 'react';
import {
    Shield, Check, Lock, ChevronRight, FileText, AlertTriangle
} from 'lucide-react';
import { AuthService } from '../../api/services';
import { useAuth } from '../../context/AuthContext';
import { useToast } from '../../context/ToastContext';

const FirstRunWizard = () => {
    const { user, refreshUser, logout } = useAuth();
    const { toast } = useToast();
    const [step, setStep] = useState(user?.eula_accepted ? 2 : 1);
    const [loading, setLoading] = useState(false);

    // Password State
    const [passData, setPassData] = useState({ current: '', new: '', confirm: '' });

    // EULA State
    const [eulaAccepted, setEulaAccepted] = useState(false);

    const handleEulaAccept = async () => {
        setLoading(true);
        try {
            await AuthService.acceptEula();
            setStep(2); // Move to Password Change
        } catch (e) {
            toast.error("Failed to accept EULA: " + e.message);
        } finally {
            setLoading(false);
        }
    };

    const handlePasswordChange = async () => {
        if (passData.new !== passData.confirm) {
            toast.warning("New passwords do not match.");
            return;
        }
        if (passData.new.length < 8) {
            toast.warning("Password must be at least 8 characters.");
            return;
        }

        setLoading(true);
        try {
            await AuthService.changePasswordMe(passData.current, passData.new);

            toast.success("Setup Complete! Entering Dashboard...");

            // Reload context from server to clear flags
            await refreshUser();
            // Navigation will happen automatically via ProtectedRoute re-render
        } catch (e) {
            toast.error("Failed to change password: " + (e.response?.data?.detail || e.message));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 z-[9999] bg-[#0e1012] flex items-center justify-center p-4">
            <div className="w-full max-w-2xl bg-[#1b1d1f] border border-gray-800 rounded-3xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">

                {/* Header */}
                <div className="p-8 border-b border-gray-800 flex items-center justify-between bg-black/20">
                    <div>
                        <h1 className="text-2xl font-black text-white flex items-center gap-3">
                            <img src="/logo_icon.png" alt="Logo" className="w-8 h-8 object-contain" />
                            Welcome to NetSphere
                        </h1>
                        <p className="text-gray-500 mt-2 text-sm font-medium">
                            Initial Security Setup Required
                        </p>
                    </div>
                    <div className="flex gap-2">
                        <button onClick={logout} className="text-xs text-gray-500 hover:text-white mr-4 underline">
                            Log Out
                        </button>
                        <StepIndicator num={1} active={step === 1} done={step > 1} label="EULA" />
                        <div className="w-8 h-[2px] bg-gray-800 self-center" />
                        <StepIndicator num={2} active={step === 2} done={false} label="Secure" />
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-10 custom-scrollbar">
                    {step === 1 && (
                        <div className="space-y-6 animate-fade-in">
                            <div className="flex items-center gap-3 text-amber-500 bg-amber-500/10 p-4 rounded-xl border border-amber-500/20">
                                <AlertTriangle size={24} />
                                <div className="text-xs font-bold">PLEASE READ CAREFULLY BEFORE PROCEEDING</div>
                            </div>

                            <div className="prose prose-invert prose-sm max-w-none bg-black/30 p-6 rounded-xl border border-gray-800 h-64 overflow-y-auto text-gray-400">
                                <h3>End User License Agreement (EULA)</h3>
                                <p><strong>1. Disclaimer of Warranty</strong><br />
                                    This software is provided "as is" without warranty of any kind. The entire risk as to the quality and performance of the software is with you. Should the software prove defective, you assume the cost of all necessary servicing, repair, or correction.</p>

                                <p><strong>2. Limitation of Liability</strong><br />
                                    In no event unless required by applicable law or agreed to in writing will the licensor be liable to you for damages, including any general, special, incidental or consequential damages arising out of the use or inability to use the software (including but not limited to loss of data or data being rendered inaccurate or losses sustained by you or third parties or a failure of the software to operate with any other software), even if such holder has been advised of the possibility of such damages.</p>

                                <p><strong>3. Network Operations Warning</strong><br />
                                    This software is capable of modifying network configurations automatically. You acknowledge that improper use may result in network outages, data loss, or security breaches. You agree to test all configurations in a lab environment before deploying to production.</p>
                            </div>

                            <label className="flex items-center gap-4 group cursor-pointer p-4 rounded-xl hover:bg-white/5 transition-colors border border-transparent hover:border-gray-700">
                                <input
                                    type="checkbox"
                                    className="w-5 h-5 rounded border-gray-600 bg-gray-700 text-blue-500 focus:ring-blue-500/50"
                                    checked={eulaAccepted}
                                    onChange={(e) => setEulaAccepted(e.target.checked)}
                                />
                                <span className="text-sm text-gray-300 group-hover:text-white transition-colors">
                                    I have read and agree to the End User License Agreement
                                </span>
                            </label>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="space-y-8 animate-fade-in max-w-md mx-auto py-4">
                            <div className="text-center">
                                <div className="w-16 h-16 bg-blue-500/10 text-blue-500 rounded-2xl flex items-center justify-center mx-auto mb-4">
                                    <Lock size={32} />
                                </div>
                                <h3 className="text-xl font-bold text-white">Secure Your Account</h3>
                                <p className="text-sm text-gray-500 mt-2">
                                    The default password is unsafe. Please set a strong password to continue.
                                </p>
                            </div>

                            <div className="space-y-4">
                                <Input label="Current Password" type="password" value={passData.current} onChange={e => setPassData({ ...passData, current: e.target.value })} />
                                <Input label="New Password" type="password" value={passData.new} onChange={e => setPassData({ ...passData, new: e.target.value })} placeholder="Min 8 chars" />
                                <Input label="Confirm Password" type="password" value={passData.confirm} onChange={e => setPassData({ ...passData, confirm: e.target.value })} />
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="p-6 border-t border-gray-800 bg-black/20 flex justify-end">
                    {step === 1 && (
                        <button
                            id="btn-accept"
                            disabled={!eulaAccepted || loading}
                            onClick={handleEulaAccept}
                            className="px-8 py-3 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl flex items-center gap-2 shadow-lg shadow-blue-900/20 transition-all"
                        >
                            {loading ? "Processing..." : <>Accept & Continue <ChevronRight size={18} /></>}
                        </button>
                    )}
                    {step === 2 && (
                        <button
                            onClick={handlePasswordChange}
                            disabled={loading || !passData.new || !passData.confirm}
                            className="px-8 py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl flex items-center gap-2 shadow-lg shadow-emerald-900/20 transition-all"
                        >
                            {loading ? "Updating..." : <>Complete Setup <Check size={18} /></>}
                        </button>
                    )}
                </div>
            </div>

        </div>
    );
};

const StepIndicator = ({ num, active, done, label }) => (
    <div className={`flex items-center gap-2 ${active ? 'opacity-100' : 'opacity-40'}`}>
        <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs transition-all
            ${active || done ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400'}`}>
            {done ? <Check size={14} /> : num}
        </div>
        <span className="text-xs font-bold uppercase tracking-wider text-white hidden sm:block">{label}</span>
    </div>
);

const Input = ({ label, type, value, onChange, placeholder }) => (
    <div>
        <label className="block text-[10px] uppercase font-bold text-gray-500 mb-1.5">{label}</label>
        <input
            type={type}
            value={value}
            onChange={onChange}
            placeholder={placeholder}
            className="w-full bg-black/20 border border-gray-700 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all"
        />
    </div>
);

export default FirstRunWizard;
