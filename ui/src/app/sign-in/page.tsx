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
          afterSignUpUrl="/sign-up/sso-callback"
          fallbackRedirectUrl="/"
          forceRedirectUrl="/"
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