import { KText } from '@/components/k-text';
import { PlaceholderScreen } from '@/components/placeholder-screen';
import { useMe } from '@/lib/queries';

// Replaced by the HUD and Base screen in #37; for now it proves the API connection and identity.
export default function BaseScreen() {
  const me = useMe();
  const stats = me.data?.stats;
  return (
    <PlaceholderScreen title="Base" note="Power Level, next quest and this week arrive with the Base screen.">
      {me.isPending && <KText color="inkFaint">Connecting…</KText>}
      {me.error && (
        <KText color="danger" accessibilityRole="alert">
          Can&apos;t reach the server: {me.error.message}
        </KText>
      )}
      {me.data && (
        <>
          <KText variant="cardTitle">{me.data.user.display_name}</KText>
          <KText variant="dataSm" color="inkMuted">
            Lv {stats?.level} · {stats?.rank} · {stats?.total_xp.toLocaleString()} XP
          </KText>
          <KText color="inkMuted">
            {me.data.enrollment ? `Path: ${me.data.enrollment.path_slug}` : 'No run yet — onboarding comes next.'}
          </KText>
        </>
      )}
    </PlaceholderScreen>
  );
}
