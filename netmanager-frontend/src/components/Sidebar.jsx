import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import {
  LayoutDashboard,
  Server,
  Settings,
  FileText,
  Share2,
  Shield,
  Layers,
  Scroll,
  Globe,
  Package,
  Users,
  CheckCircle,
  Radar,
  Blocks,
  FileCheck,
  HardDrive,
  Workflow,
  Bell,
  Wifi,
  Activity
} from 'lucide-react';

const Sidebar = ({ className = '', onNavigate }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, isAtLeast } = useAuth();

  // 사이드바 메뉴 목록 정의 (3-Tier RBAC) - 간결하게 재구성
  const menuItems = [
    {
      category: 'OPERATIONS',
      items: [
        { icon: LayoutDashboard, label: 'Dashboard', path: '/', requiredRole: 'viewer' },
        { icon: Share2, label: 'Network Map', path: '/topology', requiredRole: 'viewer' },
        { icon: Server, label: 'Devices', path: '/devices', requiredRole: 'viewer' },
        { icon: Bell, label: 'Notifications', path: '/notifications', requiredRole: 'viewer' },
        { icon: Wifi, label: 'Wireless', path: '/wireless', requiredRole: 'viewer' },
      ]
    },
    {
      category: 'AUTOMATION',
      items: [
        { icon: Radar, label: 'Auto Discovery', path: '/discovery', requiredRole: 'operator' },
        { icon: Workflow, label: 'Automation Hub', path: '/automation', requiredRole: 'operator' },
      ]
    },
    {
      category: 'SYSTEM',
      items: [
        { icon: Scroll, label: 'System Logs', path: '/logs', requiredRole: 'viewer' },
        { icon: Shield, label: 'Audit Trail', path: '/audit', requiredRole: 'operator' },
        { icon: Activity, label: 'Observability', path: '/observability', requiredRole: 'operator' },
        { icon: Users, label: 'Users', path: '/users', requiredRole: 'admin' },
        { icon: Settings, label: 'Settings', path: '/settings', requiredRole: 'admin' },
      ]
    }
  ];

  // [RBAC] Filter menu items based on user role
  const getFilteredMenu = () => {
    return menuItems.map(section => ({
      ...section,
      items: section.items.filter(item => isAtLeast(item.requiredRole))
    })).filter(section => section.items.length > 0);
  };

  const filteredMenu = getFilteredMenu();

  const getInitials = (name) => {
    if (!name) return 'U';
    const parts = name.split(' ');
    if (parts.length >= 2) {
      return parts[0][0] + parts[1][0];
    }
    return name.substring(0, 2).toUpperCase();
  };

  const getRoleDisplay = (role) => {
    const roleMap = {
      admin: 'Administrator',
      operator: 'Operator',
      viewer: 'Viewer'
    };
    return roleMap[role] || role;
  };

  return (
    <div className={`w-64 h-[100dvh] bg-white dark:bg-surface/50 backdrop-blur-md border-r border-gray-200 dark:border-white/10 flex flex-col flex-shrink-0 transition-all duration-300 relative z-50 shadow-2xl ${className}`}>
      {/* Glow Effect */}
      <div className="absolute -top-20 -left-20 w-40 h-40 bg-primary-glow/20 rounded-full blur-3xl pointer-events-none"></div>

      {/* Logo Area */}
      <div className="h-16 flex items-center gap-3 px-6 border-b border-gray-200 dark:border-white/5 bg-gray-50/50 dark:bg-black/20">
        <img src="/logo_icon_final.png" alt="NetSphere" className="w-8 h-8 object-contain" />
        <span className="text-lg font-bold bg-gradient-to-r from-blue-400 to-cyan-300 bg-clip-text text-transparent">
          NetSphere
        </span>
      </div>

      {/* 메뉴 리스트 영역 */}
      <div className="flex-1 overflow-y-auto py-6 px-3 custom-scrollbar space-y-8">
        {filteredMenu.map((section, idx) => (
          <div key={idx} className="animate-fade-in" style={{ animationDelay: `${idx * 100}ms` }}>
            <h3 className="px-4 text-[10px] font-extrabold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-3 flex items-center gap-2">
              <span className="w-1 h-1 rounded-full bg-gray-300 dark:bg-secondary/50"></span>
              {section.category}
            </h3>
            <div className="space-y-1">
              {section.items.map((item) => {
                const isActive = location.pathname === item.path;
                return (
                  <button
                    key={item.path}
                    onClick={() => {
                      navigate(item.path);
                      if (onNavigate) onNavigate(item.path);
                    }}
                    className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-300 group relative overflow-hidden
                      ${isActive
                        ? 'text-white bg-blue-600 dark:text-blue-400 dark:bg-blue-600/20 shadow-[0_0_15px_rgba(59,130,246,0.15)] border border-blue-500/30 dark:border-blue-500/30'
                        : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-white/5 hover:text-gray-900 dark:hover:text-white border border-transparent'
                      }`}
                  >
                    {isActive && (
                      <div className="absolute inset-y-0 left-0 w-1 bg-primary rounded-full shadow-[0_0_10px_#3b82f6]"></div>
                    )}

                    <item.icon
                      size={18}
                      className={`transition-all duration-300 ${isActive ? 'text-white dark:text-blue-400 scale-110' : 'text-gray-500 dark:text-gray-500 group-hover:text-gray-700 dark:group-hover:text-gray-300'}`}
                    />
                    <span className="relative z-10">{item.label}</span>

                    {/* Hover Glow */}
                    <div className="absolute inset-0 bg-gradient-to-r from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"></div>
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* 하단 프로필 영역 */}
      <div className="p-4 border-t border-gray-200 dark:border-white/5 bg-gray-50/50 dark:bg-black/20 backdrop-blur-lg">
        <div className="flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-gray-200 dark:hover:bg-white/5 cursor-pointer transition-colors group border border-transparent hover:border-gray-300 dark:hover:border-white/5">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 p-[1px] shadow-lg">
            <div className="w-full h-full rounded-full bg-surface-900 flex items-center justify-center text-xs font-bold text-white back">
              {getInitials(user?.full_name || user?.username)}
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold text-gray-800 dark:text-white truncate group-hover:text-blue-600 dark:group-hover:text-primary-glow transition-colors">
              {user?.full_name || user?.username || 'User'}
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <div className={`w-1.5 h-1.5 rounded-full ${user?.role === 'admin' ? 'bg-danger shadow-neon-danger' : 'bg-success shadow-neon-success'}`}></div>
              <div className="text-[10px] text-gray-500 dark:text-gray-400 font-medium truncate uppercase tracking-wide">
                {getRoleDisplay(user?.role)}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Sidebar;
