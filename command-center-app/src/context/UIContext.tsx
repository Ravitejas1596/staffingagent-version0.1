import { createContext, useContext } from 'react';

export type UIColors = typeof light;

interface UIContextValue {
  newUI: boolean;
  toggleNewUI: () => void;
  // Helpers — dark-aware color getters
  c: {
    cardBg: string;
    cardBorder: string;
    cardHoverBg: string;
    panelBg: string;
    text: string;
    textMuted: string;
    textDim: string;
    accent: string;
    link: string;
    inputBg: string;
    inputBorder: string;
    subBg: string;        // fafafa / expanded panel bg
    selectedBg: string;   // selected sub-item bg
    selectedBorder: string;
    // status colors (bg, border, text)
    open: { bg: string; border: string; color: string };
    pending: { bg: string; border: string; color: string };
    resolved: { bg: string; border: string; color: string };
  };
}

const light = {
  cardBg: '#fff',
  cardBorder: '#e2e8f0',
  cardHoverBg: '#f8fafc',
  panelBg: '#fafafa',
  text: '#0f172a',
  textMuted: '#64748b',
  textDim: '#94a3b8',
  accent: '#2563eb',
  link: '#2196f3',
  inputBg: '#fff',
  inputBorder: '#e2e8f0',
  subBg: '#fafafa',
  selectedBg: '#ede9fe',
  selectedBorder: '#a78bfa',
  open:     { bg: '#fef2f2', border: '#fca5a5', color: '#dc2626' },
  pending:  { bg: '#fffbeb', border: '#fcd34d', color: '#d97706' },
  resolved: { bg: '#f0fdf4', border: '#86efac', color: '#16a34a' },
};

const dark = {
  cardBg: 'rgba(255,255,255,0.05)',
  cardBorder: 'rgba(255,255,255,0.09)',
  cardHoverBg: 'rgba(255,255,255,0.08)',
  panelBg: 'rgba(255,255,255,0.03)',
  text: '#f1f5f9',
  textMuted: '#94a3b8',
  textDim: '#64748b',
  accent: '#2dd4bf',
  link: '#7dd3fc',
  inputBg: 'rgba(255,255,255,0.06)',
  inputBorder: 'rgba(255,255,255,0.12)',
  subBg: 'rgba(255,255,255,0.03)',
  selectedBg: 'rgba(109,40,217,0.2)',
  selectedBorder: 'rgba(167,139,250,0.5)',
  open:     { bg: 'rgba(239,68,68,0.12)',   border: 'rgba(239,68,68,0.35)',   color: '#f87171' },
  pending:  { bg: 'rgba(217,119,6,0.12)',   border: 'rgba(217,119,6,0.35)',   color: '#fbbf24' },
  resolved: { bg: 'rgba(22,163,74,0.12)',   border: 'rgba(22,163,74,0.35)',   color: '#34d399' },
};

export const UIContext = createContext<UIContextValue>({
  newUI: false,
  toggleNewUI: () => {},
  c: light,
});

export function useUI(): UIContextValue {
  return useContext(UIContext);
}

export function buildUIContext(newUI: boolean, toggleNewUI: () => void): UIContextValue {
  return { newUI, toggleNewUI, c: newUI ? dark : light };
}
