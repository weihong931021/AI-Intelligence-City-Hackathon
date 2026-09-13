import { createContext, useContext } from "react";

export type WorkspaceTab = "map" | "table3" | "table4" | "table5";

export const WORKSPACE_TABS: { id: WorkspaceTab; label: string; short: string; shortcut: string }[] = [
  { id: "map", label: "位置圖", short: "地圖", shortcut: "⌘1" },
  { id: "table3", label: "表3 地價區段勘查表", short: "表3", shortcut: "⌘2" },
  { id: "table4", label: "表4 比較法調查估價表", short: "表4", shortcut: "⌘3" },
  { id: "table5", label: "表5 影響地價區域因素分析明細表", short: "表5", shortcut: "⌘4" },
];

export type WorkspaceApi = {
  tab: WorkspaceTab | null;
  open: (tab: WorkspaceTab) => void;
  close: () => void;
};

export const WorkspaceContext = createContext<WorkspaceApi>({ tab: null, open: () => {}, close: () => {} });

export const useWorkspace = () => useContext(WorkspaceContext);
