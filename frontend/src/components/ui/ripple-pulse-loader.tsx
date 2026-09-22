"use client";

import type { CSSProperties } from "react";
import { cn } from "@/lib/utils";

// 内联闪电徽标，避免外部 CDN 依赖
const LogoMark = () => (
  <svg viewBox="0 0 24 24" fill="none" className="svg" aria-hidden="true">
    <path
      d="M13 2 4.5 13.5H11L9.5 22 19.5 9.5H12.5L13 2Z"
      fill="currentColor"
      stroke="currentColor"
      strokeWidth="0.5"
      strokeLinejoin="round"
    />
  </svg>
);

type RipplePulseLoaderProps = {
  className?: string;
  size?: number;
};

export function RipplePulseLoader({ className, size = 150 }: RipplePulseLoaderProps) {
  return (
    <div
      className={cn("ripple-pulse-loader", className)}
      style={{ "--ripple-size": `${size}px` } as CSSProperties}
      role="status"
      aria-label="Loading"
    >
      <div className="box">
        <div className="logo">
          <LogoMark />
        </div>
      </div>
      <div className="box" />
      <div className="box" />
      <div className="box" />
      <div className="box" />
    </div>
  );
}

export default RipplePulseLoader;
