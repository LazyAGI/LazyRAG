/**
 * Global app state (replaces qiankun initGlobalState).
 * Use React Context or Zustand in components to consume.
 */
export const BASENAME =
  typeof window !== "undefined" && window.BASENAME ? window.BASENAME : "";

export interface GlobalState {
  theme?: string;
  basename: string;
  setAppLoading?: (loading: boolean) => void;
}

export const defaultGlobalState: GlobalState = {
  basename: BASENAME,
};
