import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api';
import { useSettings } from '@/state/settings';

/** The signed-in user, run and stats. Keyed by identity so switching dev users never mixes data. */
export function useMe() {
  const email = useSettings((s) => s.devEmail);
  return useQuery({
    queryKey: ['me', email],
    queryFn: () => api.get('/v1/me'),
    enabled: !!email,
  });
}
