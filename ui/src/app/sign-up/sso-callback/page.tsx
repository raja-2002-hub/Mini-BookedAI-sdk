"use client";

import React, { useEffect, useState, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useClerk, useAuth } from '@clerk/nextjs';

function SignUpSSOCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const clerk = useClerk();
  const { isSignedIn, sessionId } = useAuth();
  const [isProcessing, setIsProcessing] = useState(true);



  useEffect(() => {
    async function handleCallback() {

      console.log('SignUp SSO Callback - Initial auth state:', { isSignedIn, sessionId });
      console.log('Callback query params:', searchParams.toString());

      // If already signed in, just redirect to home immediately
      if (isSignedIn) {
        console.log('User already signed in - redirecting to home');
        setIsProcessing(false);
        router.push('/');
        return;
      }

      // Additional check: if we have a session ID, user is likely already signed in
      if (sessionId) {
        console.log('Session ID found - user already signed in');
        setIsProcessing(false);
        router.push('/');
        return;
      }

      try {
        // Handle the OAuth callback
        await clerk.handleRedirectCallback({
          redirectUrl: '/',
        });
        console.log('SignUp OAuth callback completed successfully');
        
        // Wait longer for session to be established
        setTimeout(() => {
          setIsProcessing(false);
          router.push('/');
        }, 2000);
        
      } catch (error: any) {
        console.error('SignUp OAuth callback error:', error);
        
        // Handle specific error cases
        if (error.code === 'external_account_not_found' || error.message?.includes('External Account was not found') || error.message?.includes('There is no account to transfer')) {
          console.log('External account not found - proceeding with new user');
          // Keep loading longer to prevent showing error page
          setTimeout(() => {
            setIsProcessing(false);
            router.push('/');
          }, 2000);
        } else if (error.message?.includes('Unable to complete action')) {
          setIsProcessing(false);
          router.push('/');
        } else if (error.message?.includes('form_identifier_exists') || error.code === 'form_identifier_exists') {
          setIsProcessing(false);
          router.push('/');
        } else if (error.message?.includes('captcha') || error.message?.includes('CAPTCHA')) {
          setIsProcessing(false);
          router.push('/');
        } else if (error.message?.includes('already signed in') || error.message?.includes('You\'re already signed in') || error.message?.includes('already signed')) {
          // Keep loading for a moment to prevent flash
          setTimeout(() => {
            setIsProcessing(false);
            router.push('/');
          }, 1000);
        } else {
          setIsProcessing(false);
          router.push('/');
        }
      }
    }

    handleCallback();
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
