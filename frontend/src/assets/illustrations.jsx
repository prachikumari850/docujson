export function LogoMark({ className }) {
    return (
        <svg viewBox="0 0 48 48" fill="none" className={className} aria-hidden="true">
            <defs>
                <linearGradient id="logo-gradient" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0" stopColor="#F20B83" />
                    <stop offset="1" stopColor="#FF7518" />
                </linearGradient>
            </defs>
            <path
                d="M12 5h17l9 9v26a3 3 0 0 1-3 3H12a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3z"
                stroke="url(#logo-gradient)"
                strokeWidth="3.5"
                strokeLinejoin="round"
            />
            <path d="M29 5v9h9" stroke="url(#logo-gradient)" strokeWidth="3.5" strokeLinejoin="round" />
            <path d="M16 23h16M16 29h16M16 35h10" stroke="url(#logo-gradient)" strokeWidth="3" strokeLinecap="round" />
        </svg>
    );
}

export function CloudUploadArt({ className }) {
    return (
        <svg viewBox="0 0 160 110" fill="none" className={className} aria-hidden="true">
            <defs>
                <linearGradient id="cloud-gradient" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0" stopColor="#FF7518" />
                    <stop offset="1" stopColor="#F20B83" />
                </linearGradient>
            </defs>
            <ellipse cx="50" cy="82" rx="40" ry="18" fill="#FFE6F2" opacity="0.9" />
            <ellipse cx="112" cy="78" rx="38" ry="20" fill="#FFE6F2" opacity="0.7" />
            <path
                d="M52 80H46a22 22 0 0 1-3-43.8A32 32 0 0 1 104 34a23 23 0 0 1 10 46h-8"
                stroke="url(#cloud-gradient)"
                strokeWidth="7"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
            <path
                d="M79 92V50M62 66l17-17 17 17"
                stroke="url(#cloud-gradient)"
                strokeWidth="7"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
}

export function DocsArt({ className }) {
    return (
        <svg viewBox="0 0 280 280" fill="none" className={className} aria-hidden="true">
            <defs>
                <linearGradient id="docs-front-gradient" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0" stopColor="#F6E9FF" />
                    <stop offset="1" stopColor="#E2CBFF" />
                </linearGradient>
                <filter id="docs-shadow" x="-20%" y="-20%" width="145%" height="150%">
                    <feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#8A5CFF" floodOpacity="0.25" />
                </filter>
            </defs>
            <g transform="rotate(-14 90 190)" filter="url(#docs-shadow)">
                <rect x="26" y="88" width="134" height="170" rx="14" fill="#FBF8FF" stroke="#E4D6FF" />
                <path d="M46 114h72M46 130h92M46 146h82" stroke="#DCCBFA" strokeWidth="6" strokeLinecap="round" />
                <rect x="48" y="166" width="58" height="26" rx="6" fill="#F20B83" />
                <text x="77" y="184" textAnchor="middle" fontSize="14" fontWeight="700" fill="#fff" fontFamily="Poppins, sans-serif">
                    PDF
                </text>
                <path d="M46 210h86M46 226h66" stroke="#DCCBFA" strokeWidth="6" strokeLinecap="round" />
            </g>
            <g transform="rotate(8 190 150)" filter="url(#docs-shadow)">
                <path
                    d="M130 36h66l36 36v146a14 14 0 0 1-14 14h-88a14 14 0 0 1-14-14V50a14 14 0 0 1 14-14z"
                    fill="url(#docs-front-gradient)"
                    stroke="#E4D6FF"
                />
                <path d="M196 36v26a10 10 0 0 0 10 10h26z" fill="#fff" opacity="0.75" />
                <path d="M152 138l26-46 26 46z" fill="#EBD9FF" stroke="#8A5CFF" strokeWidth="2.5" strokeLinejoin="round" />
                <circle cx="152" cy="138" r="3.5" fill="#8A5CFF" />
                <circle cx="178" cy="92" r="3.5" fill="#8A5CFF" />
                <circle cx="204" cy="138" r="3.5" fill="#8A5CFF" />
                <path d="M148 160h70M148 174h56" stroke="#D3BDF7" strokeWidth="6" strokeLinecap="round" />
                <rect x="150" y="192" width="64" height="26" rx="6" fill="#2F6BFF" />
                <text x="182" y="210" textAnchor="middle" fontSize="14" fontWeight="700" fill="#fff" fontFamily="Poppins, sans-serif">
                    DOCX
                </text>
            </g>
            <path d="M236 34l5-14M250 48l14-6M224 22l-2-12" stroke="#FF7518" strokeWidth="3.5" strokeLinecap="round" />
        </svg>
    );
}

export function JsonArt({ className }) {
    return (
        <svg viewBox="0 0 300 240" fill="none" className={className} aria-hidden="true">
            <defs>
                <linearGradient id="json-arrow-gradient" x1="0" y1="1" x2="1" y2="0">
                    <stop offset="0" stopColor="#FF7518" />
                    <stop offset="1" stopColor="#F20B83" />
                </linearGradient>
                <filter id="json-shadow" x="-20%" y="-20%" width="145%" height="150%">
                    <feDropShadow dx="0" dy="14" stdDeviation="12" floodColor="#3A2E6E" floodOpacity="0.35" />
                </filter>
            </defs>
            <path d="M8 96C28 66 62 50 98 56" stroke="url(#json-arrow-gradient)" strokeWidth="4.5" strokeLinecap="round" />
            <path d="M84 40l18 14-20 10" stroke="url(#json-arrow-gradient)" strokeWidth="4.5" strokeLinecap="round" strokeLinejoin="round" />
            <g transform="rotate(7 180 130)" filter="url(#json-shadow)">
                <rect x="70" y="60" width="200" height="150" rx="18" fill="#463A82" />
                <path d="M70 78a18 18 0 0 1 18-18h164a18 18 0 0 1 18 18v14H70z" fill="#3A2E6E" />
                <text x="88" y="84" fontSize="14" fontWeight="600" fill="#fff" fontFamily="Poppins, sans-serif">
                    {"{ }"} JSON
                </text>
                <rect x="88" y="108" width="64" height="7" rx="3.5" fill="#FFB020" />
                <rect x="104" y="124" width="46" height="7" rx="3.5" fill="#3DD6D0" />
                <rect x="158" y="124" width="82" height="7" rx="3.5" fill="#3DD6D0" />
                <rect x="104" y="140" width="64" height="7" rx="3.5" fill="#F20B83" />
                <rect x="104" y="156" width="52" height="7" rx="3.5" fill="#FF5DA2" />
                <rect x="88" y="172" width="42" height="7" rx="3.5" fill="#A78BFA" />
                <rect x="138" y="172" width="60" height="7" rx="3.5" fill="#C14BFF" />
            </g>
            <path d="M244 40l-4-14M258 52l14-8M228 28l8-12" stroke="#FF7518" strokeWidth="3.5" strokeLinecap="round" />
        </svg>
    );
}

export function Decor() {
    return (
        <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
            <svg className="absolute -left-8 top-0 w-72 opacity-90 sm:w-96" viewBox="0 0 300 200" fill="none">
                <defs>
                    <linearGradient id="decor-top-left" x1="0" y1="0" x2="1" y2="1">
                        <stop offset="0" stopColor="#E9DFFF" />
                        <stop offset="1" stopColor="#F5EEFF" stopOpacity="0" />
                    </linearGradient>
                </defs>
                <path d="M0 0H220C190 60 120 120 0 160Z" fill="url(#decor-top-left)" />
            </svg>

            <svg className="absolute -right-10 top-[38%] hidden w-80 opacity-70 md:block" viewBox="0 0 300 300" fill="none">
                <defs>
                    <linearGradient id="decor-mid-right" x1="1" y1="0" x2="0" y2="1">
                        <stop offset="0" stopColor="#FFD3EA" />
                        <stop offset="1" stopColor="#F5EEFF" stopOpacity="0" />
                    </linearGradient>
                </defs>
                <path d="M300 0C220 40 200 120 230 180C250 220 280 250 300 270Z" fill="url(#decor-mid-right)" />
            </svg>

            <svg className="absolute bottom-0 left-0 w-64 sm:w-[26rem]" viewBox="0 0 400 400" fill="none">
                <defs>
                    <linearGradient id="decor-bottom-left" x1="0" y1="0" x2="1" y2="1">
                        <stop offset="0" stopColor="#FFB347" />
                        <stop offset="0.55" stopColor="#FF6B8B" />
                        <stop offset="1" stopColor="#E86AD6" />
                    </linearGradient>
                    <linearGradient id="decor-bottom-left-soft" x1="0" y1="0" x2="1" y2="1">
                        <stop offset="0" stopColor="#FFD3EA" />
                        <stop offset="1" stopColor="#E9DFFF" />
                    </linearGradient>
                </defs>
                <path d="M0 140C70 160 120 230 160 290C190 335 250 375 310 400H0Z" fill="url(#decor-bottom-left-soft)" opacity="0.8" />
                <path d="M0 210C50 225 90 280 120 330C135 355 160 380 190 400H0Z" fill="url(#decor-bottom-left)" />
            </svg>

            <svg className="absolute bottom-0 right-0 w-64 sm:w-[26rem]" viewBox="0 0 400 400" fill="none">
                <defs>
                    <linearGradient id="decor-bottom-right" x1="1" y1="0" x2="0" y2="1">
                        <stop offset="0" stopColor="#FFC4E1" />
                        <stop offset="1" stopColor="#F58FC8" />
                    </linearGradient>
                </defs>
                <path d="M400 90C330 110 280 180 250 250C225 310 180 365 120 400H400Z" fill="url(#decor-bottom-right)" opacity="0.75" />
            </svg>
        </div>
    );
}