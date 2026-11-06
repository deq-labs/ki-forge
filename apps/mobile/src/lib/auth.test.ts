import assert from 'node:assert/strict';
import { test } from 'node:test';

import { clerkErrorCode, clerkErrorMessage } from './auth.ts';

test('reads Clerk error codes from API errors and plain errors', () => {
  assert.equal(clerkErrorCode({ errors: [{ code: 'form_code_incorrect' }] }), 'form_code_incorrect');
  assert.equal(clerkErrorCode({ code: 'form_identifier_not_found' }), 'form_identifier_not_found');
  assert.equal(clerkErrorCode(new Error('x')), null);
  assert.equal(clerkErrorCode(null), null);
});

test('turns Clerk errors into plain messages', () => {
  assert.match(clerkErrorMessage({ errors: [{ code: 'form_code_incorrect' }] }), /doesn't match/);
  assert.match(clerkErrorMessage({ errors: [{ code: 'verification_expired' }] }), /expired/);
  assert.equal(clerkErrorMessage({ errors: [{ code: 'other', longMessage: 'Long text.' }] }), 'Long text.');
  assert.equal(clerkErrorMessage(new Error('Sign-up needs more details')), 'Sign-up needs more details');
  assert.equal(clerkErrorMessage(null), 'Something went wrong.');
});
