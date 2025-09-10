"use client";

import { useAuth } from "@clerk/nextjs";
import { SignInButton, SignUpButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";

export function GuestBanner() {
  const { isSignedIn, isLoaded } = useAuth();

  // Don't show banner if not loaded or if user is signed in
  if (!isLoaded || isSignedIn) {
    return null;
  }

  return (
    <div className="bg-blue-50 border-b border-blue-200 dark:bg-blue-900/20 dark:border-blue-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between py-3">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
            </div>
            <div className="ml-3">
              <p className="text-sm text-blue-700 dark:text-blue-300">
                <span className="font-medium">You're browsing as a guest.</span>
                <span className="ml-1">Sign up to save your conversations and access your account.</span>
              </p>
            </div>
          </div>
          <div className="flex items-center space-x-3">
            <SignInButton mode="modal">
              <Button variant="outline" size="sm">
                Sign In
              </Button>
            </SignInButton>
            <SignUpButton mode="modal">
              <Button size="sm">
                Sign Up
              </Button>
            </SignUpButton>
          </div>
        </div>
      </div>
    </div>
  );
}
