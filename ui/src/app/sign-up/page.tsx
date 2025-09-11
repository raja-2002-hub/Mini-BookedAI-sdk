"use client";

import { SignUp } from '@clerk/nextjs'
import { Button } from '@/components/ui/button'
import React from "react";

export default function SignUpPage() {

  const handleGuestMode = () => {
    // Use sessionStorage instead of localStorage for session-only guest mode
    sessionStorage.setItem('guestMode', 'true');
    // Force a page reload to ensure the guest mode is recognized
    window.location.href = '/';
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
      <div className="w-full max-w-md">
        <SignUp 
          routing="path"
          path="/sign-up"
          appearance={{
            elements: {
              formButtonPrimary: 
                "bg-blue-600 hover:bg-blue-700 text-sm normal-case",
              card: "shadow-xl border-0",
              headerTitle: "text-gray-900 dark:text-white",
              headerSubtitle: "text-gray-600 dark:text-gray-400",
              socialButtonsBlockButton: 
                "border border-gray-300 hover:bg-gray-50 dark:border-gray-600 dark:hover:bg-gray-700",
              formFieldInput: 
                "border border-gray-300 focus:border-blue-500 dark:border-gray-600 dark:focus:border-blue-400",
              footerActionLink: "text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300",
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
