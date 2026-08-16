import React from 'react';
import { LucideIcon, Loader2 } from 'lucide-react';
import { tokens } from '../styles/tokens';

interface PanelEmptyStateProps {
  icon: LucideIcon;
  label: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
    icon?: LucideIcon;
  };
  loading?: boolean;
}

export const PanelEmptyState: React.FC<PanelEmptyStateProps> = ({
  icon: Icon,
  label,
  description,
  action,
  loading = false,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        width: '100%',
        padding: tokens.spacing.xl,
        textAlign: 'center',
        userSelect: 'none',
        gap: tokens.spacing.md,
      }}
    >
      <div
        style={{
          width: '36px',
          height: '36px',
          borderRadius: tokens.radii.md,
          backgroundColor: tokens.colors.surface2,
          border: `1px solid ${tokens.colors.border}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: tokens.colors.textDim,
        }}
      >
        {loading ? (
          <Loader2 size={16} className="animate-spin" color={tokens.colors.accent} />
        ) : (
          <Icon size={16} />
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxWidth: '280px' }}>
        <span
          style={{
            fontSize: tokens.typography.header.fontSize,
            fontWeight: 500,
            color: tokens.colors.textPrimary,
          }}
        >
          {label}
        </span>
        {description && (
          <span
            style={{
              fontSize: tokens.typography.meta.fontSize,
              color: tokens.colors.textMuted,
              lineHeight: tokens.typography.meta.lineHeight,
            }}
          >
            {description}
          </span>
        )}
      </div>

      {action && (
        <button
          onClick={action.onClick}
          style={{
            backgroundColor: tokens.colors.accent,
            color: '#ffffff',
            border: 'none',
            borderRadius: tokens.radii.sm,
            padding: `${tokens.spacing.xs} ${tokens.spacing.md}`,
            fontSize: tokens.typography.meta.fontSize,
            fontWeight: 500,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: tokens.spacing.xs,
            transition: `opacity ${tokens.transitions.fast}`,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.opacity = '0.9')}
          onMouseLeave={(e) => (e.currentTarget.style.opacity = '1')}
        >
          {action.icon && <action.icon size={12} />}
          <span>{action.label}</span>
        </button>
      )}
    </div>
  );
};
