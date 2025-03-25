import React, { useState, useCallback } from 'react';
import { theme } from 'antd';

const ResizableLayout = ({ children }) => {
  const { token } = theme.useToken();
  const [dragging, setDragging] = useState(null);
  const [widths, setWidths] = useState({
    left: 25,
    middle: 35,
    right: 40
  });

  const handleMouseDown = (e, divider) => {
    e.preventDefault();
    setDragging({
      divider,
      startX: e.clientX,
      initialWidths: { ...widths }
    });
  };

  const handleMouseMove = useCallback((e) => {
    if (!dragging) return;

    const deltaX = e.clientX - dragging.startX;
    const containerWidth = window.innerWidth;
    const percentageDelta = (deltaX / containerWidth) * 100;

    if (dragging.divider === 'left') {
      const newLeftWidth = Math.min(Math.max(dragging.initialWidths.left + percentageDelta, 15), 40);
      const widthDifference = newLeftWidth - dragging.initialWidths.left;
      setWidths({
        left: newLeftWidth,
        middle: dragging.initialWidths.middle - widthDifference,
        right: dragging.initialWidths.right
      });
    } else {
      const middleWidth = Math.min(Math.max(dragging.initialWidths.middle + percentageDelta, 20), 50);
      const rightWidth = 100 - widths.left - middleWidth;
      setWidths({
        left: widths.left,
        middle: middleWidth,
        right: rightWidth
      });
    }
  }, [dragging, widths]);

  const handleMouseUp = useCallback(() => {
    setDragging(null);
  }, []);

  React.useEffect(() => {
    if (dragging) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [dragging, handleMouseMove, handleMouseUp]);

  const dividerStyle = {
    width: '4px',
    background: token.colorBorderSecondary,
    cursor: 'col-resize',
    transition: `background-color ${token.motionDurationMid}`,
    '&:hover': {
      background: token.colorPrimary,
    }
  };

  const containerStyle = {
    display: 'flex',
    height: '100%',
    width: '100%',
  };

  const panelStyle = {
    height: '100%',
    minWidth: 0,
  };

  return (
    <div style={containerStyle}>
      {/* Sources Panel */}
      <div style={{ ...panelStyle, width: `${widths.left}%`, minWidth: '15%' }}>
        {children[0]}
      </div>

      {/* Left Divider */}
      <div
        style={{
          ...dividerStyle,
          backgroundColor: dragging?.divider === 'left' ? token.colorPrimary : token.colorBorderSecondary,
          '&:hover': {
            backgroundColor: token.colorPrimary,
          }
        }}
        onMouseDown={(e) => handleMouseDown(e, 'left')}
      />

      {/* Chat Panel */}
      <div style={{ ...panelStyle, width: `${widths.middle}%`, minWidth: '20%' }}>
        {children[1]}
      </div>

      {/* Right Divider */}
      <div
        style={{
          ...dividerStyle,
          backgroundColor: dragging?.divider === 'right' ? token.colorPrimary : token.colorBorderSecondary,
          '&:hover': {
            backgroundColor: token.colorPrimary,
          }
        }}
        onMouseDown={(e) => handleMouseDown(e, 'right')}
      />

      {/* Notes Panel */}
      <div style={{ ...panelStyle, width: `${widths.right}%`, minWidth: '25%' }}>
        {children[2]}
      </div>

      {/* Overlay when dragging */}
      {dragging && (
        <div style={{
          position: 'fixed',
          inset: 0,
          zIndex: token.zIndexPopupBase,
          cursor: 'col-resize',
        }} />
      )}
    </div>
  );
};

export default ResizableLayout;