import React, { memo } from 'react';
import { Handle, Position, NodeResizer } from 'reactflow';

const GroupNode = ({ data, selected, style }) => {
    return (
        <>
            <NodeResizer
                isVisible={selected}
                minWidth={100}
                minHeight={100}
                lineStyle={{ border: '1px solid #94a3b8' }}
                handleStyle={{ width: 8, height: 8, borderRadius: '50%' }}
            />

            {/* Container Style is applied via the node style prop from parent, 
          but we can enforce some internals here if needed */}
            <div style={{ width: '100%', height: '100%', position: 'relative' }}>

                {/* Label Area */}
                <div style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    display: 'flex',
                    justifyContent: 'center',
                    paddingTop: '10px',
                    fontWeight: 'bold',
                    color: '#64748b',
                    fontSize: '16px', // Slightly larger font
                    pointerEvents: 'none', // Label shouldn't block clicks
                }}>
                    {data.label}
                </div>

                {/* The border/bg is handled by the main Node style, 
            so this component is mostly for the Resizer and Label structure */}
            </div>
        </>
    );
};

export default memo(GroupNode);
