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
    const [expanded, setExpanded] = useState(false);

    return (
        <figure className="overflow-hidden rounded-xl border border-lavender bg-white">
            <div className="flex min-h-32 items-center justify-center bg-lavender-light/60 p-2">
                {broken ? (
                    <span className="flex items-center gap-2 text-sm text-navy/60">
                        <ImageOff size={18} /> Preview unavailable
                    </span>
                ) : (
                    <button type="button" onClick={() => setExpanded(true)} className="max-w-full cursor-zoom-in" aria-label={`Open larger view of ${item.filename}`}>
                        <img
                            src={resolveSource(item, conversionId)}
                            alt={item.filename}
                            loading="lazy"
                            onError={() => setBroken(true)}
                            className="max-h-56 w-auto max-w-full object-contain"
                        />
                    </button>
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
            {expanded && !broken && (
                <div role="dialog" aria-modal="true" aria-label={`Large preview of ${item.filename}`} onClick={() => setExpanded(false)} className="fixed inset-0 z-50 flex items-center justify-center bg-navy/80 p-4">
                    <button type="button" onClick={() => setExpanded(false)} className="absolute right-5 top-5 rounded-full bg-white px-4 py-2 text-sm font-semibold text-navy">Close</button>
                    <img src={resolveSource(item, conversionId)} alt={item.filename} onClick={(event) => event.stopPropagation()} className="max-h-[88vh] max-w-[92vw] object-contain" />
                </div>
            )}
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
