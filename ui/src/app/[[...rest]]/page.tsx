"use client";

import { Thread } from "@/components/thread";
import { StreamProvider } from "@/providers/Stream";
import { ThreadProvider } from "@/providers/Thread";
import { ArtifactProvider } from "@/components/thread/artifact";
import { Toaster } from "@/components/ui/sonner";
import { useAuth } from "@clerk/nextjs";
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
  const { isSignedIn, isLoaded } = useAuth();
  const [showGuestMode, setShowGuestMode] = React.useState(false);
  const router = useRouter();

  // Check sessionStorage for guest mode on component mount
  React.useEffect(() => {
    const guestMode = sessionStorage.getItem('guestMode');
    if (guestMode === 'true') {
      setShowGuestMode(true);
    }
  }, []);

  // Redirect to sign-in page for non-authenticated users
  React.useEffect(() => {
    if (isLoaded && !isSignedIn && !showGuestMode) {
      router.push('/sign-in');
    }
  }, [isLoaded, isSignedIn, showGuestMode, router]);

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
