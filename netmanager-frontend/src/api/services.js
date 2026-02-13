import axios from 'axios';

// --------------------------------------------------------------------------
// 1. Axios 인스턴스 및 기본 설정
// --------------------------------------------------------------------------
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 요청 인터셉터 (JWT 토큰 자동 포함)
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('authToken');
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 응답 인터셉터 (401 에러 발생 시 로그인 페이지로 리다이렉트)
api.interceptors.response.use(
  (response) => {
    const payload = response?.data;
    if (payload && typeof payload === 'object' && !(payload instanceof Blob)) {
      if (Object.prototype.hasOwnProperty.call(payload, 'success') && Object.prototype.hasOwnProperty.call(payload, 'data')) {
        if (payload.success === true) {
          response.data = payload.data;
        }
      }
    }
    return response;
  },
  (error) => {
    if (error.response && error.response.status === 401) {
      console.warn("Unauthorized access. Redirecting to login...");
      localStorage.removeItem('authToken');
      // 페이지가 이미 /login이 아니라면 리다이렉트
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// --------------------------------------------------------------------------
// 2. AuthService (로그인/인증)
// --------------------------------------------------------------------------
export const AuthService = {
  login: async (username, password) => {
    // 백엔드 엔드포인트에 맞춰 수정 (보통 /auth/login 또는 /token)
    // 예시: OAuth2 Password Request
    const formData = new FormData();
    formData.append('username', username);
    formData.append('password', password);
    return api.post('/auth/login', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  },
  logout: () => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('authUser'); // [FIX] Clear cached user data
  },
  me: () => api.get('/auth/me'), // 현재 사용자 정보
  acceptEula: () => api.post('/auth/me/accept-eula'),
  changePasswordMe: (currentPassword, newPassword) => api.post('/auth/me/change-password', null, { params: { current_password: currentPassword, new_password: newPassword } })
};

export const ObservabilityService = {
  summary: () => api.get('/observability/summary'),
  devices: () => api.get('/observability/devices'),
  deviceTimeseries: (deviceId, minutes = 360, limit = 720) =>
    api.get(`/observability/devices/${deviceId}/timeseries`, { params: { minutes, limit } }),
  deviceInterfaces: (deviceId) => api.get(`/observability/devices/${deviceId}/interfaces`),
  interfaceTimeseries: (deviceId, name, minutes = 360, limit = 720) =>
    api.get(`/observability/devices/${deviceId}/interfaces/timeseries`, { params: { name, minutes, limit } }),
};

// --------------------------------------------------------------------------
// 3. DeviceService (장비 관리 및 SDN 핵심 기능 통합)
// --------------------------------------------------------------------------
export const DeviceService = {
  // --- [Basic] 기존 장비 CRUD ---
  getAll: () => api.get('/devices/'),
  getDevices: () => api.get('/devices/'),
  getDetail: (id) => api.get(`/devices/${id}`),
  create: (data) => api.post('/devices/', data),
  update: (id, data) => api.put(`/devices/${id}`, data),
  delete: (id) => api.delete(`/devices/${id}`),
  syncDevice: (id) => api.post(`/devices/${id}/sync`),
  getInventory: (id) => api.get(`/devices/${id}/inventory`),
  exportInventory: (id, format = 'xlsx') =>
    api.get(`/devices/${id}/inventory/export`, { params: { format }, responseType: 'blob' }),

  // --- [Dashboard] 통계 ---
  getDashboardStats: (siteId) => api.get('/sdn/dashboard/stats', { params: { site_id: siteId } }),
  getAnalytics: (range) => api.get(`/devices/analytics?range=${range}`),
  // getTopology: Moved to SDNService for consistency with PathTrace
  getTopology: (params = {}) => api.get('/devices/topology/links', { params }),
  getEndpointGroupDetails: (deviceId, port, params = {}) => api.get('/devices/topology/endpoint-group', { params: { device_id: deviceId, port, ...params } }),

  // --- [Feature 1] 사이트 관리 (Site Ops) ---
  getSites: () => api.get('/sites/'),
  createSite: (data) => api.post('/sites/', data),
  updateSite: (id, data) => api.put(`/sites/${id}`, data),
  deleteSite: (id) => api.delete(`/sites/${id}`),
  getSiteDevices: (siteId) => api.get(`/sites/${siteId}/devices`),
  assignDevicesToSite: (siteId, deviceIds) => api.post(`/sites/${siteId}/devices`, { device_ids: deviceIds }),

  // --- [Feature 2] 사이트 정책 설계 (Site Policies) ---
  getSiteVlans: (siteId) => api.get(`/sites/${siteId}/vlans`),
  createSiteVlan: (siteId, data) => api.post(`/sites/${siteId}/vlans`, data),

  // --- [Step 1] 스마트 템플릿 (Templates) ---
  getTemplates: () => api.get('/templates/'),
  createTemplate: (data) => api.post('/templates/', data),
  updateTemplate: (id, data) => api.put(`/templates/${id}`, data),
  deleteTemplate: (id) => api.delete(`/templates/${id}`),
  previewTemplate: (data) => api.post('/templates/preview', data),

  // [추가] 템플릿 배포 함수 (ConfigPage에서 사용)
  deployTemplate: (templateId, deviceIds) => api.post(`/templates/${templateId}/deploy`, { device_ids: deviceIds }),
  dryRunTemplate: (templateId, deviceIds, options = {}) =>
    api.post(`/templates/${templateId}/dry-run`, { device_ids: deviceIds, variables: options.variables || {}, include_rendered: !!options.includeRendered }),

  // --- [Step 2] 변수 관리 (Variables) ---
  updateVariables: (targetType, targetId, variables) =>
    api.put(`/vars/${targetType}/${targetId}`, { variables }),

  // --- [Feature 3] 무선 관리 (Wireless Ops) ---
  getWirelessOverview: () => api.get('/devices/wireless/overview'),
};

// --------------------------------------------------------------------------
// 4. LogService & IssueService & SDNService
// --------------------------------------------------------------------------
export const LogService = {
  getRecentLogs: (days) => api.get('/logs/recent', { params: { days } }),
};

export const IssueService = {
  getActiveIssues: (params = {}) => api.get('/sdn/issues/active', { params }),
  getUnreadCount: () => api.get('/sdn/issues/unread-count'),
  markAsRead: (id) => api.put(`/sdn/issues/${id}/read`),
  markAllAsRead: () => api.put('/sdn/issues/read-all'),
  resolveIssue: (id) => api.put(`/sdn/issues/${id}/resolve`),
  resolveAll: () => api.post('/sdn/issues/resolve-all'),
};

export const SDNService = {
  getDevices: () => api.get('/devices'), // [FIX] 장비 목록 조회 추가
  getImages: () => api.get('/sdn/images'),
  uploadImage: (formData) => api.post('/sdn/images', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  deleteImage: (id) => api.delete(`/sdn/images/${id}`),

  // [SWIM] Deployment
  deployImage: (imageId, deviceIds) => api.post(`/sdn/images/${imageId}/deploy`, { device_ids: deviceIds }),
  getUpgradeJobs: () => api.get('/sdn/images/jobs'),

  getPolicies: () => api.get('/sdn/policies'),
  createPolicy: (data) => api.post('/sdn/policies', data),
  updatePolicy: (id, data) => api.put(`/sdn/policies/${id}`, data),
  deletePolicy: (id) => api.delete(`/sdn/policies/${id}`),
  previewPolicy: (id) => api.get(`/sdn/policies/${id}/preview`),
  deployPolicy: (id, deviceIds) => api.post(`/sdn/policies/${id}/deploy`, { device_ids: deviceIds }), // List[int] wrapped in object

  // [PathTrace] Topology
  getTopology: (params = {}) => api.get('/devices/topology/links', { params }),
  tracePath: (srcIp, dstIp) => api.post('/topology/path-trace', { src_ip: srcIp, dst_ip: dstIp }),

  // [Fabric] Automation
  generateFabric: (payload) => api.post('/fabric/generate', payload),

  getAuditLogs: (params) => api.get('/audit', { params }), // [NEW] Audit Logs


  getUsers: () => api.get('/auth/users'), // 사용자 목록
  createUser: (data) => api.post('/auth/users', data),
  updateUser: (id, data) => api.put(`/auth/users/${id}`, data),
  deleteUser: (id) => api.delete(`/auth/users/${id}`),
};

export const DiagnosisService = {
  oneClick: (srcIp, dstIp, includeShowCommands = true) =>
    api.post('/diagnosis/one-click', { src_ip: srcIp, dst_ip: dstIp, include_show_commands: includeShowCommands }),
};

export const VisualConfigService = {
  getBlueprints: () => api.get('/visual/blueprints'),
  createBlueprint: (payload) => api.post('/visual/blueprints', payload),
  getBlueprint: (id) => api.get(`/visual/blueprints/${id}`),
  updateBlueprint: (id, payload) => api.put(`/visual/blueprints/${id}`, payload),
  deleteBlueprint: (id) => api.delete(`/visual/blueprints/${id}`),
  createVersion: (id, payload) => api.post(`/visual/blueprints/${id}/versions`, payload),
  previewBlueprint: (id) => api.post(`/visual/blueprints/${id}/preview`),
  deployBlueprint: (id, payload) => api.post(`/visual/blueprints/${id}/deploy`, payload),
  getDeployJob: (jobId) => api.get(`/visual/deploy-jobs/${jobId}`),
  listDeployJobsForBlueprint: (id, params) => api.get(`/visual/blueprints/${id}/deploy-jobs`, { params }),
  rollbackDeployJob: (jobId, payload) => api.post(`/visual/deploy-jobs/${jobId}/rollback`, payload),
};

export const TrafficService = {
  getTopTalkers: (params = {}) => api.get('/traffic/top-talkers', { params }),
  getTopFlows: (params = {}) => api.get('/traffic/top-flows', { params }),
  getTopApps: (params = {}) => api.get('/traffic/top-apps', { params }),
  getTopAppFlows: (params = {}) => api.get('/traffic/top-app-flows', { params }),
};

export const ComplianceService = {
  getStandards: () => api.get('/compliance/standards'),
  createStandard: (data) => api.post('/compliance/standards', data),
  deleteStandard: (id) => api.delete(`/compliance/standards/${id}`),

  addRule: (stdId, data) => api.post(`/compliance/standards/${stdId}/rules`, data),
  deleteRule: (ruleId) => api.delete(`/compliance/rules/${ruleId}`),

  runScan: (payload) => api.post('/compliance/scan', payload), // { device_ids: [], standard_id: opt }
  getReports: (deviceId) => api.get('/compliance/reports', { params: { device_id: deviceId } }),
  exportReports: (params = {}) => api.get('/compliance/reports/export', { params, responseType: 'blob' }),

  // [NEW] Config Drift
  getBackups: (deviceId) => api.get(`/compliance/drift/backups/${deviceId}`),
  setGolden: (backupId) => api.post(`/compliance/drift/golden/${backupId}`),
  checkDrift: (deviceId) => api.get(`/compliance/drift/check/${deviceId}`),
  remediateDrift: (deviceId, payload = {}) => api.post(`/compliance/drift/remediate/${deviceId}`, payload),
};

export const JobService = {
  getStatus: (taskId) => api.get(`/jobs/${taskId}`),
};

export const DiscoveryService = {
  startScan: (data) => api.post('/discovery/scan', data),
  startNeighborCrawl: (data) => api.post('/discovery/crawl', data),
  getJobStatus: (id) => api.get(`/discovery/jobs/${id}`),
  getJobResults: (id) => api.get(`/discovery/jobs/${id}/results`),
  approveDevice: (id) => api.post(`/discovery/approve/${id}`),
  ignoreDevice: (id) => api.post(`/discovery/ignore/${id}`),
  approveAll: (jobId) => api.post(`/discovery/jobs/${jobId}/approve-all`),
};


// [추가] 설정 관리 서비스
export const SettingsService = {
  getGeneral: () => api.get('/settings/general'),
  updateGeneral: (data) => api.put('/settings/general', data),
  sendTestEmail: (toEmail) => api.post('/settings/test-email', { to_email: toEmail }),
};

// --------------------------------------------------------------------------
// 5. ZtpService (Zero Touch Provisioning)
// --------------------------------------------------------------------------
export const ZtpService = {
  // 대기열 조회
  getQueue: (status = null) => api.get('/ztp/queue', { params: status ? { status } : {} }),
  getStats: () => api.get('/ztp/stats'),

  // 장비 승인
  approveDevice: (itemId, payload) => api.post(`/ztp/queue/${itemId}/approve`, payload),

  // 미리 등록 (RMA)
  stageDevice: (payload) => api.post('/ztp/queue/stage', payload),

  // 삭제
  deleteItem: (itemId) => api.delete(`/ztp/queue/${itemId}`),

  // 재시도
  retryItem: (itemId) => api.post(`/ztp/queue/${itemId}/retry`),
};

// --------------------------------------------------------------------------
// 6. Firmware Image Service (SDN)
// --------------------------------------------------------------------------
export const ImageService = {
  getImages: () => api.get('/sdn/images'),
  uploadImage: (formData) => api.post('/sdn/images', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  }),
  deleteImage: (id) => api.delete(`/sdn/images/${id}`),
};

// --------------------------------------------------------------------------
// 7. Topology Service
// --------------------------------------------------------------------------
export const TopologyService = {
  getLayout: () => api.get('/topology/layout'),
  saveLayout: (layoutData) => api.post('/topology/layout', layoutData),
  resetLayout: () => api.delete('/topology/layout'),
  listSnapshots: (params = {}) => api.get('/topology/snapshots', { params }),
  createSnapshot: (payload) => api.post('/topology/snapshots', payload),
  getSnapshot: (id) => api.get(`/topology/snapshots/${id}`),
  diffSnapshots: (snapshotA, snapshotB) => api.get('/topology/diff', { params: { snapshot_a: snapshotA, snapshot_b: snapshotB } }),
  getCandidates: (params = {}) => api.get('/topology/candidates', { params }),
  getCandidateRecommendations: (candidateId, params = {}) => api.get(`/topology/candidates/${candidateId}/recommendations`, { params }),
  promoteCandidate: (candidateId, payload) => api.post(`/topology/candidates/${candidateId}/promote`, payload),
  ignoreCandidate: (candidateId) => api.post(`/topology/candidates/${candidateId}/ignore`),
  bulkIgnoreCandidates: (candidateIds) => api.post('/topology/candidates/bulk-ignore', { candidate_ids: candidateIds }),
  bulkPromoteCandidates: (jobId, items) => api.post('/topology/candidates/bulk-promote', { job_id: jobId, items }),
};

// --------------------------------------------------------------------------
// 8. Approval Service (Change Management)
// --------------------------------------------------------------------------
export const ApprovalService = {
  create: (data) => api.post('/approval/', data),
  getRequests: (params) => api.get('/approval/', { params }),
  getRequest: (id) => api.get(`/approval/${id}`),
  approve: (id, comment) => api.post(`/approval/${id}/approve`, { approver_comment: comment }),
  reject: (id, comment) => api.post(`/approval/${id}/reject`, { approver_comment: comment }),
};

export default api;
