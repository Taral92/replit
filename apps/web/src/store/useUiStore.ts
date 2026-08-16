import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UiState {
  showSidebar: boolean;
  showTerminal: boolean;
  showPreview: boolean;
  showAgentPanel: boolean;
  
  // Panel sizes (percentages)
  sidebarSize: number;
  terminalSize: number;
  agentPanelSize: number;
  previewSize: number;

  toggleSidebar: () => void;
  toggleTerminal: () => void;
  togglePreview: () => void;
  toggleAgentPanel: () => void;
  
  setSidebarSize: (size: number) => void;
  setTerminalSize: (size: number) => void;
  setAgentPanelSize: (size: number) => void;
  setPreviewSize: (size: number) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      showSidebar: true,
      showTerminal: true,
      showPreview: false,
      showAgentPanel: true,
      
      sidebarSize: 18,
      terminalSize: 30,
      agentPanelSize: 28,
      previewSize: 45,

      toggleSidebar: () => set((state) => ({ showSidebar: !state.showSidebar })),
      toggleTerminal: () => set((state) => ({ showTerminal: !state.showTerminal })),
      togglePreview: () => set((state) => ({ showPreview: !state.showPreview })),
      toggleAgentPanel: () => set((state) => ({ showAgentPanel: !state.showAgentPanel })),
      
      setSidebarSize: (size) => set({ sidebarSize: size }),
      setTerminalSize: (size) => set({ terminalSize: size }),
      setAgentPanelSize: (size) => set({ agentPanelSize: size }),
      setPreviewSize: (size) => set({ previewSize: size }),
    }),
    {
      name: 'runneride-ui-storage',
    }
  )
);
