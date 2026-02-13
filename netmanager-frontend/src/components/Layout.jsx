import React, { useState, useEffect, useRef } from 'react';
import Sidebar from './Sidebar';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import { IssueService } from '../api/services';
import {
  Bell, Search, LogOut, Sun, Moon,
  AlertTriangle, XCircle, CheckCircle, Clock, ChevronRight, X, Menu
} from 'lucide-react';

const Layout = ({ children }) => {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Notification State
  const [unreadCount, setUnreadCount] = useState(0);
  const [recentAlerts, setRecentAlerts] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef(null);

  // Fetch unread count and recent alerts
  const fetchNotifications = async () => {
    try {
      const [countRes, alertsRes] = await Promise.all([
        IssueService.getUnreadCount(),
        IssueService.getActiveIssues({ is_read: false })
      ]);
      setUnreadCount(countRes.data.unread_count || 0);
      // Take only recent 5 for dropdown preview
      setRecentAlerts((Array.isArray(alertsRes.data) ? alertsRes.data : []).slice(0, 5));
    } catch (err) {
      console.error("Failed to fetch notifications:", err);
    }
  };

  // Poll every 30 seconds
  useEffect(() => {
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 10000); // 10초 간격 (실시간 관제용)
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    setSidebarOpen(false);
    setShowDropdown(false);
  }, [location.pathname]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (!sidebarOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [sidebarOpen]);

  // Mark single alert as read
  const handleMarkRead = async (id, e) => {
    e.stopPropagation();
    try {
      await IssueService.markAsRead(id);
      fetchNotifications();
    } catch (err) {
      console.error("Failed to mark as read:", err);
    }
  };

  // Format time ago
  const formatTimeAgo = (dateString) => {
    if (!dateString) return '';
    const now = new Date();
    const past = new Date(new Date(dateString).getTime() + 9 * 60 * 60 * 1000); // KST adjustment
    const diffMins = Math.floor((now - past) / 60000);
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return `${Math.floor(diffMins / 1440)}d ago`;
  };

  const getPageTitle = (path) => {
    if (path === '/') return 'Global Dashboard';
    if (path === '/topology') return 'Network Topology Map';
    if (path === '/devices') return 'Device Inventory';
    if (path.startsWith('/devices/')) return 'Device 360 Analysis';
    if (path === '/config') return 'Configuration Management';
    if (path === '/images') return 'Image Repository';
    if (path === '/policy') return 'Security Policy';
    if (path === '/ztp') return 'Zero Touch Provisioning';
    if (path === '/logs') return 'System Logs & Events';
    if (path === '/audit') return 'Audit Logs';
    if (path === '/notifications') return 'Active Alarms Center';
    if (path === '/settings') return 'System Settings';
    if (path === '/users') return 'User Management';
    if (path === '/sites') return 'Site Management';
    if (path === '/fabric') return 'Fabric Automation';
    if (path === '/compliance') return 'Security Compliance Audit';
    if (path === '/approval') return 'Change Approval Center';
    if (path === '/observability') return 'Observability';
    if (path === '/automation') return 'Automation Hub';
    return 'NetManager';
  };

  const pageTitle = getPageTitle(location.pathname);

  const handleLogout = () => {
    if (window.confirm('Are you sure you want to logout?')) {
      logout();
      navigate('/login');
    }
  };

  return (
    <div className={`flex min-h-[100dvh] h-[100dvh] w-full overflow-hidden font-sans transition-colors duration-300 ${isDark ? 'text-white bg-[#0f172a]' : 'text-gray-900 bg-slate-100'}`}>

      {/* Sidebar (Desktop) */}
      <div className="hidden lg:block">
        <Sidebar />
      </div>

      {/* Sidebar (Mobile Drawer) */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-[2px]"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-64">
            <div className="relative h-full">
              <button
                onClick={() => setSidebarOpen(false)}
                className="absolute top-3 right-3 z-[60] h-10 w-10 flex items-center justify-center rounded-xl bg-white/80 text-gray-700 shadow-sm hover:bg-white focus:outline-none dark:bg-black/40 dark:text-gray-200 dark:hover:bg-black/60 border border-gray-200 dark:border-white/10"
                aria-label="Close sidebar"
              >
                <X size={18} />
              </button>
              <Sidebar
                className="shadow-2xl"
                onNavigate={() => setSidebarOpen(false)}
              />
            </div>
          </div>
        </div>
      )}

      {/* Main Area */}
      <div className="flex-1 flex flex-col min-w-0 relative">

        {/* Header */}
        <header className="h-16 flex-shrink-0 z-20 px-3 sm:px-4 md:px-6 py-3">
          <div className="h-full bg-white/90 dark:bg-[#1b1d1f]/90 backdrop-blur-md border border-gray-200 dark:border-white/5 rounded-2xl flex items-center justify-between px-3 sm:px-4 md:px-6 shadow-sm">

            {/* Page Title */}
            <div className="flex items-center gap-4">
              <button
                onClick={() => setSidebarOpen(true)}
                className="lg:hidden h-10 w-10 flex items-center justify-center rounded-xl hover:bg-gray-100 dark:hover:bg-white/10 text-gray-600 dark:text-gray-300 border border-transparent hover:border-gray-200 dark:hover:border-white/5"
                aria-label="Open sidebar"
              >
                <Menu size={20} />
              </button>
              <h2 className="text-lg font-bold text-gray-800 dark:text-white tracking-tight flex items-center gap-2">
                <span className="w-1.5 h-6 bg-primary rounded-full shadow-sm"></span>
                {pageTitle}
              </h2>
            </div>
            {/* ... Right Icons (unchanged) ... */}
            <div className="flex items-center gap-5">
              {/* Search */}
              <div className="relative hidden md:block group">
                <Search className="absolute left-3 top-2.5 text-gray-400 group-hover:text-primary transition-colors" size={16} />
                <input
                  type="text"
                  placeholder="Global Search (Ctrl+K)"
                  className="bg-gray-50 dark:bg-black/20 border border-gray-200 dark:border-white/5 text-sm rounded-xl pl-9 pr-4 py-1.5 focus:outline-none focus:border-primary/50 text-gray-800 dark:text-gray-300 w-64 transition-all focus:bg-white dark:focus:bg-black/40 focus:ring-2 focus:ring-primary/20"
                />
              </div>

              {/* Theme Toggle */}
              <button
                onClick={toggleTheme}
                className="h-10 w-10 flex items-center justify-center rounded-xl hover:bg-gray-100 dark:hover:bg-white/10 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-all border border-transparent hover:border-gray-200 dark:hover:border-white/5"
                title={isDark ? "Light Mode" : "Dark Mode"}
              >
                {isDark ? <Sun size={20} /> : <Moon size={20} />}
              </button>

              {/* Notification Bell with Dropdown */}
              <div className="relative" ref={dropdownRef}>
                <button
                  onClick={() => setShowDropdown(!showDropdown)}
                  className="relative h-10 w-10 flex items-center justify-center rounded-xl hover:bg-gray-100 dark:hover:bg-white/10 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-all group border border-transparent hover:border-gray-200 dark:hover:border-white/5"
                >
                  <Bell size={20} className="group-hover:text-yellow-500 transition-colors" />
                  {unreadCount > 0 && (
                    <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center px-1 text-[10px] font-bold text-white bg-red-500 rounded-full border-2 border-white dark:border-[#1b1d1f] animate-pulse shadow-sm">
                      {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                  )}
                </button>

                {/* Dropdown */}
                {showDropdown && (
                  <div className="absolute right-0 top-12 w-[calc(100vw-1.5rem)] max-w-sm sm:max-w-md bg-white dark:bg-[#1b1d1f] border border-gray-200 dark:border-gray-700 rounded-2xl shadow-xl z-50 overflow-hidden animate-scale-in origin-top-right ring-1 ring-black/5">
                    {/* Header */}
                    <div className="flex justify-between items-center px-4 py-3 border-b border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-[#25282c]">
                      <h3 className="font-bold text-gray-800 dark:text-white text-sm flex items-center gap-2">
                        <Bell size={16} className="text-yellow-500" />
                        Notifications
                        {unreadCount > 0 && <span className="px-1.5 py-0.5 rounded-full bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 text-[10px]">{unreadCount} new</span>}
                      </h3>
                      <button
                        onClick={() => setShowDropdown(false)}
                        className="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
                      >
                        <X size={14} />
                      </button>
                    </div>

                    {/* Alert List */}
                    <div className="max-h-[24rem] overflow-y-auto custom-scrollbar bg-white dark:bg-[#1b1d1f]">
                      {recentAlerts.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
                          <CheckCircle size={40} className="text-gray-200 dark:text-gray-700 mb-3" />
                          <p className="text-sm font-medium">No unread notifications</p>
                          <p className="text-xs text-gray-400 mt-1">You're all caught up!</p>
                        </div>
                      ) : (
                        recentAlerts.map(alert => (
                          <div
                            key={alert.id}
                            onClick={() => { setShowDropdown(false); navigate('/notifications'); }}
                            className={`flex items-start gap-3 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800/50 cursor-pointer border-b border-gray-50 dark:border-gray-800/50 transition-colors ${!alert.is_read ? 'bg-blue-50/60 dark:bg-blue-900/10' : ''}`}
                          >
                            <div className={`mt-0.5 p-1.5 rounded-lg shrink-0 ${alert.severity === 'critical' ? 'bg-red-100 text-red-600 dark:bg-red-500/20 dark:text-red-400' : 'bg-orange-100 text-orange-600 dark:bg-orange-500/20 dark:text-orange-400'}`}>
                              {alert.severity === 'critical' ? <XCircle size={14} /> : <AlertTriangle size={14} />}
                            </div>
                            <div className="flex-1 min-w-0 space-y-0.5">
                              <div className="flex justify-between items-start gap-2">
                                <p className={`text-sm font-semibold truncate ${alert.severity === 'critical' ? 'text-gray-900 dark:text-gray-100' : 'text-gray-900 dark:text-gray-100'}`}>
                                  {alert.title}
                                </p>
                                <span className="text-[10px] text-gray-400 flex items-center gap-1 whitespace-nowrap pt-0.5">
                                  {formatTimeAgo(alert.created_at)}
                                </span>
                              </div>
                              <p className="text-xs text-gray-500 dark:text-gray-400 truncate pr-4">{alert.device} • {alert.description || 'No description'}</p>
                            </div>
                            {!alert.is_read && (
                              <button
                                onClick={(e) => handleMarkRead(alert.id, e)}
                                className="mt-1 p-1 hover:bg-green-100 dark:hover:bg-green-900/30 rounded text-green-600 dark:text-green-400 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                                title="Mark as read"
                              >
                                <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div>
                              </button>
                            )}
                          </div>
                        ))
                      )}
                    </div>

                    {/* Footer */}
                    <button
                      onClick={() => { setShowDropdown(false); navigate('/notifications'); }}
                      className="w-full flex items-center justify-center gap-2 px-4 py-3 text-xs font-bold text-gray-600 dark:text-gray-400 hover:text-primary dark:hover:text-primary hover:bg-gray-50 dark:hover:bg-[#25282c] border-t border-gray-100 dark:border-gray-800 transition-colors uppercase tracking-wide"
                    >
                      View All Activity <ChevronRight size={14} />
                    </button>
                  </div>
                )}
              </div>

              {/* Divider */}
              <div className="h-6 w-px bg-gray-200 dark:bg-white/10 mx-1"></div>

              {/* Logout */}
              <button
                onClick={handleLogout}
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl text-gray-500 dark:text-gray-400 hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 dark:hover:text-red-400 hover:border-red-200 dark:hover:border-red-900/30 border border-transparent transition-all"
                title="Logout"
              >
                <LogOut size={18} />
                <span className="text-xs font-bold hidden md:inline">Logout</span>
              </button>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <main className="flex-1 overflow-hidden relative p-3 sm:p-4 md:p-6 pt-2">
          {/* Removed bg-white/50 and border to make content stand out purely against the slate-100 background */}
          <div className="w-full h-full overflow-y-auto custom-scrollbar rounded-2xl p-1">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
};

export default Layout;
