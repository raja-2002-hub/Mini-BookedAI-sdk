import Image from "next/image";

export function BookedLogoSVG({
  className,
  height = 32,
}: {
  height?: number;
  className?: string;
}) {
  return (
    <Image
      src="/logo-booked-hq.png"
      alt="Booked.AI Logo"
      width={0}
      height={height}
      className={`w-auto ${className || ''}`}
      style={{ 
        height: `${height}px`,
        imageRendering: 'crisp-edges'
      }}
      unoptimized
      priority
    />
  );
} 