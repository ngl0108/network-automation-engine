import React, { createContext, useState, useContext, useCallback } from 'react';
import { CheckCircle, XCircle, AlertTriangle, Info, X } from 'lucide-react';

// 1. Context 생성
const ToastContext = createContext(null);

// 2. Toast Provider
export const ToastProvider = ({ children }) => {
    const [toasts, setToasts] = useState([]);

    const addToast = useCallback((message, type = 'info', duration = 4000) => {
        const id = Date.now() + Math.random();
        const newToast = { id, message, type };

        setToasts(prev => [...prev, newToast]);

        // 자동 제거
        if (duration > 0) {
            setTimeout(() => {
                setToasts(prev => prev.filter(t => t.id !== id));
            }, duration);
        }

        return id;
    }, []);

    const removeToast = useCallback((id) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    }, []);

    // 편의 함수들
    const toast = {
        success: (msg, duration) => addToast(msg, 'success', duration),
        error: (msg, duration) => addToast(msg, 'error', duration),
        warning: (msg, duration) => addToast(msg, 'warning', duration),
        info: (msg, duration) => addToast(msg, 'info', duration),
    };

    return (
        <ToastContext.Provider value={{ toast, removeToast }}>
            {children}
            <ToastContainer toasts={toasts} onRemove={removeToast} />
        </ToastContext.Provider>
    );
};

// 3. Toast Container (화면 우상단에 표시)
const ToastContainer = ({ toasts, onRemove }) => {
    return (
        <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-3 pointer-events-none">
            {toasts.map((t) => (
                <ToastItem key={t.id} toast={t} onRemove={onRemove} />
            ))}
        </div>
    );
};

// 4. 개별 Toast 아이템
const ToastItem = ({ toast, onRemove }) => {
    const config = {
        success: {
            icon: CheckCircle,
            bg: 'bg-emerald-500/10 border-emerald-500/30',
            iconColor: 'text-emerald-500',
            text: 'text-emerald-400',
            glow: 'shadow-[0_0_20px_rgba(16,185,129,0.2)]'
        },
        error: {
            icon: XCircle,
            bg: 'bg-red-500/10 border-red-500/30',
            iconColor: 'text-red-500',
            text: 'text-red-400',
            glow: 'shadow-[0_0_20px_rgba(239,68,68,0.2)]'
        },
        warning: {
            icon: AlertTriangle,
            bg: 'bg-amber-500/10 border-amber-500/30',
            iconColor: 'text-amber-500',
            text: 'text-amber-400',
            glow: 'shadow-[0_0_20px_rgba(245,158,11,0.2)]'
        },
        info: {
            icon: Info,
            bg: 'bg-blue-500/10 border-blue-500/30',
            iconColor: 'text-blue-500',
            text: 'text-blue-400',
            glow: 'shadow-[0_0_20px_rgba(59,130,246,0.2)]'
        }
    };

    const c = config[toast.type] || config.info;
    const Icon = c.icon;

    return (
        <div
            className={`
        pointer-events-auto flex items-center gap-3 px-4 py-3 
        bg-[#1b1d1f]/95 backdrop-blur-xl border rounded-xl
        ${c.bg} ${c.glow}
        animate-slide-in-right min-w-[300px] max-w-[400px]
      `}
        >
            <Icon size={20} className={c.iconColor} />
            <span className={`flex-1 text-sm font-medium ${c.text}`}>
                {toast.message}
            </span>
            <button
                onClick={() => onRemove(toast.id)}
                className="p-1 hover:bg-white/10 rounded-lg transition-colors text-gray-500 hover:text-white"
            >
                <X size={14} />
            </button>
        </div>
    );
};

// 5. Custom Hook
export const useToast = () => {
    const context = useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
};

export default ToastContext;
