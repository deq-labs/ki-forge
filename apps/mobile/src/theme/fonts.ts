import { ChakraPetch_500Medium, ChakraPetch_600SemiBold } from '@expo-google-fonts/chakra-petch';
import { DelaGothicOne_400Regular } from '@expo-google-fonts/dela-gothic-one';
import {
  MPLUS1p_400Regular,
  MPLUS1p_500Medium,
  MPLUS1p_700Bold,
  MPLUS1p_800ExtraBold,
} from '@expo-google-fonts/m-plus-1p';

/** Every font face the app loads (passed to `useFonts`). */
export const fontAssets = {
  DelaGothicOne_400Regular,
  MPLUS1p_400Regular,
  MPLUS1p_500Medium,
  MPLUS1p_700Bold,
  MPLUS1p_800ExtraBold,
  ChakraPetch_500Medium,
  ChakraPetch_600SemiBold,
};

type Family = 'display' | 'body' | 'data';

/**
 * The loaded face for a token's family and weight. Custom fonts carry their weight in the face, so
 * styles set `fontFamily` only (setting `fontWeight` too makes Android fall back to the system font).
 */
export function fontFace(family: Family, weight: string | number = '400'): string {
  const w = Number(weight);
  if (family === 'display') return 'DelaGothicOne_400Regular';
  if (family === 'data') return w >= 600 ? 'ChakraPetch_600SemiBold' : 'ChakraPetch_500Medium';
  if (w >= 800) return 'MPLUS1p_800ExtraBold';
  if (w >= 700) return 'MPLUS1p_700Bold';
  if (w >= 500) return 'MPLUS1p_500Medium';
  return 'MPLUS1p_400Regular';
}
