# Clerk Authentication Setup (Minimal)

## Environment Variables

Create a `.env.local` file in the `ui` directory with the following variables:

```env
# Clerk Authentication (Required)
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_your_publishable_key_here
CLERK_SECRET_KEY=sk_test_your_secret_key_here

# Clerk URLs (Optional - defaults to current domain)
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_CLERK_AFTER_SIGN_IN_URL=/
NEXT_PUBLIC_CLERK_AFTER_SIGN_UP_URL=/
```

## Getting Your Clerk Keys

1. Go to [clerk.com](https://clerk.com) and create an account
2. Create a new application
3. Copy your Publishable Key and Secret Key from the API Keys section
4. Replace the placeholder values in your `.env.local` file

## Quick Start

1. **Install dependencies** (already done):
   ```bash
   pnpm add @clerk/nextjs
   ```

2. **Set up environment variables** (see above)

3. **Run the development server**:
   ```bash
   pnpm dev
   ```

4. **Visit your app** at `http://localhost:3000`

## What's Included (Minimal Setup)

- ✅ **ClerkProvider** - Wraps the entire app
- ✅ **Middleware** - Protects routes automatically
- ✅ **Sign-in/Sign-up pages** - Official Clerk components
- ✅ **UserButton** - In the app header for profile management
- ✅ **Automatic redirects** - Clerk handles everything

## What Users Will See

### Unauthenticated Users
- Automatically redirected to `/sign-in`
- Clean Clerk sign-in page with your branding

### Authenticated Users
- Full BookedAI chat interface
- User profile button in the header
- Access to all travel booking features

## Next Steps

1. **Get your Clerk keys** and add them to `.env.local`
2. **Test the authentication flow** by signing up
3. **Customize the appearance** in the sign-in/sign-up components if needed

That's it! Clerk handles all the complexity. 🚀
