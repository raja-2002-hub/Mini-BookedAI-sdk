"use client";

import { SignUp } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import React, { useEffect, useState } from "react";


export default function SignUpPage() {
  const [isMounted, setIsMounted] = useState(false);

  const handleGuestMode = () => {
    // Use sessionStorage instead of localStorage for session-only guest mode
    sessionStorage.setItem('guestMode', 'true');
    // Force a page reload to ensure the guest mode is recognized
    window.location.href = '/';
  };


  // Handle hydration
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // Force-hide any Clerk footer/sign-in elements that may render after hydration
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const hideClerkSignIn = () => {
      const selectors = [
        '[data-clerk-component="SignUp"] .cl-footerAction',
        '[data-clerk-component="SignUp"] .cl-footerAction__text',
        '[data-clerk-component="SignUp"] .cl-footerAction__link',
        '[data-clerk-component="SignUp"] [data-localization-key="signUp.start.actionText"]',
        '[data-clerk-component="SignUp"] [data-localization-key="signUp.start.actionLink"]',
        '[data-clerk-component="SignUp"] a[href*="sign-in"]',
        '[data-clerk-component="SignUp"] a[href*="/sign-in"]',
      ];
      document.querySelectorAll(selectors.join(',')).forEach((el) => {
        const element = el as HTMLElement;
        element.style.display = 'none';
        element.style.height = '0px';
        element.style.padding = '0px';
        element.style.margin = '0px';
        element.style.border = '0px';
        element.setAttribute('aria-hidden', 'true');
      });

      // As a fallback, hide any element whose text is exactly "Sign in"
      const container = document.querySelector('[data-clerk-component="SignUp"]');
      if (container) {
        const allNodes = Array.from(container.querySelectorAll('*')) as HTMLElement[];
        allNodes.forEach((node) => {
          const text = (node.textContent || '').trim().toLowerCase();
          if (text === 'sign in') {
            // Hide the node and its nearest container to remove spacing
            node.style.display = 'none';
            node.setAttribute('aria-hidden', 'true');
            const parent = node.closest('.cl-footer, .cl-cardFooter, .cl-footerAction, div, p, span');
            if (parent && parent instanceof HTMLElement) {
              parent.style.display = 'none';
              parent.setAttribute('aria-hidden', 'true');
            }
          }
        });
      }
    };

    // Run immediately and for a short period to catch late mounts
    hideClerkSignIn();
    const intervalId = setInterval(hideClerkSignIn, 100);
    const timeoutId = setTimeout(() => clearInterval(intervalId), 3000);

    return () => {
      clearInterval(intervalId);
      clearTimeout(timeoutId);
    };
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
        <SignUp 
          routing="path"
          path="/sign-up"
          afterSignUpUrl="/"
          afterSignInUrl="/"
          fallbackRedirectUrl="/"
          appearance={{
            elements: {
              footer: 'hidden',
              footerAction: 'hidden',
              footerActionLink: 'hidden',
              footerActionText: 'hidden',
              cardFooter: 'hidden',
              formButtonPrimary: 
                "bg-blue-600 hover:bg-blue-700 text-sm normal-case",
              card: "shadow-xl border-0",
              headerTitle: "text-gray-900 dark:text-white",
              headerSubtitle: "text-gray-600 dark:text-gray-400",
              socialButtonsBlockButton: 
                "border border-gray-300 hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-700",
              formFieldInput: 
                "border border-gray-300 focus:border-blue-500 dark:border-gray-600 dark:focus:border-blue-400",
              // Disable CAPTCHA completely
              captcha: 'none',
            },
          }}
        />
        <div className="mt-6 text-center relative z-10 w-full max-w-[400px]">
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
