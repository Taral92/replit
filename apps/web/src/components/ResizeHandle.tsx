import React, { useState } from 'react';
import { PanelResizeHandle } from 'react-resizable-panels';
import { GripVertical, GripHorizontal } from 'lucide-react';

interface ResizeHandleProps {
  direction?: 'horizontal' | 'vertical';
}

export const ResizeHandle: React.FC<ResizeHandleProps> = ({ direction = 'horizontal' }) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const isVertical = direction === 'vertical';

  return (
    <PanelResizeHandle
      onDragging={setIsDragging}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        width: isVertical ? '100%' : '10px',
        height: isVertical ? '10px' : '100%',
        margin: isVertical ? '-5px 0' : '0 -5px',
        zIndex: 20,
        backgroundColor: 'transparent',
        cursor: isVertical ? 'row-resize' : 'col-resize',
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        position: 'relative'
      }}
    >
      <div 
        style={{
          width: isVertical ? '100%' : '2px',
          height: isVertical ? '2px' : '100%',
          backgroundColor: isDragging ? '#3b82f6' : isHovered ? '#60a5fa' : '#27272a',
          boxShadow: isDragging || isHovered ? '0 0 8px rgba(59, 130, 246, 0.6)' : 'none',
          transition: 'all 0.15s ease',
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}
      >
        {isHovered && (
          <div style={{
            position: 'absolute',
            backgroundColor: '#3b82f6',
            borderRadius: '4px',
            padding: '2px',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 0 6px rgba(0,0,0,0.5)'
          }}>
            {isVertical ? <GripHorizontal size={10} /> : <GripVertical size={10} />}
          </div>
        )}
      </div>
    </PanelResizeHandle>
  );
};
