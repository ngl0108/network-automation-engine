
import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import { Server, Wifi, Router, Box, Radio } from 'lucide-react';

const NetworkNode = ({ data, selected }) => {
    // Styles based on Tier/Role
    let bg = '#fff';
    let border = '#9ca3af';
    let Icon = Box;

    if (data.status === 'online') {
        if (data.role === 'core') {
            bg = '#eff6ff'; // Blue-50
            border = '#3b82f6'; // Blue-500
            Icon = Router; // Or Server
        } else if (data.role === 'wlc' || data.role === 'distribution') {
            bg = '#fdf4ff'; // Purple-50
            border = '#d946ef'; // Fuchsia-500
            Icon = Server;
        } else if (data.role === 'access_point') {
            bg = '#f0fdf4'; // Green-50
            border = '#22c55e'; // Green-500
            Icon = Wifi;
        } else {
            bg = '#fff';
            border = '#10b981'; // Green-500 (Access)
            Icon = Box;
        }
    }

    const nodeStyle = {
        background: bg,
        border: `2px solid ${border}`,
        borderRadius: '12px',
        padding: '10px',
        minWidth: '150px',
        boxShadow: selected ? '0 0 0 2px #2563eb' : '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: '12px',
        position: 'relative' // For absolute handles
    };

    return (
        <div style={nodeStyle}>
            {/* 4 Handles for Multi-Directional Connection */}
            <Handle type="target" position={Position.Top} id="top" style={{ top: -5, background: '#555' }} />
            <Handle type="source" position={Position.Top} id="top-s" style={{ top: -5, background: '#555', visibility: 'hidden' }} />

            <Handle type="target" position={Position.Right} id="right" style={{ right: -5, background: '#555' }} />
            <Handle type="source" position={Position.Right} id="right-s" style={{ right: -5, background: '#555', visibility: 'hidden' }} />

            <Handle type="target" position={Position.Bottom} id="bottom" style={{ bottom: -5, background: '#555' }} />
            <Handle type="source" position={Position.Bottom} id="bottom-s" style={{ bottom: -5, background: '#555', visibility: 'hidden' }} />

            <Handle type="target" position={Position.Left} id="left" style={{ left: -5, background: '#555' }} />
            <Handle type="source" position={Position.Left} id="left-s" style={{ left: -5, background: '#555', visibility: 'hidden' }} />

            {/* Content */}
            <div className={`p-2 rounded-full mb-2 ${data.status === 'online' ? 'bg-opacity-20 bg-current' : 'bg-gray-100 text-gray-400'}`} style={{ color: border }}>
                <Icon size={24} />
            </div>
            <div className="font-bold text-sm text-gray-800 text-center">{data.label}</div>
            <div className="text-xs text-gray-500 font-mono text-center">{data.ip}</div>
        </div>
    );
};

export default memo(NetworkNode);
