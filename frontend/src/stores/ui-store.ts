import { create } from 'zustand';

type Theme = 'dark' | 'light';

interface UIState {
  // Sidebar
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;

  // Active panel
  activePanel: string | null;
  setActivePanel: (panel: string | null) => void;

  // Theme
  theme: Theme;
  setTheme: (theme: Theme) => void;

  // Modal
  modalOpen: boolean;
  modalContent: React.ReactNode | null;
  openModal: (content: React.ReactNode) => void;
  closeModal: () => void;

  // Notifications
  notifications: Array<{
    id: string;
    type: 'success' | 'warning' | 'danger' | 'info';
    message: string;
    timestamp: number;
  }>;
  addNotification: (notification: Omit<UIState['notifications'][0], 'id' | 'timestamp'>) => void;
  removeNotification: (id: string) => void;

  // Loading states
  globalLoading: boolean;
  setGlobalLoading: (loading: boolean) => void;
}

export const useUIStore = create<UIState>((set) => ({
  // Initial state
  sidebarOpen: true,
  activePanel: null,
  theme: 'dark',
  modalOpen: false,
  modalContent: null,
  notifications: [],
  globalLoading: false,

  // Sidebar actions
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  // Panel actions
  setActivePanel: (panel) => set({ activePanel: panel }),

  // Theme actions
  setTheme: (theme) => set({ theme }),

  // Modal actions
  openModal: (content) => set({ modalOpen: true, modalContent: content }),
  closeModal: () => set({ modalOpen: false, modalContent: null }),

  // Notification actions
  addNotification: (notification) =>
    set((state) => ({
      notifications: [
        ...state.notifications,
        {
          ...notification,
          id: Math.random().toString(36).substring(7),
          timestamp: Date.now(),
        },
      ],
    })),
  removeNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    })),

  // Loading actions
  setGlobalLoading: (loading) => set({ globalLoading: loading }),
}));
