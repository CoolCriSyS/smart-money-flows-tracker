import "./globals.css";

export const metadata = {
  title: "Smart Money Flows Tracker",
  description:
    "Where independent smart-money wallets are converging, exiting, and rotating — powered by Nansen.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
