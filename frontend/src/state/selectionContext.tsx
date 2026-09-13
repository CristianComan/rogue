import { createContext, useContext, useState, type ReactNode } from "react";
import type { Selection } from "./selection";

interface SelectionContextValue {
  selection: Selection;
  select: (selection: Selection) => void;
}

const SelectionContext = createContext<SelectionContextValue | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<Selection>(null);
  return (
    <SelectionContext.Provider value={{ selection, select: setSelection }}>
      {children}
    </SelectionContext.Provider>
  );
}

export function useSelection(): SelectionContextValue {
  const context = useContext(SelectionContext);
  if (!context) throw new Error("useSelection must be used within a SelectionProvider");
  return context;
}
