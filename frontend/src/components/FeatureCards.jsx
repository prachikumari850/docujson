import { CodeXml, Image, Languages, MessageCircleQuestion } from "lucide-react";

const FEATURES = [
    {
        icon: MessageCircleQuestion,
        title: "Questions & Answers",
        subtitle: "Extraction",
        card: "from-pink-light/90 to-white/80",
        badge: "bg-pink-light text-brand-pink",
    },
    {
        icon: Image,
        title: "Diagrams & Figures",
        subtitle: "(PNG/JPEG)",
        card: "from-lavender/80 to-white/80",
        badge: "bg-lavender text-deep-purple",
    },
    {
        icon: CodeXml,
        title: "SVG Graphics",
        subtitle: "(Vector)",
        card: "from-sky-soft/80 to-white/80",
        badge: "bg-sky-soft text-sky-600",
    },
    {
        icon: Languages,
        title: "Bilingual Content",
        subtitle: "(English / Hindi)",
        card: "from-pink-light/90 to-white/80",
        badge: "bg-pink-light text-brand-pink",
    },
];

export default function FeatureCards() {
    return (
        <section id="features" className="mx-auto mt-12 grid w-full max-w-6xl gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, subtitle, card, badge }) => (
                <div
                    key={title}
                    className={`flex items-center gap-4 rounded-2xl bg-linear-to-br ${card} p-5 shadow-[0_12px_30px_-16px_rgba(73,50,140,0.35)] ring-1 ring-white`}
                >
                    <span className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl ${badge}`}>
                        <Icon size={28} strokeWidth={1.8} />
                    </span>
                    <p className="text-[15px] leading-snug text-navy">
                        <span className="block font-bold">{title}</span>
                        <span className="block font-medium text-navy/80">{subtitle}</span>
                    </p>
                </div>
            ))}
        </section>
    );
}