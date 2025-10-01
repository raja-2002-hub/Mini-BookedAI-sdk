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
  const [isMounted, setIsMounted] = React.useState(false);
  const router = useRouter();

  // Handle hydration
  React.useEffect(() => {
    setIsMounted(true);
  }, []);

  // Check authentication state and guest mode
  React.useEffect(() => {
    if (!isMounted || !isLoaded) return;

    if (isSignedIn) {
      if (typeof window !== 'undefined') {
        sessionStorage.removeItem('guestMode');
      }
      setShowGuestMode(false);
    } else {
      const guestMode = typeof window !== 'undefined' ? sessionStorage.getItem('guestMode') === 'true' : false;
      setShowGuestMode(guestMode);
      
      // Only redirect to sign-in if not in guest mode and no URL params (not from OAuth)
      if (!guestMode && typeof window !== 'undefined') {
        const urlParams = new URLSearchParams(window.location.search);
        const hasUrlParams = urlParams.toString().length > 0;
        
        if (!hasUrlParams) {
          router.push('/sign-in');
        }
      }
    }
  }, [isLoaded, isSignedIn, router, isMounted]);

  // Periodically check if user becomes signed in and remove guest mode
  React.useEffect(() => {
    if (!isMounted) return;
    
    const checkAuthInterval = setInterval(() => {
      if (isSignedIn && typeof window !== 'undefined') {
        const guestMode = sessionStorage.getItem('guestMode');
        if (guestMode === 'true') {
          console.log('User is now signed in, removing guest mode');
          sessionStorage.removeItem('guestMode');
          setShowGuestMode(false);
          // Force a re-render to update the UI
          window.location.reload();
        }
      }
    }, 500);
    
    return () => clearInterval(checkAuthInterval);
  }, [isMounted, isSignedIn]);

  // Show loading state during hydration
  if (!isLoaded || !isMounted) {
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
