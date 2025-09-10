"use client";

import { Thread } from "@/components/thread";
import { StreamProvider } from "@/providers/Stream";
import { ThreadProvider } from "@/providers/Thread";
import { ArtifactProvider } from "@/components/thread/artifact";
import { Toaster } from "@/components/ui/sonner";
import { SignInButton } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { useAuth } from "@clerk/nextjs";
import React from "react";

function AppContent() {
  const { isSignedIn, isLoaded } = useAuth();
  const [showGuestMode, setShowGuestMode] = React.useState(false);

  if (!isLoaded) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!isSignedIn && !showGuestMode) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
        <div className="w-full max-w-md">
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-bold text-gray-900 dark:text-white">
              Welcome to Booked.AI
            </h1>
            <p className="mt-2 text-gray-600 dark:text-gray-400">
              Sign in to your account to continue
            </p>
          </div>
          <div className="space-y-4">
            <SignInButton mode="modal">
              <Button className="w-full bg-blue-600 hover:bg-blue-700">
                Sign In
              </Button>
            </SignInButton>
            <Button
              onClick={() => setShowGuestMode(true)}
              variant="outline"
              className="w-full"
            >
              Continue as Guest
            </Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <ThreadProvider>
      <StreamProvider>
        <ArtifactProvider>
          <Thread />
        </ArtifactProvider>
      </StreamProvider>
    </ThreadProvider>
  );
}

export default function DemoPage(): React.ReactNode {
  return (
    <React.Suspense fallback={<div>Loading (layout)...</div>}>
      <Toaster />
      <AppContent />
    </React.Suspense>
  );
}
