import type { ColorValue } from 'react-native';
import Svg, { Circle, Path, Rect } from 'react-native-svg';

type IconProps = { color: ColorValue; size?: number; strokeWidth?: number };

/**
 * Simple geometric line icons (no third-party icon set). 24-unit grid, round caps. Decorative: the button or
 * tab around each icon carries the label. `aria-hidden` works on native and web (`accessible` is native-only
 * and leaks onto the DOM <svg> on web).
 */
function Icon({ size = 26, children }: { size?: number; children: React.ReactNode }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      {children}
    </Svg>
  );
}

export function StarIcon({ color, size, strokeWidth = 1.8 }: IconProps) {
  return (
    <Icon size={size}>
      <Path
        d="M12 3.2l2.6 5.5 6 .8-4.4 4.1 1.1 5.9L12 16.6l-5.3 2.9 1.1-5.9-4.4-4.1 6-.8z"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
    </Icon>
  );
}

export function ArcIcon({ color, size, strokeWidth = 1.8 }: IconProps) {
  return (
    <Icon size={size}>
      <Circle cx={6} cy={18} r={2.2} stroke={color} strokeWidth={strokeWidth} />
      <Circle cx={18} cy={6} r={2.2} stroke={color} strokeWidth={strokeWidth} />
      <Path d="M7.6 16.4C9 12 10 13 12 10s3.4-1.8 4.4-2.4" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
    </Icon>
  );
}

export function BarbellIcon({ color, size, strokeWidth = 2.2 }: IconProps) {
  return (
    <Icon size={size}>
      <Path d="M3 12h18" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
      <Rect x={5} y={7} width={2.6} height={10} rx={1} stroke={color} strokeWidth={strokeWidth} />
      <Rect x={16.4} y={7} width={2.6} height={10} rx={1} stroke={color} strokeWidth={strokeWidth} />
    </Icon>
  );
}

export function ScanIcon({ color, size, strokeWidth = 1.8 }: IconProps) {
  const corner = { stroke: color, strokeWidth, strokeLinecap: 'round' as const };
  return (
    <Icon size={size}>
      <Path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" {...corner} />
      <Circle cx={12} cy={10} r={2.4} stroke={color} strokeWidth={strokeWidth} />
      <Path d="M8 17c.8-2.2 2.2-3.2 4-3.2s3.2 1 4 3.2" {...corner} />
    </Icon>
  );
}

export function PersonIcon({ color, size, strokeWidth = 1.8 }: IconProps) {
  return (
    <Icon size={size}>
      <Circle cx={12} cy={8} r={4} stroke={color} strokeWidth={strokeWidth} />
      <Path d="M4 20.5c1.4-4 4.4-6 8-6s6.6 2 8 6" stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" />
    </Icon>
  );
}

export function CarIcon({ color, size, strokeWidth = 1.8 }: IconProps) {
  return (
    <Icon size={size}>
      <Path
        d="M4 15.5v-2.8l1.8-4.2A2 2 0 0 1 7.6 7.3h8.8a2 2 0 0 1 1.8 1.2l1.8 4.2v2.8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"
        stroke={color}
        strokeWidth={strokeWidth}
        strokeLinejoin="round"
      />
      <Path d="M4.6 12.5h14.8" stroke={color} strokeWidth={strokeWidth} />
      <Circle cx={7.8} cy={16.6} r={1.6} stroke={color} strokeWidth={strokeWidth} />
      <Circle cx={16.2} cy={16.6} r={1.6} stroke={color} strokeWidth={strokeWidth} />
    </Icon>
  );
}
