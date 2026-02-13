import React, { useState, useEffect } from 'react';
import { SDNService } from '../../api/services';
import { useAuth } from '../../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { useToast } from '../../context/ToastContext';
import {
    Users, Plus, Edit2, Trash2, RefreshCw, Shield,
    Check, X, AlertTriangle
} from 'lucide-react';

const UserManagementPage = () => {
    const { isAdmin, user: currentUser } = useAuth();
    const navigate = useNavigate();
    const { toast } = useToast();

    const [users, setUsers] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingUser, setEditingUser] = useState(null);
    const [formData, setFormData] = useState({
        username: '',
        email: '',
        full_name: '',
        password: '',
        role: 'viewer',
        is_active: true
    });

    // [RBAC] Access Control: Redirect non-admins
    useEffect(() => {
        if (!isAdmin()) {
            toast.error('Access Denied: Administrator privileges required.');
            navigate('/');
        }
    }, [isAdmin, navigate]);

    // Fetch users
    const fetchUsers = async () => {
        setLoading(true);
        try {
            const res = await SDNService.getUsers();
            setUsers(res.data);
        } catch (err) {
            console.error('Failed to fetch users:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchUsers();
    }, []);

    // Open modal for create/edit
    const openModal = (user = null) => {
        if (user) {
            setEditingUser(user);
            setFormData({
                username: user.username,
                email: user.email || '',
                full_name: user.full_name || '',
                password: '', // Don't show password
                role: user.role,
                is_active: user.is_active
            });
        } else {
            setEditingUser(null);
            setFormData({
                username: '',
                email: '',
                full_name: '',
                password: '',
                role: 'viewer',
                is_active: true
            });
        }
        setShowModal(true);
    };

    // Handle form submit
    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            // Clean up empty optional fields to avoid validation errors
            const cleanData = {
                username: formData.username,
                password: formData.password,
                role: formData.role,
                is_active: formData.is_active,
            };
            // Only include optional fields if they have values
            if (formData.email && formData.email.trim()) {
                cleanData.email = formData.email.trim();
            }
            if (formData.full_name && formData.full_name.trim()) {
                cleanData.full_name = formData.full_name.trim();
            }

            if (editingUser) {
                // Update existing user
                const updateData = { ...cleanData };
                if (!updateData.password) delete updateData.password; // Don't update if empty
                delete updateData.username; // Cannot change username
                await SDNService.updateUser(editingUser.id, updateData);
            } else {
                // Create new user
                await SDNService.createUser(cleanData);
            }
            setShowModal(false);
            fetchUsers();
        } catch (err) {
            console.error('Failed to save user:', err);
            // Show more detailed error message
            const detail = err.response?.data?.detail;
            const msg = (typeof detail === 'object')
                ? JSON.stringify(detail, null, 2)
                : (detail || 'Failed to save user');
            toast.error(String(msg).slice(0, 800));
        }
    };

    // Handle delete
    const handleDelete = async (userId, username) => {
        if (username === currentUser?.username) {
            toast.warning('You cannot delete your own account!');
            return;
        }
        if (window.confirm(`Are you sure you want to delete "${username}"?`)) {
            try {
                await SDNService.deleteUser(userId);
                fetchUsers();
            } catch (err) {
                console.error('Failed to delete user:', err);
                toast.error(err.response?.data?.detail || 'Failed to delete user');
            }
        }
    };

    // Role badge color (3-Tier)
    const getRoleBadge = (role) => {
        const colors = {
            admin: 'bg-red-500/20 text-red-400 border-red-500/30',
            operator: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
            viewer: 'bg-gray-500/20 text-gray-600 dark:text-gray-400 border-gray-500/30'
        };
        const labels = {
            admin: 'Administrator',
            operator: 'Operator',
            viewer: 'Viewer'
        };
        return (
            <span className={`px-2 py-1 text-xs font-medium rounded-full border ${colors[role] || colors.viewer}`}>
                {labels[role] || role}
            </span>
        );
    };

    return (
        <div className="h-full overflow-y-auto p-3 sm:p-4 md:p-6 bg-gray-50 dark:bg-[#0e1012]">
            {/* Header */}
            <div className="flex justify-between items-center mb-6">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-600/20 rounded-lg">
                        <Users className="text-blue-400" size={24} />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold text-gray-900 dark:text-white">User Management</h1>
                        <p className="text-sm text-gray-500">Manage user accounts and permissions</p>
                    </div>
                </div>

                <div className="flex gap-3">
                    <button
                        onClick={fetchUsers}
                        className="p-2 rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 transition-colors"
                    >
                        <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                    </button>
                    <button
                        onClick={() => openModal()}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
                    >
                        <Plus size={18} />
                        Add User
                    </button>
                </div>
            </div>

            {/* User Table */}
            <div className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 overflow-hidden shadow-sm">
                <table className="w-full">
                    <thead className="bg-gray-100 dark:bg-[#25282c]">
                        <tr>
                            <th className="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">User</th>
                            <th className="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Role</th>
                            <th className="px-6 py-4 text-left text-xs font-bold text-gray-500 uppercase tracking-wider">Status</th>
                            <th className="px-6 py-4 text-right text-xs font-bold text-gray-500 uppercase tracking-wider">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                        {loading ? (
                            <tr>
                                <td colSpan="4" className="px-6 py-10 text-center text-gray-500">
                                    <RefreshCw className="animate-spin mx-auto mb-2" size={24} />
                                    Loading users...
                                </td>
                            </tr>
                        ) : users.length === 0 ? (
                            <tr>
                                <td colSpan="4" className="px-6 py-10 text-center text-gray-500">
                                    No users found
                                </td>
                            </tr>
                        ) : (
                            users.map((u) => (
                                <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors border-b border-gray-100 dark:border-gray-800/50">
                                    <td className="px-6 py-4">
                                        <div className="flex items-center gap-3">
                                            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-600 to-blue-400 flex items-center justify-center text-white font-bold text-sm">
                                                {(u.full_name || u.username).substring(0, 2).toUpperCase()}
                                            </div>
                                            <div>
                                                <div className="text-sm font-medium text-gray-900 dark:text-white">{u.full_name || u.username}</div>
                                                <div className="text-xs text-gray-600 dark:text-gray-500">{u.email || u.username}</div>
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4">
                                        {getRoleBadge(u.role)}
                                    </td>
                                    <td className="px-6 py-4">
                                        {u.is_active ? (
                                            <span className="flex items-center gap-1 text-green-600 dark:text-green-400 text-sm">
                                                <Check size={14} /> Active
                                            </span>
                                        ) : (
                                            <span className="flex items-center gap-1 text-red-600 dark:text-red-400 text-sm">
                                                <X size={14} /> Inactive
                                            </span>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 text-right">
                                        <button
                                            onClick={() => openModal(u)}
                                            className="p-2 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-500/20 text-gray-500 dark:text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors mr-2"
                                            title="Edit"
                                        >
                                            <Edit2 size={16} />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(u.id, u.username)}
                                            className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-500/20 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                                            title="Delete"
                                            disabled={u.username === currentUser?.username}
                                        >
                                            <Trash2 size={16} />
                                        </button>
                                    </td>
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Modal */}
            {showModal && (
                <div className="fixed inset-0 bg-black/50 dark:bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-[#1b1d1f] rounded-xl border border-gray-200 dark:border-gray-800 p-6 w-full max-w-md shadow-2xl">
                        <h2 className="text-lg font-bold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
                            <Shield className="text-blue-400" size={20} />
                            {editingUser ? 'Edit User' : 'Create New User'}
                        </h2>

                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Username *</label>
                                <input
                                    type="text"
                                    required
                                    value={formData.username}
                                    onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                    disabled={!!editingUser} // Cannot change username
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Full Name</label>
                                <input
                                    type="text"
                                    value={formData.full_name}
                                    onChange={(e) => setFormData({ ...formData, full_name: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Email</label>
                                <input
                                    type="email"
                                    value={formData.email}
                                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">
                                    {editingUser ? 'New Password (leave blank to keep)' : 'Password *'}
                                </label>
                                <input
                                    type="password"
                                    required={!editingUser}
                                    value={formData.password}
                                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Role *</label>
                                <select
                                    value={formData.role}
                                    onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                                    className="w-full px-3 py-2 bg-gray-50 dark:bg-[#0e1012] border border-gray-300 dark:border-gray-700 rounded-lg text-gray-900 dark:text-white focus:border-blue-500 focus:outline-none"
                                >
                                    <option value="viewer">Viewer (Read Only)</option>
                                    <option value="operator">Operator (Manage Devices)</option>
                                    <option value="admin">Administrator (Full Access)</option>
                                </select>
                            </div>

                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="is_active"
                                    checked={formData.is_active}
                                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                                    className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-blue-600 focus:ring-blue-500"
                                />
                                <label htmlFor="is_active" className="text-sm text-gray-600 dark:text-gray-400">Active Account</label>
                            </div>

                            <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-800">
                                <button
                                    type="button"
                                    onClick={() => setShowModal(false)}
                                    className="px-4 py-2 bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-white rounded-lg font-medium transition-colors"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium transition-colors"
                                >
                                    {editingUser ? 'Save Changes' : 'Create User'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default UserManagementPage;
