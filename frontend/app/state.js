// Tiny observable store.
const listeners = new Set();

export const state = {
  caseId: null,
  title: "",
  graph: null,
  alerts: [],
  deadline: null,
  mode: "defense",
  pseudo: false,
  asOf: null,          // null = law in force at each act's date
  filter: "all",
  selectedNode: null,
  selectedAlert: null,
  verdicts: {},        // alert id -> tribunal verdict
  engines: {},
  reforms: [],
  zoom: 1,
};

export function set(patch) {
  Object.assign(state, patch);
  for (const fn of listeners) fn(patch);
}

export const subscribe = fn => { listeners.add(fn); return () => listeners.delete(fn); };
