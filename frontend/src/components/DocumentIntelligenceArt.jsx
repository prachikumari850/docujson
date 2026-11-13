
import { FileText, Braces, Image, CheckCircle2 } from "lucide-react";

export default function DocumentIntelligenceArt() {
    return (
        <div className="relative mx-auto w-full max-w-2xl">
            <div className="absolute inset-8 rounded-full bg-linear-to-br from-lavender/70 via-pink-light/50 to-sky-soft/60 blur-3xl" />

            <svg
                viewBox="0 0 680 460"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
                className="relative z-10 w-full"
                role="img"
                aria-label="Document intelligence workflow from uploaded files through AI extraction and structured content"
            >
                <defs>
                    <linearGradient id="documentGradient" x1="0" y1="0" x2="1" y2="1">
                        <stop stopColor="#FFF1E8" />
                        <stop offset="1" stopColor="#FFE1D4" />
                    </linearGradient>
                    <linearGradient id="aiGradient" x1="0" y1="0" x2="1" y2="1">
                        <stop stopColor="#E9DFFF" />
                        <stop offset="1" stopColor="#F9E5F4" />
                    </linearGradient>
                    <linearGradient id="jsonGradient" x1="0" y1="0" x2="1" y2="1">
                        <stop stopColor="#FFE5ED" />
                        <stop offset="1" stopColor="#F3E7FF" />
                    </linearGradient>
                    <filter id="cardShadow" x="-30%" y="-30%" width="160%" height="170%">
                        <feDropShadow dx="0" dy="12" stdDeviation="12" floodColor="#49328C" floodOpacity="0.12" />
                    </filter>
                </defs>

                <path
                    d="M178 218 C220 218 222 218 258 218"
                    stroke="#B7A2E8"
                    strokeWidth="3"
                    strokeDasharray="7 8"
                    strokeLinecap="round"
                />
                <path
                    d="M423 218 C459 218 461 218 499 218"
                    stroke="#E8A2C3"
                    strokeWidth="3"
                    strokeDasharray="7 8"
                    strokeLinecap="round"
                />
                <path d="M248 210 L259 218 L248 226" stroke="#9B83D1" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M489 210 L500 218 L489 226" stroke="#D77FA9" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />

                <g filter="url(#cardShadow)">
                    <rect x="35" y="120" width="145" height="190" rx="22" fill="white" />
                    <rect x="35.75" y="120.75" width="143.5" height="188.5" rx="21.25" stroke="#E7DDF7" strokeWidth="1.5" />
                    <rect x="65" y="145" width="85" height="105" rx="10" fill="url(#documentGradient)" />
                    <path d="M121 145 V170 H150" stroke="#F3B99C" strokeWidth="2" />
                    <path d="M121 145 L150 170" stroke="#F3B99C" strokeWidth="2" />
                    <path d="M81 184 H133 M81 197 H133 M81 210 H121" stroke="#D98F6D" strokeWidth="5" strokeLinecap="round" />
                    <rect x="59" y="266" width="97" height="25" rx="12.5" fill="#FFF0E8" />
                    <text x="107.5" y="283" textAnchor="middle" fill="#C76A3C" fontSize="11" fontWeight="600">DOCUMENTS</text>
                </g>

                <g filter="url(#cardShadow)">
                    <rect x="258" y="120" width="165" height="190" rx="24" fill="white" />
                    <rect x="258.75" y="120.75" width="163.5" height="188.5" rx="23.25" stroke="#DED2F6" strokeWidth="1.5" />
                    <rect x="298" y="145" width="85" height="85" rx="24" fill="url(#aiGradient)" />
                    <path d="M340.5 161 V174 M340.5 200 V213 M316 187 H329 M352 187 H365" stroke="#8A6ACB" strokeWidth="4" strokeLinecap="round" />
                    <path d="M340.5 174 C333 174 327.5 179.5 327.5 187 C327.5 194.5 333 200 340.5 200 C348 200 353.5 194.5 353.5 187 C353.5 179.5 348 174 340.5 174Z" stroke="#8A6ACB" strokeWidth="3" />
                    <circle cx="340.5" cy="187" r="5" fill="#F09BBE" />
                    <text x="340.5" y="257" textAnchor="middle" fill="#49328C" fontSize="14" fontWeight="700">AI PROCESSING</text>
                    <text x="340.5" y="278" textAnchor="middle" fill="#81749F" fontSize="10" fontWeight="500">Extract · Understand</text>
                    <text x="340.5" y="293" textAnchor="middle" fill="#81749F" fontSize="10" fontWeight="500">Structure · Validate</text>
                </g>

                <g filter="url(#cardShadow)">
                    <rect x="500" y="120" width="145" height="190" rx="22" fill="white" />
                    <rect x="500.75" y="120.75" width="143.5" height="188.5" rx="21.25" stroke="#F0D5E4" strokeWidth="1.5" />
                    <rect x="530" y="145" width="85" height="105" rx="10" fill="url(#jsonGradient)" />
                    <path d="M553 176 C544 176 544 190 553 190 M592 176 C601 176 601 190 592 190" stroke="#C36D9A" strokeWidth="3" strokeLinecap="round" />
                    <path d="M566 169 L559 198 M579 169 L572 198" stroke="#9B75CE" strokeWidth="3" strokeLinecap="round" />
                    <path d="M549 210 H596" stroke="#D9A0BC" strokeWidth="4" strokeLinecap="round" />
                    <rect x="522" y="266" width="101" height="25" rx="12.5" fill="#FCEAF2" />
                    <text x="572.5" y="283" textAnchor="middle" fill="#B85D8A" fontSize="11" fontWeight="600">STRUCTURED</text>
                </g>

                <g filter="url(#cardShadow)">
                    <rect x="220" y="25" width="115" height="48" rx="15" fill="white" />
                    <circle cx="243" cy="49" r="11" fill="#E8DFFF" />
                    <path d="M239 49 L242 52 L248 45" stroke="#8062C1" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <text x="261" y="53" fill="#49328C" fontSize="11" fontWeight="600">AI EXTRACT</text>
                </g>

                <g filter="url(#cardShadow)">
                    <rect x="400" y="365" width="125" height="48" rx="15" fill="white" />
                    <circle cx="424" cy="389" r="11" fill="#FFE3EC" />
                    <path d="M419 389 L423 393 L430 385" stroke="#C76D97" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <text x="442" y="393" fill="#49328C" fontSize="11" fontWeight="600">REVIEW READY</text>
                </g>

                <circle cx="90" cy="65" r="7" fill="#F4B18D" opacity="0.8" />
                <circle cx="580" cy="65" r="10" fill="#D9C8F5" opacity="0.9" />
                <circle cx="600" cy="370" r="6" fill="#F0A6C5" opacity="0.8" />
                <circle cx="125" cy="390" r="9" fill="#D8C9F4" opacity="0.8" />
                <path d="M178 91 L188 101 M188 91 L178 101" stroke="#E8A0C0" strokeWidth="2.5" strokeLinecap="round" />
                <path d="M555 330 L565 340 M565 330 L555 340" stroke="#B59BDF" strokeWidth="2.5" strokeLinecap="round" />
            </svg>

            <div className="absolute -bottom-2 left-1/2 z-20 flex -translate-x-1/2 items-center gap-2 rounded-full border border-white bg-white/95 px-4 py-2.5 shadow-[0_10px_30px_-12px_rgba(73,50,140,0.35)]">
                <CheckCircle2 size={17} className="text-emerald-500" />
                <span className="whitespace-nowrap text-xs font-semibold text-navy sm:text-sm">
                    From documents to structured knowledge
                </span>
            </div>
        </div>
    );
}
