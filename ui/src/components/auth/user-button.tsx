import { UserButton } from "@clerk/nextjs";

export function AuthUserButton() {
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
      afterSignOutUrl="/"
    />
  );
}
