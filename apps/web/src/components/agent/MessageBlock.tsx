import React, { useEffect, useState } from 'react';

export const MessageBlock: React.FC<{ content: string; isStreaming?: boolean }> = ({ content, isStreaming }) => {
  const [visibleContent, setVisibleContent] = useState('');

  useEffect(() => {
    if (isStreaming) {
      // In a real implementation we would stagger chunks. 
      // For now, we update immediately but rely on CSS transition for opacity.
      setVisibleContent(content);
    } else {
      setVisibleContent(content);
    }
  }, [content, isStreaming]);

  if (!content) return null;

  return (
    <div className="pl-[12px] border-l-2 border-border-subtle py-1">
      <div 
        className={`text-base leading-[1.6] text-text-primary ${isStreaming ? 'transition-opacity duration-180 ease-out' : ''}`}
        style={{ opacity: visibleContent ? 1 : 0 }}
      >
        {visibleContent.split('\n').map((line, i) => (
          <React.Fragment key={i}>
            {line}
            {i !== visibleContent.split('\n').length - 1 && <br />}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
};
