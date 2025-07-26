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

  // Avoid hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

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