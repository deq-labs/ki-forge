/**
 * Sign-in plumbing (#78). With `EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY` set the app signs in with Clerk (email
 * one-time codes) and every API call carries the Clerk session token. Without it the dev "Who's training?"
 * sign-in stays, so local work doesn't need a Clerk account.
 *
 * The Clerk hooks live in React; this module is the bridge the API client and the settings store use.
 */

export const CLERK_PUBLISHABLE_KEY = process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY ?? '';
export const clerkEnabled = CLERK_PUBLISHABLE_KEY.length > 0;

type Bridge = {
  getToken: () => Promise<string | null>;
  signOut: () => Promise<unknown>;
};

let bridge: Bridge | null = null;

/** Called by the Clerk session component once Clerk has loaded; null when it unmounts. */
export function setAuthBridge(b: Bridge | null): void {
  bridge = b;
}

/** A fresh Clerk session token (Clerk refreshes it), or null when signed out or Clerk is off. */
export async function sessionToken(): Promise<string | null> {
  if (!bridge) return null;
  try {
    return await bridge.getToken();
  } catch {
    return null;
  }
}

/** Ends the Clerk session (no-op without Clerk). */
export async function clerkSignOut(): Promise<void> {
  await bridge?.signOut().catch(() => {});
}

/** Clerk error code from a ClerkAPIResponseError (`errors[0].code`) or a plain ClerkError (`code`). */
export function clerkErrorCode(e: unknown): string | null {
  if (!e || typeof e !== 'object') return null;
  const o = e as { errors?: { code?: string }[]; code?: string };
  return o.errors?.[0]?.code ?? o.code ?? null;
}

/** A message for people, not developers. */
export function clerkErrorMessage(e: unknown): string {
  switch (clerkErrorCode(e)) {
    case 'form_code_incorrect':
      return "That code doesn't match. Check the latest email and try again.";
    case 'verification_expired':
      return 'That code expired. Send a new one.';
    case 'too_many_requests':
    case 'verification_failed':
      return 'Too many tries. Wait a minute, then send a new code.';
    case 'form_param_format_invalid':
    case 'form_identifier_invalid':
      return "That doesn't look like an email address.";
    default: {
      const o = e as { errors?: { longMessage?: string; message?: string }[]; message?: string } | null;
      return o?.errors?.[0]?.longMessage ?? o?.errors?.[0]?.message ?? o?.message ?? 'Something went wrong.';
    }
  }
}
