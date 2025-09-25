import type { Metadata } from "next";
import "./globals.css";
import { Inter } from "next/font/google";
import React from "react";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { ThemeProvider } from "@/providers/theme";
import { ClerkProvider } from "@clerk/nextjs";
import { ErrorSuppressor } from "@/components/ErrorSuppressor";

const inter = Inter({
  subsets: ["latin"],
  preload: true,
  display: "swap",
});

export const metadata: Metadata = {
  title: "Booked.AI",
  description: "Booked.AI - AI-Powered Booking Assistant",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              // Completely disable CAPTCHA before anything loads
              (function() {
                // Override CAPTCHA-related functions immediately
                window.grecaptcha = {
                  ready: function(callback) { if (callback) callback(); },
                  execute: function() { return Promise.resolve(''); },
                  render: function() { return 0; },
                  getResponse: function() { return ''; },
                  reset: function() {}
                };
                window.hcaptcha = {
                  ready: function(callback) { if (callback) callback(); },
                  execute: function() { return Promise.resolve(''); },
                  render: function() { return 0; },
                  getResponse: function() { return ''; },
                  reset: function() {}
                };
              })();
            `,
          }}
        />
      </head>
      <body className={inter.className}>
        <ClerkProvider
          publishableKey={process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY}
          signInUrl="/sign-in"
          signUpUrl="/sign-up"
          appearance={{
            elements: {
              captcha: 'none',
              captchaContainer: 'none',
            },
          }}
          localization={{
            locale: 'en',
          }}
          afterSignInUrl="/"
          afterSignUpUrl="/"
        >
          <ErrorSuppressor />
          <ThemeProvider>
            <NuqsAdapter>{children}</NuqsAdapter>
          </ThemeProvider>
          {/* Hidden CAPTCHA elements to prevent "DOM element not found" error */}
          <div id="clerk-captcha" style={{ display: 'none' }}></div>
          <div id="g-recaptcha" style={{ display: 'none' }}></div>
          <div id="h-captcha" style={{ display: 'none' }}></div>
        </ClerkProvider>
      </body>
    </html>
  );
}
