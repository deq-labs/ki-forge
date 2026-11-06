import { useAuth, useUser } from '@clerk/expo';
import { useEffect } from 'react';

import { setAuthBridge } from '@/lib/auth';
import { useSettings } from '@/state/settings';

/**
 * Keeps the app's signed-in identity in step with Clerk: hands the API client a token getter, sets the
 * account (its email keys the on-device data) after sign-in, and signs out locally when Clerk does.
 */
export function ClerkSession() {
  const { isLoaded, isSignedIn, getToken, signOut } = useAuth();
  const { user } = useUser();
  const owner = useSettings((s) => s.devEmail);
  const signIn = useSettings((s) => s.signIn);

  useEffect(() => {
    setAuthBridge({ getToken: () => getToken(), signOut: () => signOut() });
    return () => setAuthBridge(null);
  }, [getToken, signOut]);

  useEffect(() => {
    if (!isLoaded) return; // offline at launch: keep the last account until Clerk answers
    if (isSignedIn && user) {
      const id = (user.primaryEmailAddress?.emailAddress ?? user.id).toLowerCase();
      if (owner !== id) signIn(id);
    } else if (!isSignedIn && owner) {
      useSettings.getState().signOut();
    }
  }, [isLoaded, isSignedIn, user, owner, signIn]);

  return null;
}
