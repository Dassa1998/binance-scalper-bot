import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'Futures Scalper', description: 'Testnet-first Binance USDⓈ-M Futures dashboard' };
export default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang="en"><body>{children}</body></html>; }
