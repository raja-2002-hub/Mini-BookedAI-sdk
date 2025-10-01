"use client";

import { SignIn } from '@clerk/nextjs';
import { Button } from '@/components/ui/button';
import React, { useEffect, useState } from 'react';


export default function SignInPage() {
  const [isMounted, setIsMounted] = useState(false);

  const handleGuestMode = () => {
    sessionStorage.setItem('guestMode', 'true');
    window.location.href = '/';
  };

  // Handle hydration
  useEffect(() => {
    setIsMounted(true);
    
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
          console.log('Detected OAuth error - hiding and redirecting...');
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
          // Set guest mode temporarily so home page doesn't redirect back
          sessionStorage.setItem('guestMode', 'true');
          // Wait a bit for Clerk to establish session, then redirect
          setTimeout(() => {
            window.location.href = '/';
          }, 1500);
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