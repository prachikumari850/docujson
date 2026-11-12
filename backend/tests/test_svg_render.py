import xml.etree.ElementTree as ET
import fitz

from PIL import Image

from app.services.svg_render import attach_raster_svg_wrappers, create_raster_svg_wrapper, reconstruct_pdf_vector_svg


def test_png_wrapper_is_valid_references_original_and_preserves_aspect_ratio(tmp_path):
    source = tmp_path / "diagram.png"
    wrapper = tmp_path / "diagram.png.wrapper.svg"
    Image.new("RGB", (320, 180), "white").save(source)

    metadata = create_raster_svg_wrapper(source, wrapper)
    root = ET.parse(wrapper).getroot()

    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.attrib["viewBox"] == "0 0 320 180"
    image = root.find("{http://www.w3.org/2000/svg}image")
    assert image is not None
    assert image.attrib["href"] == source.name
    assert image.attrib["preserveAspectRatio"] == "xMidYMid meet"
    assert metadata["representation"] == "svg_wrapper"
    assert metadata["width_px"] / metadata["height_px"] == 320 / 180
    assert source.is_file() and wrapper.is_file()


def test_jpeg_wrapper_and_invalid_svg_destination(tmp_path):
    source = tmp_path / "figure.jpg"
    Image.new("RGB", (120, 240), "white").save(source, format="JPEG")

    metadata = create_raster_svg_wrapper(source, tmp_path / "figure.svg")
    assert metadata["media_type"] == "image/jpeg"
    assert metadata["width_px"] == 120
    assert metadata["height_px"] == 240

    try:
        create_raster_svg_wrapper(source, tmp_path / "renamed.png")
    except ValueError as error:
        assert ".svg" in str(error)
    else:
        raise AssertionError("A raster destination must not be accepted as SVG")


def test_wrapper_attachment_is_deduplicated_and_keeps_raster_references(tmp_path):
    source = tmp_path / "option.png"
    Image.new("RGB", (64, 48), "white").save(source)
    asset = {"asset_id": "m1", "filename": source.name, "type": "option_crop"}
    sections = [{"questions": [{"media": [asset], "options": [{"id": "1", "media": [asset]}]}]}]

    wrapped = attach_raster_svg_wrappers(sections, tmp_path)

    assert wrapped == [source.name]
    assert asset["filename"] == source.name
    assert asset["representation"] == "svg_wrapper"
    assert asset["svg_filename"] == "option.png.wrapper.svg"
    assert (tmp_path / asset["svg_filename"]).is_file()


def test_pdf_graph_primitives_and_labels_reconstruct_as_genuine_svg(tmp_path):
    document = fitz.open()
    page = document.new_page(width=300, height=220)
    # Source-backed graph axes, ticks, a cubic curve, and a labeled arrow.
    page.draw_line((40, 180), (260, 180), color=(0, 0, 0), width=1)
    page.draw_line((50, 195), (50, 25), color=(0, 0, 0), width=1)
    page.draw_bezier((55, 165), (95, 70), (170, 70), (245, 40), color=(0.1, 0.2, 0.8), width=1.5)
    page.draw_line((150, 150), (210, 110), color=(0.8, 0.1, 0.1), width=1.3)
    page.draw_polyline([(210, 110), (202, 111), (207, 118)], color=(0.8, 0.1, 0.1), closePath=True, fill=(0.8, 0.1, 0.1))
    page.insert_text((220, 108), "x-axis", fontsize=9)
    drawings = page.get_drawings()
    destination = tmp_path / "graph.svg"
    result = reconstruct_pdf_vector_svg(page, drawings, fitz.Rect(30, 20, 275, 205), destination)
    document.close()

    assert result is not None
    root = ET.parse(destination).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    assert root.attrib["viewBox"].startswith("0 0 ")
    assert root.find(".//{http://www.w3.org/2000/svg}path") is not None
    assert root.find(".//{http://www.w3.org/2000/svg}text") is not None
    assert root.find(".//{http://www.w3.org/2000/svg}image") is None
    assert result["representation"] == "svg_vector"
    assert result["vector_primitive_count"] >= 1


def test_raster_only_region_is_not_claimed_as_vector(tmp_path):
    document = fitz.open()
    page = document.new_page(width=200, height=160)
    destination = tmp_path / "raster.svg"
    result = reconstruct_pdf_vector_svg(page, [], page.rect, destination)
    document.close()
    assert result is None
    assert not destination.exists()

    source = tmp_path / "original.png"
    Image.new("RGB", (160, 100), "white").save(source)
    asset = {"asset_id": "r1", "filename": source.name, "type": "image", "media_format": "raster_original"}
    wrapped = attach_raster_svg_wrappers([{"questions": [{"media": [asset], "options": []}]}], tmp_path)
    assert wrapped == [source.name]
    assert asset["representation"] == "svg_wrapper"
    assert asset["media_format"] == "svg_raster_wrapper"
    assert asset["svg_genuine_vector"] is False
    assert source.is_file()


def test_rotated_page_uses_raster_fallback_until_coordinates_are_unambiguous(tmp_path):
    document = fitz.open()
    page = document.new_page(width=200, height=140)
    page.draw_line((40, 80), (160, 80), color=(0, 0, 0), width=1)
    page.set_rotation(90)
    result = reconstruct_pdf_vector_svg(page, page.get_drawings(), page.rect, tmp_path / "rotated.svg")
    document.close()
    assert result is None
    assert not (tmp_path / "rotated.svg").exists()


def test_genuine_vector_media_is_not_wrapped_or_relabelled(tmp_path):
    source = tmp_path / "diagram.png"
    Image.new("RGB", (100, 80), "white").save(source)
    asset = {"asset_id": "v1", "filename": source.name, "type": "diagram", "svg_filename": "diagram.svg", "representation": "svg_vector", "media_format": "svg_vector", "svg_genuine_vector": True}
    assert attach_raster_svg_wrappers([{"questions": [{"media": [asset], "options": []}]}], tmp_path) == []
    assert asset["representation"] == "svg_vector"
    assert not (tmp_path / "diagram.png.wrapper.svg").exists()
