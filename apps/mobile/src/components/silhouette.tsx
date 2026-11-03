import Svg, { Circle, Defs, Path, RadialGradient, Rect, Stop } from 'react-native-svg';

/**
 * A figure generated from a shoulder-to-waist ratio (never a drawn character): the shoulder line is
 * `ratio` times the waist, so a 1.60 Storm frame is visibly wider up top than a 1.45 Shadow frame.
 */
export function Silhouette({
  ratio,
  color,
  glow,
  size = 120,
  label,
}: {
  ratio: number;
  color: string;
  glow?: string;
  size?: number;
  label?: string;
}) {
  const w = 100;
  const h = 120;
  const cx = w / 2;
  const waist = 22;
  const shoulders = Math.min(waist * ratio, 52);
  const sTop = 30; // shoulder line
  const wY = 64; // waist line
  const s = shoulders / 2;
  const half = waist / 2;
  const torso = [
    `M${cx - s} ${sTop}`,
    `Q${cx} ${sTop - 4} ${cx + s} ${sTop}`,
    `L${cx + half} ${wY}`,
    `L${cx - half} ${wY}`,
    'Z',
  ].join(' ');
  const arm = (dir: 1 | -1) =>
    `M${cx + dir * s} ${sTop + 1} L${cx + dir * (s + 5)} ${sTop + 6} L${cx + dir * (s + 7)} ${wY - 4} L${cx + dir * (s + 3)} ${wY - 3} L${cx + dir * (s + 1)} ${sTop + 12} Z`;
  const legs = `M${cx - half} ${wY} L${cx + half} ${wY} L${cx + half - 2} ${h - 6} L${cx + 1.5} ${h - 6} L${cx} ${wY + 12} L${cx - 1.5} ${h - 6} L${cx - half + 2} ${h - 6} Z`;

  return (
    <Svg
      width={size}
      height={(size * h) / w}
      viewBox={`0 0 ${w} ${h}`}
      accessible={!!label}
      accessibilityLabel={label}>
      {glow && (
        <>
          <Defs>
            <RadialGradient id="aura" cx="50%" cy="78%" r="55%">
              <Stop offset="0" stopColor={glow} stopOpacity={0.55} />
              <Stop offset="1" stopColor={glow} stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Rect x={0} y={0} width={w} height={h} fill="url(#aura)" />
        </>
      )}
      <Circle cx={cx} cy={sTop - 13} r={7} fill={color} />
      <Rect x={cx - 3} y={sTop - 7} width={6} height={6} fill={color} />
      <Path d={torso} fill={color} />
      <Path d={arm(-1)} fill={color} />
      <Path d={arm(1)} fill={color} />
      <Path d={legs} fill={color} />
    </Svg>
  );
}
