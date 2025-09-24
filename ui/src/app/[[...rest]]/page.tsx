"use client";

import { Thread } from "@/components/thread";
import { StreamProvider } from "@/providers/Stream";
import { ThreadProvider } from "@/providers/Thread";
import { ArtifactProvider } from "@/components/thread/artifact";
import { Toaster } from "@/components/ui/sonner";
import { useAuth, useUser } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import React from "react";

function AppContent() {
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

export default function CatchAllPage(): React.ReactNode {
  const { isSignedIn, isLoaded, sessionId } = useAuth();
  const { user } = useUser();
  const [showGuestMode, setShowGuestMode] = React.useState(false);
  const router = useRouter();

  // Check authentication state and guest mode with session sync delay
  React.useEffect(() => {
    // Delay to ensure Clerk session sync
    const timer = setTimeout(() => {
      console.log('Auth Debug:', {
        isLoaded,
        isSignedIn,
        sessionId,
        user: user
          ? {
              id: user.id,
              firstName: user.firstName,
              emailAddresses: user.emailAddresses.map(email => email.emailAddress),
              externalAccounts: user.externalAccounts.map(account => ({
                provider: account.provider,
                emailAddress: account.emailAddress,
              })),
            }
          : null,
        showGuestMode,
        guestModeFromStorage: sessionStorage.getItem('guestMode'),
      });

      if (isLoaded) {
        if (isSignedIn) {
          sessionStorage.removeItem('guestMode');
          setShowGuestMode(false);
        } else {
          const guestMode = sessionStorage.getItem('guestMode') === 'true';
          setShowGuestMode(guestMode);
          if (!guestMode) {
            router.push('/sign-in');
          }
        }
      }
    }, 500); // Wait 0.5s for session sync

    return () => clearTimeout(timer);
  }, [isLoaded, isSignedIn, user, sessionId, router]);

  if (!isLoaded) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  // If user is signed in or in guest mode, show the app
  if (isSignedIn || showGuestMode) {
    return (
      <React.Suspense fallback={<div>Loading (layout)...</div>}>
        <Toaster />
        <AppContent />
      </React.Suspense>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
    </div>
  );
}
