# Dark Mode & Theme Switching Implementation Guide

A comprehensive guide for implementing robust dark mode support with theme switching in React applications, covering branding updates and component styling patterns.

## Table of Contents

- [Overview](#overview)
- [Dependencies](#dependencies)
- [Project Structure](#project-structure)
- [CSS Variables Setup](#css-variables-setup)
- [Theme Provider Implementation](#theme-provider-implementation)
- [Theme Switcher Component](#theme-switcher-component)
- [Component Styling Patterns](#component-styling-patterns)
- [Integration Steps](#integration-steps)
- [Common Issues & Solutions](#common-issues--solutions)
- [Best Practices](#best-practices)
- [Testing Checklist](#testing-checklist)

## Overview

This implementation provides:

- **Three theme modes**: Light, Dark, and System (follows OS preference)
- **Seamless switching**: Instant theme changes without page reload
- **Persistent preferences**: Theme choice saved in localStorage
- **SSR compatibility**: Prevents hydration mismatches
- **Accessible theming**: Proper semantic color variables
- **Brand consistency**: Logo and component adaptation across themes

### Architecture

```
Theme System
├── ThemeProvider (next-themes wrapper)
├── ThemeSwitcher (UI component)
├── CSS Variables (semantic color system)
└── Component Integration (theme-aware styling)
```

## Dependencies

### Required Packages

```json
{
  "next-themes": "^0.4.4",
  "tailwindcss": "^3.x.x",
  "lucide-react": "^0.x.x"
}
```

### Tailwind Configuration

```javascript
// tailwind.config.js
module.exports = {
  darkMode: ["class"], // Enable class-based dark mode
  content: [
    "./src/**/*.{ts,tsx,js,jsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Semantic color system
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
      },
    },
  },
};
```

## Project Structure

```
src/
├── providers/
│   └── theme.tsx                 # Theme provider wrapper
├── components/
│   ├── theme-switcher.tsx        # Theme switching component
│   ├── icons/
│   │   └── brand-logo.tsx        # Adaptive brand logo
│   └── ui/                       # Theme-aware UI components
├── app/
│   ├── globals.css               # CSS variables and base styles
│   └── layout.tsx                # Root layout with providers
└── lib/
    └── utils.ts                  # Utility functions
```

## CSS Variables Setup

### Base CSS Variables

```css
/* globals.css */
@import "tailwindcss";

/* Light theme (default) */
:root {
  --background: oklch(1 0 0);                    /* Pure white */
  --foreground: oklch(0.145 0 0);               /* Near black */
  --card: oklch(1 0 0);                         /* White */
  --card-foreground: oklch(0.145 0 0);          /* Dark text */
  --popover: oklch(1 0 0);                      /* White */
  --popover-foreground: oklch(0.145 0 0);       /* Dark text */
  --primary: oklch(0.205 0 0);                  /* Dark primary */
  --primary-foreground: oklch(0.985 0 0);       /* Light text */
  --secondary: oklch(0.97 0 0);                 /* Light gray */
  --secondary-foreground: oklch(0.205 0 0);     /* Dark text */
  --muted: oklch(0.97 0 0);                     /* Light muted */
  --muted-foreground: oklch(0.556 0 0);         /* Medium gray */
  --accent: oklch(0.97 0 0);                    /* Light accent */
  --accent-foreground: oklch(0.205 0 0);        /* Dark text */
  --destructive: oklch(0.577 0.245 27.325);     /* Red */
  --destructive-foreground: oklch(0.985 0 0);   /* White text */
  --border: oklch(0.922 0 0);                   /* Light border */
  --input: oklch(0.922 0 0);                    /* Input border */
  --ring: oklch(0.87 0 0);                      /* Focus ring */
}

/* Dark theme */
.dark {
  --background: oklch(0.145 0 0);               /* Near black */
  --foreground: oklch(0.985 0 0);               /* Near white */
  --card: oklch(0.145 0 0);                     /* Dark card */
  --card-foreground: oklch(0.985 0 0);          /* Light text */
  --popover: oklch(0.145 0 0);                  /* Dark popover */
  --popover-foreground: oklch(0.985 0 0);       /* Light text */
  --primary: oklch(0.985 0 0);                  /* Light primary */
  --primary-foreground: oklch(0.205 0 0);       /* Dark text */
  --secondary: oklch(0.269 0 0);                /* Dark gray */
  --secondary-foreground: oklch(0.985 0 0);     /* Light text */
  --muted: oklch(0.269 0 0);                    /* Dark muted */
  --muted-foreground: oklch(0.708 0 0);         /* Light gray */
  --accent: oklch(0.269 0 0);                   /* Dark accent */
  --accent-foreground: oklch(0.985 0 0);        /* Light text */
  --destructive: oklch(0.396 0.141 25.723);     /* Dark red */
  --destructive-foreground: oklch(0.985 0 0);   /* Light text */
  --border: oklch(0.269 0 0);                   /* Dark border */
  --input: oklch(0.269 0 0);                    /* Dark input */
  --ring: oklch(0.439 0 0);                     /* Dark focus ring */
}

/* Base styles */
@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  
  body {
    @apply bg-background text-foreground;
  }
}
```

### Color System Principles

1. **Semantic naming**: Use purpose-based names (`background`, `foreground`) not color names
2. **Contrast ratios**: Ensure WCAG AA compliance (4.5:1 minimum)
3. **Consistent spacing**: Use OKLCH color space for perceptual uniformity
4. **Hierarchy**: Clear visual hierarchy through color relationships

## Theme Provider Implementation

### Provider Component

```tsx
// src/providers/theme.tsx
"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import { ReactNode } from "react";

interface ThemeProviderProps {
  children: ReactNode;
  [key: string]: any;
}

export function ThemeProvider({ children, ...props }: ThemeProviderProps) {
  return (
    <NextThemesProvider
      attribute="class"           // Use class-based theming
      defaultTheme="system"       // Default to system preference
      enableSystem                // Enable system theme detection
      disableTransitionOnChange   // Prevent flash during SSR
      {...props}
    >
      {children}
    </NextThemesProvider>
  );
}
```

### Root Layout Integration

```tsx
// src/app/layout.tsx
import { ThemeProvider } from "@/providers/theme";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
```

**Key points:**
- `suppressHydrationWarning` prevents SSR mismatch errors
- `attribute="class"` tells next-themes to use CSS classes
- `enableSystem` allows automatic OS preference detection

## Theme Switcher Component

### Cycling Button Implementation

```tsx
// src/components/theme-switcher.tsx
"use client";

import { Moon, Sun, Monitor } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function ThemeSwitcher() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // Prevent hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

  // Show loading state during SSR
  if (!mounted) {
    return (
      <Button variant="ghost" size="icon" className="size-9 text-foreground">
        <Sun className="size-4" />
      </Button>
    );
  }

  const cycleTheme = () => {
    switch (theme) {
      case "light":
        setTheme("dark");
        break;
      case "dark":
        setTheme("system");
        break;
      default:
        setTheme("light");
        break;
    }
  };

  const getIcon = () => {
    switch (theme) {
      case "light":
        return <Sun className="size-4" />;
      case "dark":
        return <Moon className="size-4" />;
      default:
        return <Monitor className="size-4" />;
    }
  };

  const getTooltipText = () => {
    switch (theme) {
      case "light":
        return "Light mode - Click to switch to dark";
      case "dark":
        return "Dark mode - Click to switch to system";
      default:
        return "System mode - Click to switch to light";
    }
  };

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button 
            variant="ghost" 
            size="icon" 
            className="size-9 text-foreground hover:text-accent-foreground" 
            onClick={cycleTheme}
          >
            {getIcon()}
            <span className="sr-only">Toggle theme</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          <p>{getTooltipText()}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
```

### Dropdown Menu Alternative

```tsx
// Alternative: Dropdown menu implementation
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function ThemeSwitcherDropdown() {
  const { theme, setTheme } = useTheme();
  // ... mounted state logic

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon">
          {getIcon()}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTheme("light")}>
          <Sun className="mr-2 h-4 w-4" />
          Light
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          <Moon className="mr-2 h-4 w-4" />
          Dark
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          <Monitor className="mr-2 h-4 w-4" />
          System
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```

## Component Styling Patterns

### Do's and Don'ts

#### ❌ Wrong: Hardcoded Colors

```tsx
// BAD: Hardcoded colors that don't adapt
<div className="bg-white text-black border-gray-200">
  <h1 className="text-gray-900">Title</h1>
  <p className="text-gray-500">Description</p>
</div>
```

#### ✅ Correct: Semantic Variables

```tsx
// GOOD: Theme-aware semantic colors
<div className="bg-card text-card-foreground border-border">
  <h1 className="text-foreground">Title</h1>
  <p className="text-muted-foreground">Description</p>
</div>
```

### Color Mapping Guide

| Purpose | Light Theme | Dark Theme | CSS Variable |
|---------|-------------|------------|--------------|
| Main background | White | Dark gray | `bg-background` |
| Main text | Black | White | `text-foreground` |
| Card background | White | Dark | `bg-card` |
| Card text | Black | White | `text-card-foreground` |
| Muted text | Gray | Light gray | `text-muted-foreground` |
| Borders | Light gray | Dark gray | `border-border` |
| Interactive backgrounds | Light gray | Medium gray | `bg-muted` |

### Complex Component Example

```tsx
// Tool result component with proper theming
export function ToolResult({ message }: { message: ToolMessage }) {
  return (
    <div className="mx-auto grid max-w-3xl gap-2">
      <div className="overflow-hidden rounded-lg border border-border bg-card">
        {/* Header */}
        <div className="border-b border-border bg-muted px-4 py-2">
          <h3 className="font-medium text-card-foreground">
            Tool Result:
            <code className="ml-2 rounded bg-background px-2 py-1 text-muted-foreground">
              {message.name}
            </code>
          </h3>
        </div>
        
        {/* Content */}
        <div className="bg-muted/50 p-3">
          <table className="min-w-full divide-y divide-border">
            <tbody className="divide-y divide-border">
              <tr>
                <td className="px-4 py-2 text-sm font-medium text-foreground">
                  Key
                </td>
                <td className="px-4 py-2 text-sm text-muted-foreground">
                  <code className="rounded bg-background px-2 py-1 text-foreground">
                    Value
                  </code>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        
        {/* Interactive button */}
        <button className="w-full border-t border-border py-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground">
          Expand
        </button>
      </div>
    </div>
  );
}
```

## Integration Steps

### 1. Install Dependencies

```bash
npm install next-themes
# or
yarn add next-themes
```

### 2. Configure Tailwind

Update `tailwind.config.js` with dark mode support and semantic colors.

### 3. Setup CSS Variables

Add CSS variables to `globals.css` for both light and dark themes.

### 4. Create Theme Provider

Implement the `ThemeProvider` wrapper component.

### 5. Add to Root Layout

Integrate provider in your root layout with proper HTML attributes.

### 6. Build Theme Switcher

Create the theme switching UI component.

### 7. Update Components

Convert existing components to use semantic color variables.

### 8. Add Theme Switcher to Layout

Place theme switcher in header/navigation areas.

### 9. Test All States

Verify all three theme modes work correctly.

### 10. Handle Branding Assets

Update logos and brand assets to adapt to themes.

## Common Issues & Solutions

### Issue: Hydration Mismatch

**Problem**: Server and client render different content during SSR.

**Solution**:
```tsx
// Always include suppressHydrationWarning
<html lang="en" suppressHydrationWarning>

// Use mounted state in theme components
const [mounted, setMounted] = useState(false);
useEffect(() => setMounted(true), []);
if (!mounted) return <LoadingSkeleton />;
```

### Issue: Flash of Wrong Theme

**Problem**: Brief flash of default theme before correct theme loads.

**Solution**:
```tsx
// Use disableTransitionOnChange
<ThemeProvider disableTransitionOnChange>
  {children}
</ThemeProvider>

// Add theme detection script to head (optional)
<script dangerouslySetInnerHTML={{
  __html: `
    try {
      if (localStorage.theme === 'dark' || (!localStorage.theme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
    } catch (_) {}
  `
}} />
```

### Issue: Images/Logos Not Adapting

**Problem**: Brand assets don't change with theme.

**Solution**:
```tsx
// Option 1: Conditional rendering
function Logo() {
  const { theme } = useTheme();
  const [mounted, setMounted] = useState(false);
  
  useEffect(() => setMounted(true), []);
  
  if (!mounted) return <LogoSkeleton />;
  
  return (
    <Image
      src={theme === 'dark' ? '/logo-dark.png' : '/logo-light.png'}
      alt="Logo"
    />
  );
}

// Option 2: CSS-based switching
<Image
  src="/logo-light.png"
  className="block dark:hidden"
  alt="Logo"
/>
<Image
  src="/logo-dark.png" 
  className="hidden dark:block"
  alt="Logo"
/>
```

### Issue: Poor Contrast in Dark Mode

**Problem**: Insufficient contrast ratios for accessibility.

**Solution**:
```css
/* Test contrast ratios with tools like WebAIM */
/* Ensure minimum 4.5:1 ratio for normal text */
/* Ensure minimum 3:1 ratio for large text */

.dark {
  --foreground: oklch(0.985 0 0);  /* Very light for good contrast */
  --background: oklch(0.145 0 0);  /* Very dark for good contrast */
}
```

## Best Practices

### 1. Semantic Color System

- Use purpose-based color names (`background`, `foreground`)
- Avoid color-specific names (`blue`, `red`) in favor of semantic ones (`primary`, `destructive`)
- Maintain consistent color relationships across themes

### 2. Accessibility

- Ensure WCAG AA compliance (4.5:1 contrast ratio minimum)
- Test with screen readers and keyboard navigation
- Provide clear visual indicators for theme state

### 3. Performance

- Use CSS variables instead of runtime theme switching
- Minimize layout shifts during theme changes
- Lazy load theme-specific assets when possible

### 4. User Experience

- Remember user's theme preference
- Respect system preferences by default
- Provide clear visual feedback during theme changes
- Consider reduced motion preferences

### 5. Development Workflow

- Test all components in both themes during development
- Use design tokens for consistent theming
- Document theme-specific behavior
- Set up automated testing for theme switching

### 6. Brand Consistency

- Ensure brand assets work in all themes
- Maintain brand color relationships
- Test logo visibility across all backgrounds
- Consider theme-specific brand variations

## Testing Checklist

### Functionality Tests

- [ ] Theme switcher cycles through all three modes
- [ ] System theme detection works correctly
- [ ] Theme preference persists across browser sessions
- [ ] No hydration mismatches in console
- [ ] Theme changes apply immediately

### Visual Tests

- [ ] All text has sufficient contrast in both themes
- [ ] Borders and dividers are visible in both themes
- [ ] Interactive elements (buttons, links) have clear hover states
- [ ] Focus indicators work in both themes
- [ ] Brand assets (logos, icons) are visible in both themes

### Accessibility Tests

- [ ] Screen reader compatibility maintained
- [ ] Keyboard navigation works in both themes
- [ ] Focus indicators meet contrast requirements
- [ ] Color is not the only indicator of information

### Browser Tests

- [ ] Works in Chrome, Firefox, Safari, Edge
- [ ] Mobile browsers support theme switching
- [ ] System preference changes are detected
- [ ] No console errors in any browser

### Edge Cases

- [ ] Theme switching works with JavaScript disabled
- [ ] Handles missing localStorage gracefully
- [ ] Works when system preference changes while app is open
- [ ] Theme switcher is accessible in all application states

---

## Conclusion

This guide provides a complete implementation strategy for robust dark mode support. The key principles are:

1. **Use semantic CSS variables** for maintainable theming
2. **Implement proper SSR handling** to prevent hydration issues
3. **Follow accessibility best practices** for inclusive design
4. **Test thoroughly** across all themes and browsers
5. **Maintain brand consistency** across all themes

By following this guide, you'll have a professional, accessible, and maintainable dark mode implementation that enhances user experience while maintaining brand integrity.

For questions or improvements to this guide, please refer to the implementation examples in this codebase. 