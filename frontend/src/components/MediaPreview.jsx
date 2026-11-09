import { useState } from "react";
import { ImageOff } from "lucide-react";
import { mediaUrl } from "../services/converterApi";

function resolveSource(item, conversionId) {
    if (item.type === "svg" && item.content) {
        return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(item.content)}`;
    }
    return mediaUrl(conversionId, item.filename);
}

function MediaItem({ item, conversionId }) {
    const [broken, setBroken] = useState(false);

    return (
        <figure className="overflow-hidden rounded-xl border border-lavender bg-white">
            <div className="flex min-h-32 items-center justify-center bg-lavender-light/60 p-2">
                {broken ? (
                    <span className="flex items-center gap-2 text-sm text-navy/60">
                        <ImageOff size={18} /> Preview unavailable
                    </span>
                ) : (
                    <img
                        src={resolveSource(item, conversionId)}
                        alt={item.filename}
                        loading="lazy"
                        onError={() => setBroken(true)}
                        className="max-h-56 w-auto max-w-full object-contain"
                    />
                )}
            </div>
            <figcaption className="flex items-center justify-between gap-2 px-3 py-2 text-xs text-navy/70">
                <span className="truncate font-semibold" title={item.filename}>
                    {item.filename}
                </span>
                <span className="shrink-0 uppercase">
                    {item.type}
                    {item.source_page ? ` · p${item.source_page}` : ""}
                </span>
            </figcaption>
        </figure>
    );
}

export default function MediaPreview({ media, conversionId }) {
    if (!media?.length) return null;

    return (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
            {media.map((item) => (
                <MediaItem key={item.asset_id ?? item.filename} item={item} conversionId={conversionId} />
            ))}
        </div>
    );
}