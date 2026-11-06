import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { TextStyle } from 'react-native';

import { fontFace } from '@/theme/fonts';
import { useSettings } from '@/state/settings';
import {
  colors as baseColors,
  pathColors,
  themeColors,
  themePathColors,
  themes,
  typography,
  type PathSlug,
  type ThemeId,
  type TypographyToken,
} from '@/theme/tokens';

export type Colors = { -readonly [K in keyof typeof baseColors]: string };

export type ThemeStyle = (typeof themes)[number];

export type Theme = {
  path: PathSlug;
  /** Token colors with `ki` / `kiHot` re-pointed to the active path's energy pair. */
  colors: Colors;
  /** The color theme's style: light/dark, gradients and glows on or off, border weight, corner radius. */
  style: ThemeStyle;
};

export const THEME_IDS = themes.map((t) => t.id) as ThemeId[];

export function isThemeId(v: unknown): v is ThemeId {
  return typeof v === 'string' && v in themeColors;
}

export function themeFor(path: PathSlug, id: ThemeId = 'night'): Theme {
  const style = themes.find((t) => t.id === id) ?? themes[0];
  const paths = themePathColors[style.id] ?? pathColors;
  return { path, colors: { ...(themeColors[style.id] ?? baseColors), ...paths[path] }, style };
}

const ThemeContext = createContext<Theme>(themeFor('storm'));

/** Path energy plus the color theme picked in Profile › Theme (stored on this device). */
export function PathThemeProvider({ path, children }: { path: PathSlug; children: ReactNode }) {
  const id = useSettings((s) => s.theme);
  const theme = useMemo(() => themeFor(path, id), [path, id]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

/** A path's energy pair in the current color theme (path pickers show every path, not just yours). */
export function pathPair(theme: Theme, slug: string): { ki: string; kiHot: string } {
  const paths = themePathColors[theme.style.id] as Record<string, { ki: string; kiHot: string }>;
  return paths[slug] ?? paths.storm;
}

/** Energy fill stops: the ki gradient, or one flat color on themes without gradients. */
export function energyFill(theme: Theme): [string, string] {
  return theme.style.gradient ? [theme.colors.kiHot, theme.colors.ki] : [theme.colors.ki, theme.colors.ki];
}

/** A glow color for text or box shadows, or transparent on themes without glow. */
export function glowColor(theme: Theme, color: string): string {
  return theme.style.glow ? color : 'transparent';
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
