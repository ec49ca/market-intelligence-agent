import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Market Intelligence",
  description: "Watchlist, book, and daily briefings",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" style={{ colorScheme: "light" }}>
      <body
        style={{
          margin: 0,
          background: "#fff",
          color: "#111",
          fontFamily:
            "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif",
        }}
      >
        {children}
      </body>
    </html>
  );
}
