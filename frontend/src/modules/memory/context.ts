import { useOutletContext } from "react-router-dom";

export function useMemoryManagementOutletContext() {
  return useOutletContext<any>();
}
