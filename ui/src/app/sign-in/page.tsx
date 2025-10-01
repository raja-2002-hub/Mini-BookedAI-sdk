"use client";

import { SignIn, useAuth, useClerk } from '@clerk/nextjs';
import { Button } from '@/components/ui/button';
import React, { useEffect, useState } from 'react';


export default function SignInPage() {
  const [isMounted, setIsMounted] = useState(false);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const { isSignedIn } = useAuth();
  const clerk = useClerk();

  const handleGuestMode = () => {
    sessionStorage.setItem('guestMode', 'true');
    window.location.href = '/';
  };

  // Handle hydration
  useEffect(() => {
    setIsMounted(true);
    
    // Check if we're coming back from OAuth (has __clerk params) or in authenticating state
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      const isInAuthFlow = sessionStorage.getItem('isAuthenticating') === 'true';
      
      if (params.toString().includes('__clerk') || isInAuthFlow) {
        console.log('Detected OAuth callback - showing loading screen');
        sessionStorage.setItem('isAuthenticating', 'true');
        setIsAuthenticating(true);
      }
    }
    
    // Function to check and hide OAuth errors
    const checkAndHideErrors = () => {
      // Check all elements with role="alert" and any element with error text
      const allElements = Array.from(document.querySelectorAll('[role="alert"], div, p, span'));
      allElements.forEach((el) => {
        const text = el.textContent?.toLowerCase() || '';
        if ((text.includes('external account') && text.includes('not found')) ||
            (text.includes('account') && text.includes('transfer')) ||
            (text.includes('no account') && text.includes('transfer')) ||
            (text.includes('there is no') && text.includes('account')) ||
            text.includes('already signed in')) {
          console.log('Detected OAuth error - showing loading and redirecting...');
          // Show loading screen
          setIsAuthenticating(true);
          // Hide the error immediately
          if (el instanceof HTMLElement) {
            el.style.display = 'none';
            // Also hide parent containers
            let parent = el.parentElement;
            for (let i = 0; i < 5 && parent; i++) {
              parent.style.display = 'none';
              parent = parent.parentElement;
            }
          }
          clearInterval(checkForErrors);
          
          // If not already showing loading, show it now
          if (!isAuthenticating) {
            sessionStorage.setItem('isAuthenticating', 'true');
            setIsAuthenticating(true);
          }
          
          // Poll until user is signed in, then redirect
          let pollCount = 0;
          const pollInterval = setInterval(async () => {
            pollCount++;
            // Check clerk.session directly instead of relying on hook value
            const hasSession = clerk.session !== null && clerk.session !== undefined;
            console.log('Checking auth status...', { hasSession, pollCount, sessionId: clerk.session?.id });
            
            // Check if signed in or timeout after 15 seconds (longer for Railway)
            if (hasSession || pollCount > 30) {
              clearInterval(pollInterval);
              console.log('Redirecting to home, hasSession:', hasSession);
              sessionStorage.removeItem('isAuthenticating');
              window.location.href = '/';
            }
          }, 500);
        }
      });
    };
    
    // Run immediately
    checkAndHideErrors();
    
    // Watch for OAuth errors and auto-redirect every 50ms
    const checkForErrors = setInterval(checkAndHideErrors, 50);
    
    return () => clearInterval(checkForErrors);
  }, []);


  // Prevent hydration mismatch by showing loading state initially
  // Also show loading if in auth flow
  if (!isMounted || (typeof window !== 'undefined' && sessionStorage.getItem('isAuthenticating') === 'true')) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-700 dark:text-gray-300 text-lg">Completing sign-up...</p>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-2">Please wait while we set up your account</p>
        </div>
      </div>
    );
  }

  // Show loading screen while authenticating
  if (isAuthenticating) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-700 dark:text-gray-300 text-lg">Completing sign-up...</p>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-2">Please wait while we set up your account</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
      <div className="w-full max-w-md">
        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl="/sign-up"
          afterSignInUrl="/"
          afterSignUpUrl="/"
          fallbackRedirectUrl="/"
          appearance={{
            elements: {
              formButtonPrimary:
                'bg-blue-600 hover:bg-blue-700 text-sm normal-case',
              card: 'shadow-xl border-0',
              headerTitle: 'text-gray-900 dark:text-white',
              headerSubtitle: 'text-gray-600 dark:text-gray-400',
              socialButtonsBlockButton:
                'border border-gray-300 hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-700',
              formFieldInput:
                'border border-gray-300 focus:border-blue-500 dark:border-gray-600 dark:focus:border-blue-400',
              footerActionLink:
                'text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300',
              // Disable CAPTCHA completely
              captcha: 'none',
            },
          }}
        />
        {/* Hidden CAPTCHA element to prevent "DOM element not found" error */}
        <div id="clerk-captcha" style={{ display: 'none' }}></div>
        <div className="mt-6 text-center relative z-10 w-full max-w-[406px]">
          <Button
            onClick={handleGuestMode}
            variant="outline"
            className="w-full bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600"
          >
            Continue as Guest
          </Button>
        </div>
      </div>
    </div>
  );
}