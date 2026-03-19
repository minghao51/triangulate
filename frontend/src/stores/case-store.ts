import { create } from 'zustand';
import type { TopicCase, CaseDetail, Claim, Evidence, Exception, Party, TimelineEvent, RunHistoryItem } from '../types/backend-models';

interface PipelineStatus {
  currentStage: string;
  stages: Array<{
    name: string;
    status: 'pending' | 'running' | 'success' | 'error';
    timestamp?: string;
  }>;
}

interface CaseState {
  // Active case
  activeCase: TopicCase | null;
  caseDetail: CaseDetail | null;
  pipelineStatus: PipelineStatus | null;

  // Case data
  claims: Claim[];
  evidence: Evidence[];
  exceptions: Exception[];
  parties: Party[];
  timeline: TimelineEvent[];
  runHistory: RunHistoryItem[];

  // Actions
  setActiveCase: (caseData: TopicCase) => void;
  setCaseDetail: (detail: CaseDetail) => void;
  setPipelineStatus: (status: PipelineStatus) => void;
  setClaims: (claims: Claim[]) => void;
  setEvidence: (evidence: Evidence[]) => void;
  setExceptions: (exceptions: Exception[]) => void;
  setParties: (parties: Party[]) => void;
  setTimeline: (timeline: TimelineEvent[]) => void;
  setRunHistory: (history: RunHistoryItem[]) => void;

  // Update helpers
  updateClaim: (claimId: string, updates: Partial<Claim>) => void;
  updateException: (exceptionId: string, updates: Partial<Exception>) => void;
  addLogEntry: (entry: RunHistoryItem) => void;

  // Clear
  clearActiveCase: () => void;
}

export const useCaseStore = create<CaseState>((set) => ({
  // Initial state
  activeCase: null,
  caseDetail: null,
  pipelineStatus: null,
  claims: [],
  evidence: [],
  exceptions: [],
  parties: [],
  timeline: [],
  runHistory: [],

  // Actions
  setActiveCase: (caseData) => set({ activeCase: caseData }),
  setCaseDetail: (detail) => set({ caseDetail: detail }),
  setPipelineStatus: (status) => set({ pipelineStatus: status }),
  setClaims: (claims) => set({ claims }),
  setEvidence: (evidence) => set({ evidence }),
  setExceptions: (exceptions) => set({ exceptions }),
  setParties: (parties) => set({ parties }),
  setTimeline: (timeline) => set({ timeline }),
  setRunHistory: (history) => set({ runHistory: history }),

  // Update helpers
  updateClaim: (claimId, updates) =>
    set((state) => ({
      claims: state.claims.map((c) =>
        c.id === claimId ? { ...c, ...updates } : c
      ),
    })),

  updateException: (exceptionId, updates) =>
    set((state) => ({
      exceptions: state.exceptions.map((e) =>
        e.id === exceptionId ? { ...e, ...updates } : e
      ),
    })),

  addLogEntry: (entry) =>
    set((state) => ({
      runHistory: [entry, ...state.runHistory],
    })),

  // Clear
  clearActiveCase: () =>
    set({
      activeCase: null,
      caseDetail: null,
      pipelineStatus: null,
      claims: [],
      evidence: [],
      exceptions: [],
      parties: [],
      timeline: [],
      runHistory: [],
    }),
}));
