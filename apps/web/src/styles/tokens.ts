export const tokens = {
  colors: {
    surface0: '#09090b',       // App root background
    surface1: '#18181b',       // Top-level panels: navbar, AiPanel, modal
    surface2: '#1e1e1e',       // Nested panels: Sidebar, Terminal, Editor gutter, dropdowns
    border: '#27272a',         // Standard panel dividers and component borders
    borderStrong: '#3f3f46',   // Active/hover borders, selected rows
    textPrimary: '#e4e4e7',    // Main readable text
    textMuted: '#a1a1aa',      // Secondary text, subheadings, labels
    textDim: '#71717a',        // Disabled, hints, icons
    accent: '#3b82f6',         // Brand interactive blue
    accentSubtle: 'rgba(59, 130, 246, 0.15)', // Selection & active highlights
    success: '#22c55e',        // Successful states, green indicators
    error: '#ef4444',          // Errors, crashes, red badges
  },
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '20px',
    xxl: '24px',
  },
  typography: {
    meta: {
      fontSize: '11px',
      lineHeight: '1.4',
      fontWeight: 500,
    },
    secondary: {
      fontSize: '12px',
      lineHeight: '1.4',
      fontWeight: 400,
    },
    body: {
      fontSize: '13px',
      lineHeight: '1.5',
      fontWeight: 400,
    },
    header: {
      fontSize: '12px',
      lineHeight: '1.4',
      fontWeight: 600,
    },
    mono: {
      fontFamily: "'JetBrains Mono', Menlo, Monaco, Consolas, monospace",
      fontSize: '11px',
      lineHeight: '1.4',
    },
  },
  radii: {
    sm: '4px',
    md: '6px',
    lg: '8px',
  },
  transitions: {
    fast: '100ms ease-out',
    morph: '150ms ease-out',
    expand: '200ms ease-in-out',
  },
} as const;
