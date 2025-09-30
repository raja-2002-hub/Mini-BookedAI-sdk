"use client";

import React, { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useClerk, useAuth } from '@clerk/nextjs';

function SignUpSSOCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const clerk = useClerk();
  const { isSignedIn, sessionId } = useAuth();
  const [_isProcessing, setIsProcessing] = useState(true);



  useEffect(() => {
    let isMounted = true;
    let timeoutId: NodeJS.Timeout;
    
    async function handleCallback() {
      console.log('SignUp SSO Callback - Initial auth state:', { isSignedIn, sessionId });
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
          console.log('SignUp OAuth callback completed successfully');
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
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
        <p>Processing sign-up authentication...</p>
      </div>
    </div>
  );
}

export default function SignUpSSOCallback() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p>Processing sign-up authentication...</p>
        </div>
      </div>
    }>
      <SignUpSSOCallbackContent />
    </Suspense>
  );
}
