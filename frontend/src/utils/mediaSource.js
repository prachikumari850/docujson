/** Resolve an image preview to the canonical displayable asset.
 * Raster SVG wrappers reference sibling files, which is unreliable inside an
 * HTMLImageElement; use the retained raster instead. Genuine vector SVGs stay
 * vector and inline SVG content remains supported.
 */
export function resolveMediaSource(item, conversionId, urlForMedia) {
    if (item.type === "svg" && item.content) {
        return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(item.content)}`;
    }
    const filename = item.representation === "svg_vector" && item.svg_filename
        ? item.svg_filename
        : item.filename;
    return urlForMedia(conversionId, filename);
}
