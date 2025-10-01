"use client";

import React, { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useClerk, useAuth } from '@clerk/nextjs';

function SSOCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const clerk = useClerk();
  const { isSignedIn, sessionId } = useAuth();
  const [_isProcessing, setIsProcessing] = useState(true);



  useEffect(() => {
    let isMounted = true;
    let timeoutId: NodeJS.Timeout;
    
    async function handleCallback() {
      console.log('SSO Callback - Initial auth state:', { isSignedIn, sessionId });
      console.log('Callback query params:', searchParams.toString());

      // If already signed in at mount, redirect immediately without calling handleRedirectCallback
      if (isSignedIn && sessionId) {
        console.log('User already signed in - redirecting to home immediately');
        if (isMounted) {
          router.replace('/');
        }
        return;
      }

      // Set a minimum loading time to prevent error flashes
      const minLoadTime = new Promise(resolve => {
        timeoutId = setTimeout(resolve, 1500);
      });

      try {
        // Wrap handleRedirectCallback in try-catch to suppress all errors
        try {
          await clerk.handleRedirectCallback({
            redirectUrl: '/',
            afterSignInUrl: '/',
            afterSignUpUrl: '/',
          });
          console.log('OAuth callback completed successfully');
        } catch (callbackError: any) {
          // Silently catch all handleRedirectCallback errors
          console.log('Callback processing (error caught, continuing):', callbackError?.message);
        }
        
        // Wait for minimum load time before redirecting
        await minLoadTime;
        
        if (isMounted) {
          setIsProcessing(false);
          router.replace('/');
        }
        
      } catch (error: any) {
        // Final catch-all - wait minimum time then redirect
        await minLoadTime;
        
        if (isMounted) {
          setIsProcessing(false);
          router.replace('/');
        }
      }
    }

    handleCallback();
    
    return () => {
      isMounted = false;
      if (timeoutId) clearTimeout(timeoutId);
    };
  }, [clerk, router, searchParams, isSignedIn, sessionId]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
      </div>
    </div>
  );
}

export default function SSOCallback() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
        </div>
      </div>
    }>
      <SSOCallbackContent />
    </Suspense>
  );
}
