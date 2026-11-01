const PATHS: Record<string, string> = {
  home: "M3 11 12 3l9 8M5 9.5V21h5v-6h4v6h5V9.5",
  list: "M9 6h12M9 12h12M9 18h12M4 6h.01M4 12h.01M4 18h.01",
  bars: "M5 20v-6M12 20V6M19 20v-9",
  doc: "M6 3h8l5 5v13H6zM14 3v5h5M9 13h7M9 17h7",
  user: "M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9ZM4 21c.6-4.4 3.8-7 8-7s7.4 2.6 8 7",
  chevron: "m9 5 7 7-7 7",
  drop: "M12 3s7 7.2 7 12a7 7 0 0 1-14 0c0-4.800 7-12 7-12Z",
  eye: "M2 12s3.600-7 10-7 10 7 10 7-3.600 7-10 7-10-7-10-7ZM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
  pulse: "M3 12h4l2-5 4 10 2-5h6",
  flask: "M9 3h6M10 3v6l-5.500 9.500A1.700 1.700 0 0 0 6 21h12a1.700 1.700 0 0 0 1.500-2.500L14 9V3M7.500 15h9",
  heart: "M12 20.500S3.500 15.500 3.500 9.300A4.800 4.800 0 0 1 12 6.300a4.800 4.800 0 0 1 8.500 3c0 6.200-8.500 11.200-8.500 11.200Z",
  moon: "M20 14.500A8.500 8.500 0 1 1 9.500 4a7 7 0 0 0 10.500 10.500Z",
  walk: "M13 5a1.500 1.500 0 1 0 0-3 1.500 1.500 0 0 0 0 3ZM9 22l3-7-3-3 2-5 3 3 3 1M8 11l3-4M15 22l-3-7",
  chat: "M4 5h16v12H9l-5 4zM8 11h.01M12 11h.01M16 11h.01",
  shield: "M12 3 5 6v6c0 4.500 3 7.500 7 9 4-1.500 7-4.500 7-9V6z",
  send: "M12 20V5M5 12l7-7 7 7",
  plus: "M12 5v14M5 12h14",
  check: "m5 12.500 4.500 4.500L19 7.500",
  alert: "M12 8v5M12 16.500h.01M10.300 3.900 2.400 17.600A2 2 0 0 0 4.100 20.600h15.800a2 2 0 0 0 1.700-3L13.700 3.900a2 2 0 0 0-3.400 0Z",
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 24 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

export function Logo({ size = 34 }: { size?: number }) {
  return <img src="/logo.svg" width={size} height={size} alt="Vitala" />;
}
