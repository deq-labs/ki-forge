import { Text, type TextProps } from 'react-native';

import { textStyle, useTheme, type Colors } from '@/theme/theme';
import type { TypographyToken } from '@/theme/tokens';

type Props = TextProps & {
  variant?: TypographyToken;
  color?: keyof Colors;
};

/** App text: a typography token plus a theme color (ki / kiHot follow the active path). */
export function KText({ variant = 'body', color = 'ink', style, ...rest }: Props) {
  const { colors } = useTheme();
  return <Text {...rest} style={[textStyle(variant), { color: colors[color] }, style]} />;
}
