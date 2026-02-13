import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Layout from './components/Layout';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { ThemeProvider } from './context/ThemeContext';
import FirstRunWizard from './components/auth/FirstRunWizard';

// 기존 페이지들
import DashboardPage from './components/dashboard/DashboardPage';
import DeviceListPage from './components/devices/DeviceListPage';
import ConfigPage from './components/config/ConfigPage';
import LogsPage from './components/logs/LogsPage';
import TopologyPage from './components/topology/TopologyPage';
import DeviceDetailPage from './pages/DeviceDetailPage';
import LoginPage from './pages/LoginPage';
import ObservabilityPage from './pages/ObservabilityPage';
import AutomationHubPage from './pages/AutomationHubPage';

// [신규] 운영 및 설정 페이지들
import ImagePage from './components/images/ImagePage';
import PolicyPage from './components/policy/PolicyPage';
import SettingsPage from './components/settings/SettingsPage';
import NotificationsPage from './components/notifications/NotificationsPage';
import AuditPage from './components/audit/AuditPage';
import CompliancePage from './components/compliance/CompliancePage';
import DiscoveryPage from './components/discovery/DiscoveryPage'; // [NEW] Discovery
import ApprovalPage from './components/approval/ApprovalPage'; // [NEW] Approval

// [추가] 사이트 관리 페이지 (경로: src/pages/SiteListPage.jsx)
import SiteListPage from './pages/SiteListPage';
import WirelessPage from './pages/WirelessPage';

// [NEW] ZTP (Zero Touch Provisioning)
import ZtpPage from './components/ztp/ZtpPage';
import FabricPage from './components/fabric/FabricPage'; // [NEW] Fabric Automation
import VisualConfigPage from './components/visual-config/VisualConfigPage';

// [RBAC] User Management
import UserManagementPage from './components/users/UserManagementPage';

// [보안 가드] 로그인 토큰 체크
const ProtectedRoute = ({ children }) => {
  const { user, loading } = useAuth();
  const token = localStorage.getItem('authToken');
  const location = useLocation();

  if (!token) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // [Security] First Run Wizard Check
  if (!loading && user) {
    if (!user.eula_accepted || user.must_change_password) {
      return <FirstRunWizard />;
    }
  }

  return children;
};

function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              {/* 1. 공개 라우트 */}
              <Route path="/login" element={<LoginPage />} />

              {/* 2. 보호된 라우트 */}
              <Route
                path="/*"
                element={
                  <ProtectedRoute>
                    <Layout>
                      <Routes>
                        {/* 메인 대시보드 */}
                        <Route path="/" element={<DashboardPage />} />

                        {/* 장비 관련 */}
                        <Route path="/devices" element={<DeviceListPage />} />
                        <Route path="/devices/:id" element={<DeviceDetailPage />} />

                        {/* [추가] 사이트 관리 (Site Management) */}
                        <Route path="/sites" element={<SiteListPage />} />

                        {/* 네트워크 맵 */}
                        <Route path="/topology" element={<TopologyPage />} />

                        {/* 설정 및 운영 */}
                        <Route path="/config" element={<ConfigPage />} />
                        <Route path="/images" element={<ImagePage />} />
                        <Route path="/visual-config" element={<VisualConfigPage />} />
                        <Route path="/policy" element={<PolicyPage />} />
                        <Route path="/ztp" element={<ZtpPage />} />
                        <Route path="/fabric" element={<FabricPage />} />
                        <Route path="/compliance" element={<CompliancePage />} />
                        <Route path="/discovery" element={<DiscoveryPage />} />

                        {/* 모니터링 및 로그 */}
                        <Route path="/logs" element={<LogsPage />} />
                        <Route path="/audit" element={<AuditPage />} />
                        <Route path="/wireless" element={<WirelessPage />} />
                        <Route path="/notifications" element={<NotificationsPage />} />

                        {/* 시스템 설정 */}
                        <Route path="/settings" element={<SettingsPage />} />

                        {/* [RBAC] 사용자 관리 (Admin Only) */}
                        <Route path="/users" element={<UserManagementPage />} />

                        {/* [Approval] Change Management */}
                        <Route path="/approval" element={<ApprovalPage />} />

                        <Route path="/observability" element={<ObservabilityPage />} />
                        <Route path="/automation" element={<AutomationHubPage />} />
                      </Routes>
                    </Layout>
                  </ProtectedRoute>
                }
              />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}

export default App;
