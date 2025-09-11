"use client";

import { UserButton, useAuth } from "@clerk/nextjs";
import { Button } from "@/components/ui/button";
import { useRouter } from "next/navigation";

export function AuthUserButton() {
  const { isSignedIn, isLoaded } = useAuth();
  const router = useRouter();

  if (!isLoaded) {
    return <div className="w-8 h-8" />; // Placeholder while loading
  }

  if (!isSignedIn) {
    // Show Sign In button for guest users
    return (
      <Button 
        variant="outline" 
        size="sm"
        onClick={() => router.push('/sign-in')}
        className="text-sm"
      >
        Sign In
      </Button>
    );
  }

  // Show UserButton for authenticated users
  return (
    <UserButton 
      appearance={{
        elements: {
          avatarBox: "w-8 h-8",
          userButtonPopoverCard: "shadow-lg border-0",
          userButtonPopoverActionButton: "hover:bg-gray-50 dark:hover:bg-gray-700",
          userButtonPopoverActionButtonText: "text-gray-700 dark:text-gray-300",
          userButtonPopoverFooter: "hidden", // Hide the "Manage account" link
        },
      }}
    />
  );
}
