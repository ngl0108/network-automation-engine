import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext'; // [RBAC] AuthContext
import { Activity, Lock, User, ArrowRight } from 'lucide-react';

const LoginPage = () => {
  const navigate = useNavigate();
  const { login } = useAuth(); // [RBAC] Context의 login 함수 사용
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setIsLoading(true);
    setError('');

    try {
      // [RBAC] AuthContext의 login 함수 호출 (토큰 + 사용자 정보 저장)
      const success = await login(username, password);

      if (success) {
        navigate('/', { replace: true });
      } else {
        throw new Error("Login failed");
      }

    } catch (err) {
      console.error("Login Failed:", err);
      const msg = err.response?.data?.detail || "Invalid credentials or server error.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-[100dvh] bg-[#0e1012] flex flex-col items-center justify-center p-4">
      {/* Background Decoration (Subtle) */}
      <div className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[min(600px,90vw)] h-[min(600px,90vw)] bg-blue-900/10 rounded-full blur-[100px] pointer-events-none"></div>

      {/* Brand Section (Centered above card) */}
      <div className="mb-8 text-center z-10 animate-fade-in-down">
        <div className="flex items-center justify-center gap-4 mb-2">
          <img
            src="/logo_icon_final.png"
            alt="NetSphere"
            className="h-16 w-16 object-contain"
          />
          <h1 className="text-4xl font-bold text-white tracking-tight">
            NetSphere
          </h1>
        </div>
        <p className="text-blue-200/60 text-sm font-medium tracking-widest uppercase">
          Global Network Control
        </p>
      </div>

      {/* Login Form Card */}
      <div className="w-full max-w-sm bg-[#1b1d1f] border border-gray-800/50 rounded-2xl shadow-xl overflow-hidden relative z-10 animate-fade-in-up p-8">

        {/* Removed Header Section inside card */}
        <form onSubmit={handleLogin} className="space-y-5">

          {/* 아이디 입력 */}
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Username</label>
            <div className="relative">
              <User className="absolute left-3 top-2.5 text-gray-500" size={18} />
              <input
                type="text"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                placeholder="Enter username"
              />
            </div>
          </div>

          {/* 비밀번호 입력 */}
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider mb-2">Password</label>
            <div className="relative">
              <Lock className="absolute left-3 top-2.5 text-gray-500" size={18} />
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 bg-[#0e1012] border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all placeholder-gray-600"
                placeholder="Enter password"
              />
            </div>
          </div>

          {/* 에러 메시지 */}
          {error && (
            <div className="text-red-500 text-sm text-center font-medium bg-red-500/10 py-2 rounded-lg border border-red-500/20">
              {error}
            </div>
          )}

          {/* 로그인 버튼 */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-3 rounded-lg transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-blue-900/20 disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
            ) : (
              <>Sign In <ArrowRight size={18} /></>
            )}
          </button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-xs text-gray-500">
            Development Access: <span className="text-gray-300 font-mono">admin / admin123</span>
          </p>
        </div>
      </div> {/* End of Form Content */}
    </div>
  );
};

export default LoginPage;
