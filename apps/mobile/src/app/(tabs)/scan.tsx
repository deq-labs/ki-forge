import type { components } from '@kiforge/api-types';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { ScrollView, StyleSheet, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Hud } from '@/components/hud';
import { KText } from '@/components/k-text';
import { Silhouette } from '@/components/silhouette';
import { Panel, PrimaryButton } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { useMe, useProgram, useScans } from '@/lib/queries';
import { useSync } from '@/lib/sync';
import { GAUGE_MAX, GAUGE_MIN, gaugePercent, scanAdvice } from '@/lib/scan';
import { parseNumber } from '@/lib/trial-form';
import { useSettings } from '@/state/settings';
import { toast } from '@/state/toast';
import { textStyle, useTheme } from '@/theme/theme';
import { radius, spacing } from '@/theme/tokens';

type ScanSaved = components['schemas']['ScanSaved'];

/** Progress scan, tape only until photo scans (M5): frame ratio vs the path target, a gauge and history. */
export default function ScanScreen() {
  const { colors } = useTheme();
  const me = useMe();
  const program = useProgram();
  const scans = useScans();
  const path = program.data?.paths.find((p) => p.slug === me.data?.enrollment?.path_slug);
  const target = path?.ratio_target ?? 1.5;
  const ratio = me.data?.stats.frame_ratio ?? null; // newest of Trials and scans (server)
  const latestScan = scans.data?.[0];

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.night900 }]} edges={['top']}>
      <View style={styles.hud}>
        <Hud />
      </View>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <KText variant="screenTitle" accessibilityRole="header">
          Progress scan
        </KText>

        <View style={styles.figures}>
          <Panel style={styles.figure}>
            <KText variant="label" color="inkMuted">
              You
            </KText>
            <Silhouette ratio={ratio ?? 1.3} color={colors.volt} size={90} label={`Your frame ${ratio?.toFixed(2) ?? 'not measured'}`} />
            <KText variant="stat">{ratio != null ? ratio.toFixed(2) : '—'}</KText>
            <KText variant="caption" color="inkMuted">
              tape ratio
            </KText>
          </Panel>
          <Panel style={styles.figure}>
            <KText variant="label" color="inkMuted">
              {path?.name ?? 'Target'}
            </KText>
            <Silhouette ratio={target} color={colors.ki} glow={colors.ki} size={90} label={`Target frame ${target.toFixed(2)}`} />
            <KText variant="stat" color="kiHot">
              {target.toFixed(2)}
            </KText>
            <KText variant="caption" color="inkMuted">
              target
            </KText>
          </Panel>
        </View>

        <Gauge ratio={ratio} target={target} />
        <KText color="inkMuted">{scanAdvice(ratio, target, latestScan?.waist_in ?? null)}</KText>

        <NewScan />

        <KText variant="caption" color="inkFaint">
          Photo scans arrive later; for now a scan is your tape measurements. When photos come, they&apos;re deleted after
          analysis unless you turn on Keep progress photos in Profile.
        </KText>

        {scans.data && scans.data.length > 0 && (
          <Panel style={styles.history}>
            <KText variant="cardTitle">History</KText>
            {scans.data.map((s, i) => (
              <View key={s.id} style={[styles.historyRow, i > 0 && { borderTopColor: colors.line, borderTopWidth: 1 }]}>
                <KText variant="dataSm" color="inkMuted" style={styles.flex}>
                  {new Date(s.taken_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                </KText>
                <KText variant="dataSm" color="inkMuted">
                  {s.shoulders_in}&quot; / {s.waist_in}&quot;
                </KText>
                <KText variant="dataSm" style={styles.histRatio}>
                  {s.frame_ratio?.toFixed(2) ?? '—'}
                </KText>
              </View>
            ))}
          </Panel>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Gauge({ ratio, target }: { ratio: number | null; target: number }) {
  const { colors } = useTheme();
  const pos = (v: number) => `${gaugePercent(v)}%` as const;
  return (
    <View
      style={styles.gauge}
      accessibilityLabel={`Frame ratio gauge from ${GAUGE_MIN.toFixed(2)} to ${GAUGE_MAX.toFixed(2)}: you ${ratio?.toFixed(2) ?? 'not measured'}, target ${target.toFixed(2)}`}>
      <View style={[styles.gaugeTrack, { backgroundColor: colors.panelRaised }]}>
        {ratio != null && <View style={[styles.gaugeFill, { width: pos(ratio), backgroundColor: `${colors.volt}66` }]} />}
      </View>
      {/* Both markers carry a text label, so color is never the only signal. */}
      <View style={[styles.marker, { left: pos(target) }]}>
        <View style={[styles.tick, { backgroundColor: colors.ki }]} />
        <KText variant="label" color="kiHot" style={styles.markerLabel}>
          Target {target.toFixed(2)}
        </KText>
      </View>
      {ratio != null && (
        <View style={[styles.marker, styles.markerTop, { left: pos(ratio) }]}>
          <KText variant="label" color="volt" style={styles.markerLabel}>
            You {ratio.toFixed(2)}
          </KText>
          <View style={[styles.tick, { backgroundColor: colors.volt }]} />
        </View>
      )}
      <View style={styles.scale}>
        <KText variant="caption" color="inkFaint">
          {GAUGE_MIN.toFixed(2)}
        </KText>
        <KText variant="caption" color="inkFaint">
          {GAUGE_MAX.toFixed(2)}
        </KText>
      </View>
    </View>
  );
}

function NewScan() {
  const { colors } = useTheme();
  const queryClient = useQueryClient();
  const owner = useSettings((s) => s.devEmail);
  const [shoulders, setShoulders] = useState('');
  const [waist, setWaist] = useState('');
  const [busy, setBusy] = useState(false);
  const s = parseNumber(shoulders);
  const w = parseNumber(waist);
  const valid = typeof s === 'number' && s > 0 && s < 100 && typeof w === 'number' && w > 0 && w < 100;

  async function save() {
    if (!valid) return;
    setBusy(true);
    try {
      const res = (await api.post('/v1/scans', { shoulders_in: s, waist_in: w, with_photo: false })) as ScanSaved;
      setShoulders('');
      setWaist('');
      const xp = res.xp_awarded.reduce((n, a) => n + a.amount, 0);
      toast(`Scan logged · ${res.scan.frame_ratio?.toFixed(2) ?? ''} · +${xp} XP`);
      if (res.level_up || res.new_badges.length) {
        useSync.setState({ lastReward: { ...res, sessions: [], accepted: { sessions: [], sets: [] } } as never });
      }
      void queryClient.invalidateQueries({ queryKey: ['scans', owner] });
      void queryClient.invalidateQueries({ queryKey: ['me', owner] });
    } catch (e) {
      toast(e instanceof ApiError && e.offline ? 'Logging a scan needs a connection to the server.' : String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  const input = [textStyle('stat'), styles.input, { color: colors.ink, backgroundColor: colors.night800, borderColor: colors.line }];
  return (
    <Panel style={styles.newScan}>
      <KText variant="cardTitle">New scan</KText>
      <KText variant="caption" color="inkMuted">
        Tape at the widest point of the delts, arms relaxed; waist at the navel, relaxed, in the morning.
      </KText>
      <View style={styles.inputs}>
        <View style={styles.flex}>
          <KText variant="label" color="inkMuted">
            Shoulders (in)
          </KText>
          <TextInput value={shoulders} onChangeText={setShoulders} placeholder="46" placeholderTextColor={colors.inkFaint} inputMode="decimal" keyboardType="decimal-pad" accessibilityLabel="Shoulders in inches" style={input} />
        </View>
        <View style={styles.flex}>
          <KText variant="label" color="inkMuted">
            Waist (in)
          </KText>
          <TextInput value={waist} onChangeText={setWaist} placeholder="33" placeholderTextColor={colors.inkFaint} inputMode="decimal" keyboardType="decimal-pad" accessibilityLabel="Waist in inches" style={input} />
        </View>
      </View>
      <PrimaryButton label={busy ? 'Saving…' : valid ? 'New scan · +50 XP' : 'Enter shoulders and waist'} disabled={!valid || busy} onPress={() => void save()} />
    </Panel>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  flex: { flex: 1 },
  hud: { paddingHorizontal: spacing[4] },
  body: { padding: spacing[4], paddingTop: spacing[2], gap: spacing[4], paddingBottom: spacing[6] },
  figures: { flexDirection: 'row', gap: spacing[3] },
  figure: { flex: 1, alignItems: 'center', gap: spacing[1] },
  gauge: { paddingTop: 28, paddingBottom: 4 },
  gaugeTrack: { height: 12, borderRadius: 6, overflow: 'hidden' },
  gaugeFill: { height: 12 },
  marker: { position: 'absolute', top: 22, alignItems: 'center', width: 110, marginLeft: -55 },
  markerTop: { top: 0 },
  tick: { width: 3, height: 24, borderRadius: 2 },
  markerLabel: { fontSize: 10, lineHeight: 12 },
  scale: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 22 },
  newScan: { gap: spacing[3] },
  inputs: { flexDirection: 'row', gap: spacing[3] },
  input: { minHeight: 52, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing[3], marginTop: spacing[1] },
  history: { gap: 0, padding: 0, overflow: 'hidden' },
  historyRow: { flexDirection: 'row', gap: spacing[3], paddingHorizontal: spacing[4], paddingVertical: spacing[3] },
  histRatio: { width: 44, textAlign: 'right' },
});
