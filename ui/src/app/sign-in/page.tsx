"use client";

import { SignIn, useSignUp } from '@clerk/nextjs';
import { Button } from '@/components/ui/button';
import React, { useEffect, useState } from 'react';

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

export default function SignInPage() {
  const { signUp } = useSignUp();
  const [isMounted, setIsMounted] = useState(false);

  const handleGuestMode = () => {
    sessionStorage.setItem('guestMode', 'true');
    window.location.href = '/';
  };

  const handleSocialAuth = async (strategy: 'oauth_apple' | 'oauth_google') => {
    console.log('handleSocialAuth called with strategy:', strategy);
    try {
      console.log('Calling signUp.authenticateWithRedirect...');
      await signUp?.authenticateWithRedirect({
        strategy,
        redirectUrl: '/sign-in/sso-callback',
        redirectUrlComplete: '/sign-in/sso-callback',
        continueSignUp: true,
      });
      console.log('signUp.authenticateWithRedirect completed');
    } catch (error: any) {
      console.error('Social auth failed:', error);
      if (error.code === 'external_account_not_found' || error.message?.includes('external account')) {
        console.log('External account not found - new user created successfully');
        // Ignore this error since sign-up proceeds
      } else {
        // Handle other errors (e.g., network issues)
        console.error('Unexpected auth error:', error);
      }
    }
  };

  // Handle hydration
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Override social buttons to trigger sign-up flow
  useEffect(() => {
    if (!isMounted) return;
    const overrideSocialButtons = () => {
      const appleBtn = document.querySelector('button[data-provider="apple"]');
      const googleBtn = document.querySelector('button[data-provider="google"]');

      console.log('Looking for social buttons:', { appleBtn, googleBtn });

      if (appleBtn && !appleBtn.getAttribute('data-overridden')) {
        console.log('Overriding Apple button');
        appleBtn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          console.log('Apple button clicked - triggering signUp flow');
          handleSocialAuth('oauth_apple');
        });
        // Prevent multiple listeners
        appleBtn.setAttribute('data-overridden', 'true');
      }

      if (googleBtn && !googleBtn.getAttribute('data-overridden')) {
        console.log('Overriding Google button');
        googleBtn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          console.log('Google button clicked - triggering signUp flow');
          handleSocialAuth('oauth_google');
        });
        // Prevent multiple listeners
        googleBtn.setAttribute('data-overridden', 'true');
      }
    };

    // Use MutationObserver to detect when social buttons are rendered
    const observer = new MutationObserver(() => {
      const appleBtn = document.querySelector('button[data-provider="apple"]');
      const googleBtn = document.querySelector('button[data-provider="google"]');
      if ((appleBtn && !appleBtn.getAttribute('data-overridden')) || (googleBtn && !googleBtn.getAttribute('data-overridden'))) {
        overrideSocialButtons();
      }
    });

    // Observe changes in the DOM under the SignIn component
    const signInContainer = document.querySelector('.cl-signIn-root');
    if (signInContainer) {
      observer.observe(signInContainer, { childList: true, subtree: true });
    }

    overrideSocialButtons();

    return () => observer.disconnect();
  }, [isMounted]);

  // Prevent hydration mismatch by showing loading state initially
  if (!isMounted) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
        <div className="w-full max-w-md">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
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
          fallbackRedirectUrl="/sign-in/sso-callback"
          forceRedirectUrl="/sign-in/sso-callback"
          afterSignInUrl="/"
          afterSignUpUrl="/sign-in/sso-callback"
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
              // Removed 'captcha: "block"' to prevent init warning; fallback to invisible
            },
          }}
        />
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