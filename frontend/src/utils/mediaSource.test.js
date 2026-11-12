import test from "node:test";
import assert from "node:assert/strict";
import { resolveMediaSource } from "./mediaSource.js";

const url = (conversionId, filename) => `/media/${conversionId}/${filename}`;

test("SVG raster wrapper previews use the original sibling raster directly", () => {
    const source = resolveMediaSource({
        filename: "p3_img1.png",
        svg_filename: "p3_img1.png.wrapper.svg",
        representation: "svg_wrapper",
    }, "conversion", url);
    assert.equal(source, "/media/conversion/p3_img1.png");
});

test("genuine vector SVG preview uses its SVG asset", () => {
    const source = resolveMediaSource({
        filename: "diagram.png",
        svg_filename: "diagram.svg",
        representation: "svg_vector",
    }, "conversion", url);
    assert.equal(source, "/media/conversion/diagram.svg");
});

test("inline SVG content remains supported", () => {
    const source = resolveMediaSource({ type: "svg", content: "<svg/>" }, "conversion", url);
    assert.equal(decodeURIComponent(source.split(",", 2)[1]), "<svg/>");
});
