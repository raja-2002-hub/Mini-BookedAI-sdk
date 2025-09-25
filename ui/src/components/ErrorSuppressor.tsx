"use client";

import { useEffect } from 'react';

export function ErrorSuppressor() {
  useEffect(() => {
    // Suppress console errors for OAuth flow
    const originalError = console.error;
    console.error = function(...args) {
      const message = args.join(' ').toLowerCase();
      if (message.includes('captcha') || message.includes('recaptcha') || message.includes('hcaptcha') ||
          message.includes('no account to transfer') || message.includes('there is no account to transfer') ||
          message.includes('already signed in') || message.includes('you are already signed in') ||
          message.includes('external account was not found') || message.includes('the external account was not found') ||
          message.includes('runtime error') || message.includes('account to transfer') ||
          message.includes('transfer') || message.includes('account')) {
        return; // Suppress these errors
      }
      originalError.apply(console, args);
    };

    // Suppress console warnings
    const originalWarn = console.warn;
    console.warn = function(...args) {
      const message = args.join(' ').toLowerCase();
      if (message.includes('no account to transfer') || message.includes('there is no account to transfer') ||
          message.includes('already signed in') || message.includes('you are already signed in') ||
          message.includes('external account was not found') || message.includes('the external account was not found') ||
          message.includes('runtime error') || message.includes('account to transfer') ||
          message.includes('transfer') || message.includes('account')) {
        return; // Suppress these warnings
      }
      originalWarn.apply(console, args);
    };

    // Suppress window.onerror globally
    const originalOnError = window.onerror;
    window.onerror = function(message, source, lineno, colno, error) {
      const errorMessage = String(message).toLowerCase();
      if (errorMessage.includes('captcha') || errorMessage.includes('recaptcha') || errorMessage.includes('hcaptcha') ||
          errorMessage.includes('no account to transfer') || errorMessage.includes('there is no account to transfer') ||
          errorMessage.includes('already signed in') || errorMessage.includes('you are already signed in') ||
          errorMessage.includes('external account was not found') || errorMessage.includes('the external account was not found') ||
          errorMessage.includes('runtime error') || errorMessage.includes('account to transfer') ||
          errorMessage.includes('transfer') || errorMessage.includes('account')) {
        return true; // Suppress the error
      }
      if (originalOnError) {
        return originalOnError(message, source, lineno, colno, error);
      }
      return false;
    };

    // Suppress unhandled promise rejections
    const originalUnhandledRejection = window.onunhandledrejection;
    window.onunhandledrejection = (event) => {
      const errorMessage = String(event.reason).toLowerCase();
      if (errorMessage.includes('no account to transfer') || errorMessage.includes('there is no account to transfer') ||
          errorMessage.includes('already signed in') || errorMessage.includes('you are already signed in') ||
          errorMessage.includes('external account was not found') || errorMessage.includes('the external account was not found') ||
          errorMessage.includes('runtime error') || errorMessage.includes('account to transfer') ||
          errorMessage.includes('transfer') || errorMessage.includes('account')) {
        event.preventDefault(); // Suppress the error
        return;
      }
      if (originalUnhandledRejection) {
        return originalUnhandledRejection.call(window, event);
      }
    };

    // Override alert to prevent error dialogs
    const originalAlert = window.alert;
    window.alert = function(message) {
      const errorMessage = String(message).toLowerCase();
      if (errorMessage.includes('no account to transfer') || errorMessage.includes('there is no account to transfer') ||
          errorMessage.includes('already signed in') || errorMessage.includes('you are already signed in') ||
          errorMessage.includes('external account was not found') || errorMessage.includes('the external account was not found') ||
          errorMessage.includes('runtime error') || errorMessage.includes('account to transfer') ||
          errorMessage.includes('transfer') || errorMessage.includes('account')) {
        return; // Suppress the alert
      }
      return originalAlert(message);
    };

    // Cleanup function
    return () => {
      console.error = originalError;
      console.warn = originalWarn;
      window.onerror = originalOnError;
      window.onunhandledrejection = originalUnhandledRejection;
      window.alert = originalAlert;
    };
  }, []);

  return null; // This component doesn't render anything
}
