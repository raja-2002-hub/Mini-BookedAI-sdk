"use client";

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useClerk, useAuth } from '@clerk/nextjs';

// Type declaration for window.Clerk
declare global {
  interface Window {
    Clerk?: {
      __unstable__environment?: {
        skipCaptcha?: boolean;
      };
    };
  }
}

export default function SSOCallback() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const clerk = useClerk();
  const { isSignedIn, sessionId } = useAuth();
  const [isProcessing, setIsProcessing] = useState(true);

  useEffect(() => {
    async function handleCallback() {
      console.log('SSO Callback - Initial auth state:', { isSignedIn, sessionId });
      console.log('Callback query params:', searchParams.toString());

      try {
        await clerk.handleRedirectCallback({
          redirectUrl: '/',
          afterSignInUrl: '/',
          afterSignUpUrl: '/',
          continueSignUpUrl: '/sign-up',
        });
        console.log('OAuth callback completed. Post-callback auth state:', { isSignedIn, sessionId });

        // Poll for session readiness
        const maxAttempts = 10;
        let attempts = 0;
        const checkSession = setInterval(() => {
          attempts++;
          console.log(`Checking session (attempt ${attempts}):`, { isSignedIn, sessionId });
          if (isSignedIn || attempts >= maxAttempts) {
            clearInterval(checkSession);
            setIsProcessing(false);
            router.push('/');
          }
        }, 500); // Check every 0.5s
      } catch (error: any) {
        console.error('OAuth callback error:', error);
        if (error.code === 'external_account_not_found') {
          console.log('External account not found - proceeding with new user');
          setIsProcessing(false);
          router.push('/');
        } else {
          router.push('/sign-in?error=oauth_failed');
        }
      }
    }

    handleCallback();
  }, [clerk, router, searchParams, isSignedIn, sessionId]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <p>Processing authentication...</p>
      </div>
    </div>
  );
}
