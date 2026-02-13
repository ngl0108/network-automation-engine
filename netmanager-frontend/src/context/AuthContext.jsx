import React, { createContext, useState, useContext, useEffect } from 'react';
import { AuthService } from '../api/services';

// 1. Context 생성
const AuthContext = createContext(null);

// 2. 3-Tier 권한 계층 정의 (간소화)
// Admin (0) > Operator (1) > Viewer (2)
const ROLE_HIERARCHY = {
    admin: 0,
    operator: 1,
    viewer: 2,
};

// 3. AuthProvider 컴포넌트
export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    // 로그인: 서버 응답에서 사용자 정보 저장
    const login = async (username, password) => {
        const res = await AuthService.login(username, password);
        const token =
            res?.data?.access_token ||
            res?.data?.token ||
            res?.data?.data?.access_token ||
            res?.data?.data?.token;

        if (token) {
            localStorage.setItem('authToken', token);

            // /auth/me 호출하여 상세 사용자 정보 가져오기
            try {
                const meRes = await AuthService.me();
                const userData = meRes?.data?.data || meRes?.data;
                setUser(userData);
                localStorage.setItem('authUser', JSON.stringify(userData));
            } catch (e) {
                // Fallback: Basic User from username
                const fallbackUser = { username, role: 'viewer' };
                setUser(fallbackUser);
                localStorage.setItem('authUser', JSON.stringify(fallbackUser));
            }

            return true;
        }
        return false;
    };

    // 로그아웃
    const logout = () => {
        setUser(null);
        localStorage.removeItem('authToken');
        localStorage.removeItem('authUser');
    };

    // 사용자 정보 최신화 함수 (외부 노출)
    const refreshUser = async () => {
        try {
            const res = await AuthService.me();
            const userData = res?.data?.data || res?.data;
            setUser(userData);
            localStorage.setItem('authUser', JSON.stringify(userData));
            return userData;
        } catch (e) {
            // 토큰 만료 시 로그아웃 처리
            if (e.response && e.response.status === 401) {
                logout();
            }
            throw e;
        }
    };

    // 앱 시작 시 저장된 사용자 정보 로드 + 서버 최신 동기화
    useEffect(() => {
        const loadUser = async () => {
            const token = localStorage.getItem('authToken');

            if (token) {
                // 1. 로컬 데이터 로드 및 유효성 검사 (스키마 확인)
                const storedUser = localStorage.getItem('authUser');
                if (storedUser) {
                    const parsed = JSON.parse(storedUser);
                    // [Security] 데이터가 구형이거나 손상되었으면 초기화
                    if (parsed.eula_accepted === undefined) {
                        console.warn("Stale user data detected. Force logout.");
                        logout();
                        setLoading(false);
                        return;
                    }
                    setUser(parsed);
                }

                // 2. 백그라운드에서 최신 정보 가져와서 갱신 (핵심!)
                try {
                    await refreshUser();
                } catch (e) {
                    console.error("Session expired or invalid:", e);
                }
            }
            setLoading(false);
        };
        loadUser();
    }, []);

    /**
     * 현재 사용자가 필요한 권한 레벨 이상인지 확인.
     * @param {string} minRole - 최소 필요 역할 (admin, operator, viewer)
     * @returns {boolean}
     */
    const isAtLeast = (minRole) => {
        if (!user || !user.role) return false;
        const userLevel = ROLE_HIERARCHY[user.role] ?? 999;
        const requiredLevel = ROLE_HIERARCHY[minRole] ?? 999;
        return userLevel <= requiredLevel;
    };

    // Context Value (3-Tier 전용 함수들)
    const value = {
        user,
        loading,
        login,
        logout,
        refreshUser, // [New] 외부에서 강제 갱신 가능
        isAtLeast,
        // 3-Tier 헬퍼 함수
        isAdmin: () => isAtLeast('admin'),       // Admin만
        isOperator: () => isAtLeast('operator'), // Admin + Operator
        isViewer: () => isAtLeast('viewer'),     // 모든 인증 사용자
    };

    return (
        <AuthContext.Provider value={value}>
            {!loading && children}
        </AuthContext.Provider>
    );
};

// 4. Custom Hook for easy access
export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};

export default AuthContext;
