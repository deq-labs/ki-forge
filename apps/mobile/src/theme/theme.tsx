import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { TextStyle } from 'react-native';

import { fontFace } from '@/theme/fonts';
import { colors as baseColors, pathColors, typography, type PathSlug, type TypographyToken } from '@/theme/tokens';

export type Colors = { -readonly [K in keyof typeof baseColors]: string };

export type Theme = {
  path: PathSlug;
  /** Token colors with `ki` / `kiHot` re-pointed to the active path's energy pair. */
  colors: Colors;
};

export function themeFor(path: PathSlug): Theme {
  return { path, colors: { ...baseColors, ...pathColors[path] } };
}

const ThemeContext = createContext<Theme>(themeFor('storm'));

export function PathThemeProvider({ path, children }: { path: PathSlug; children: ReactNode }) {
  const theme = useMemo(() => themeFor(path), [path]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Theme {
  return useContext(ThemeContext);
}

/** Text style for a typography token: loaded font face, size, line height, spacing, tabular numbers. */
export function textStyle(token: TypographyToken): TextStyle {
  const t = typography[token] as (typeof typography)[TypographyToken] & {
    letterSpacing?: number;
    fontVariant?: readonly string[];
  };
  return {
    fontFamily: fontFace(t.family as 'display' | 'body' | 'data', t.fontWeight),
    fontSize: t.fontSize,
    lineHeight: t.lineHeight,
    ...(t.letterSpacing ? { letterSpacing: t.letterSpacing, textTransform: 'uppercase' as const } : {}),
    ...(t.fontVariant ? { fontVariant: [...t.fontVariant] as TextStyle['fontVariant'] } : {}),
  };
}

export function isPathSlug(v: unknown): v is PathSlug {
  return typeof v === 'string' && v in pathColors;
}
