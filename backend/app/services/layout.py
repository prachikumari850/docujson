
from __future__ import annotations

from statistics import median


def _coordinates(bbox) -> tuple[float, float, float, float]:
    if hasattr(bbox, "x0"):
        values = (bbox.x0, bbox.y0, bbox.x1, bbox.y1)
    else:
        values = bbox

    x0, y0, x1, y1 = (float(value) for value in values)

    if x1 < x0 or y1 < y0:
        raise ValueError("Bounding box coordinates are invalid.")

    return x0, y0, x1, y1


def _line_data(lines) -> list[dict]:
    result = []

    for index, line in enumerate(lines):
        if len(line) < 4:
            raise ValueError(
                f"Line at index {index} must contain at least four fields."
            )

        x0, y0, x1, y1 = _coordinates(line[3])

        if x1 == x0 or y1 == y0:
            continue

        result.append(
            {
                "index": index,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "width": x1 - x0,
                "height": y1 - y0,
                "center_x": (x0 + x1) / 2,
                "center_y": (y0 + y1) / 2,
            }
        )

    return result


def _vertical_overlap(first, second) -> float:
    overlap = max(
        0.0,
        min(first["y1"], second["y1"])
        - max(first["y0"], second["y0"]),
    )

    smaller_height = min(
        first["y1"] - first["y0"],
        second["y1"] - second["y0"],
    )

    return overlap / smaller_height if smaller_height > 0 else 0.0



def _candidate_columns(lines, page_width: float) -> list[list[dict]]:
    if not lines:
        return []

    minimum_width = max(12.0, page_width * 0.025)
    spanning_threshold = page_width * 0.68
    minimum_gutter = max(5.0, page_width * 0.008)

    body_lines = [
        line
        for line in lines
        if minimum_width <= line["width"] < spanning_threshold
    ]

    if len(body_lines) < 4:
        return []

    boundaries = sorted({
        round(value, 2)
        for line in body_lines
        for value in (line["x0"], line["x1"])
    })

    rows = []

    for line in sorted(body_lines, key=lambda item: item["center_y"]):
        if not rows or line["center_y"] - median(
            item["center_y"] for item in rows[-1]
        ) > 14:
            rows.append([line])
        else:
            rows[-1].append(line)

    candidates = []

    for left, right in zip(boundaries, boundaries[1:]):
        gap = right - left

        if gap < minimum_gutter:
            continue

        left_lines = [
            line for line in body_lines
            if line["x1"] <= left + 1.0
        ]

        right_lines = [
            line for line in body_lines
            if line["x0"] >= right - 1.0
        ]

        if len(left_lines) < 2 or len(right_lines) < 2:
            continue

        left_top = min(line["y0"] for line in left_lines)
        left_bottom = max(line["y1"] for line in left_lines)
        right_top = min(line["y0"] for line in right_lines)
        right_bottom = max(line["y1"] for line in right_lines)

        overlap = max(
            0.0,
            min(left_bottom, right_bottom)
            - max(left_top, right_top),
        )

        support = min(
            left_bottom - left_top,
            right_bottom - right_top,
        )

        if support <= 0 or overlap / support < 0.35:
            continue

        paired_rows = 0
        crossing_rows = 0

        for row in rows:
            has_left = any(
                line["x1"] <= left + 1.0
                for line in row
            )

            has_right = any(
                line["x0"] >= right - 1.0
                for line in row
            )

            has_crossing = any(
                line["x0"] <= left + 1.0
                and line["x1"] >= right - 1.0
                for line in row
            )

            if has_left and has_right:
                paired_rows += 1

            if has_crossing:
                crossing_rows += 1

        if paired_rows < 2:
            continue

        # A real page gutter should have more paired rows than
        # rows containing text that crosses the proposed gutter.
        if crossing_rows >= paired_rows:
            continue

        score = (
            paired_rows - crossing_rows * 1.5,
            paired_rows,
            -crossing_rows,
            gap,
        )

        candidates.append({
            "left": left,
            "right": right,
            "score": score,
        })

    if not candidates:
        return []

    # Select the strongest independent gutters. This prevents
    # repeated local whitespace gaps from becoming extra columns.
    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    selected = []

    for candidate in candidates:
        if any(
            candidate["left"] <= existing["right"]
            and candidate["right"] >= existing["left"]
            for existing in selected
        ):
            continue

        selected.append(candidate)

        # Three gutters are sufficient for layouts of up to four columns.
        if len(selected) == 3:
            break

    if not selected:
        return []

    selected.sort(key=lambda item: item["left"])

    page_left = min(line["x0"] for line in body_lines)
    page_right = max(line["x1"] for line in body_lines)

    column_ranges = []
    previous_right = page_left

    for gutter in selected:
        column_ranges.append((previous_right, gutter["left"]))
        previous_right = gutter["right"]

    column_ranges.append((previous_right, page_right))

    components = []

    for column_left, column_right in column_ranges:
        members = [
            line for line in body_lines
            if column_left <= line["center_x"] <= column_right
        ]

        if len(members) >= 2:
            components.append(members)

    if len(components) < 2:
        return []

    components.sort(
        key=lambda component: median(
            line["center_x"] for line in component
        )
    )

    return components


def _cluster_columns(lines, page_width: float) -> list[dict]:
    if not lines:
        return []

    components = _candidate_columns(lines, page_width)

    if len(components) < 2:
        return [
            {
                "column_index": 0,
                "bbox": [
                    min(item["x0"] for item in lines),
                    min(item["y0"] for item in lines),
                    max(item["x1"] for item in lines),
                    max(item["y1"] for item in lines),
                ],
                "line_indices": sorted(
                    item["index"] for item in lines
                ),
            }
        ]

    columns = []

    for index, component in enumerate(components):
        columns.append({
            "column_index": index,
            "bbox": [
                min(item["x0"] for item in component),
                min(item["y0"] for item in component),
                max(item["x1"] for item in component),
                max(item["y1"] for item in component),
            ],
            "line_indices": sorted(
                item["index"] for item in component
            ),
        })

    assigned = {
        index
        for column in columns
        for index in column["line_indices"]
    }

    # Assign short question numbers using column boundaries.
    for line in lines:
        if line["index"] in assigned:
            continue

        if line["width"] >= page_width * 0.68:
            continue

        best_column = None
        best_distance = float("inf")

        for column in columns:
            x0, _, x1, _ = column["bbox"]

            if line["x1"] <= x0:
                distance = x0 - line["x1"]
            elif line["x0"] >= x1:
                distance = line["x0"] - x1
            else:
                distance = 0.0

            if distance < best_distance:
                best_distance = distance
                best_column = column

        if best_column is not None and best_distance <= max(
            32.0,
            page_width * 0.06,
        ):
            best_column["line_indices"].append(line["index"])

        for column in columns:
            column["line_indices"] = sorted(
                set(column["line_indices"])
        )

    return columns


def _is_spanning_line(line, columns, page_width: float) -> bool:
    if line["width"] >= page_width * 0.68:
        return True

    if len(columns) < 2:
        return False

    minimum_width = max(24.0, page_width * 0.12)

    if line["width"] < minimum_width:
        return False

    ordered_columns = sorted(
        columns,
        key=lambda column: column["bbox"][0],
    )

    for left_column, right_column in zip(
        ordered_columns,
        ordered_columns[1:],
    ):
        gutter_left = left_column["bbox"][2]
        gutter_right = right_column["bbox"][0]

        if gutter_left >= gutter_right:
            continue

        gutter_center = (gutter_left + gutter_right) / 2

        if line["x0"] < gutter_center < line["x1"]:
            return True

    return False

def _build_regions(lines, columns, page_width: float, page_height: float):
    spanning = [
        line
        for line in lines
        if len(columns) > 1
        and _is_spanning_line(line, columns, page_width)
    ]

    spanning_indices = {
        line["index"] for line in spanning
    }

    spanning.sort(
        key=lambda item: (item["center_y"], item["x0"])
    )

    separators = [
        line["center_y"]
        for line in spanning
    ]

    regions = []
    reading_order = []
    line_order = []
    region_number = 1

    def add_region(region_type, items, column_index=None):
        nonlocal region_number

        if not items:
            return

        items = sorted(
            items,
            key=lambda item: (item["y0"], item["x0"]),
        )

        region_id = f"r{region_number}"
        region_number += 1

        regions.append({
            "region_id": region_id,
            "region_type": region_type,
            "bbox": [
                min(item["x0"] for item in items),
                min(item["y0"] for item in items),
                max(item["x1"] for item in items),
                max(item["y1"] for item in items),
            ],
            "column_index": column_index,
            "line_indices": [
                item["index"] for item in items
            ],
            "reading_order": len(reading_order) + 1,
            "confidence": 1.0,
        })

        reading_order.append(region_id)
        line_order.extend(
            item["index"] for item in items
        )

    if len(columns) < 2:
        add_region("content", lines)
        return regions, reading_order, line_order

    column_assignments = {
        column["column_index"]: []
        for column in columns
    }

    for line in lines:
        if line["index"] in spanning_indices:
            continue

        best_column = min(
            columns,
            key=lambda column: (
                max(
                    column["bbox"][0] - line["center_x"],
                    0.0,
                    line["center_x"] - column["bbox"][2],
                ),
                abs(
                    line["center_x"]
                    - (
                        column["bbox"][0]
                        + column["bbox"][2]
                    ) / 2
                ),
            ),
        )

        column_assignments[
            best_column["column_index"]
        ].append(line)

    band_count = len(separators) + 1

    bands = {
        index: {
            column["column_index"]: []
            for column in columns
        }
        for index in range(band_count)
    }

    for column_index, assigned_lines in column_assignments.items():
        for line in assigned_lines:
            band_index = sum(
                separator < line["center_y"]
                for separator in separators
            )

            bands[band_index][column_index].append(line)

    for band_index in range(band_count):
        for column in columns:
            column_index = column["column_index"]

            add_region(
                "column",
                bands[band_index][column_index],
                column_index,
            )

        if band_index < len(spanning):
            add_region(
                "spanning",
                [spanning[band_index]],
            )

    assigned = set(line_order)

    unassigned = [
        line
        for line in lines
        if line["index"] not in assigned
    ]

    if unassigned:
        add_region("unassigned", unassigned)

    return regions, reading_order, line_order

def detect_page_layout(
    lines,
    page_width: float,
    page_height: float,
    drawings=None,
    images=None,
) -> dict:
    if page_width <= 0 or page_height <= 0:
        raise ValueError("Page dimensions must be positive.")

    line_data = _line_data(lines)

    if not line_data:
        return {
            "page_width": float(page_width),
            "page_height": float(page_height),
            "layout_type": "empty",
            "columns": [],
            "regions": [],
            "reading_order": [],
            "line_order": [],
            "confidence": 1.0,
            "warnings": [],
        }

    columns = _cluster_columns(line_data, page_width)

    regions, reading_order, line_order = _build_regions(
        line_data,
        columns,
        page_width,
        page_height,
    )

    column_count = len(columns)

    if column_count == 0:
        layout_type = "spanning"
    elif column_count == 1:
        layout_type = "single_column"
    else:
        layout_type = "multi_column"

    warnings = []

    if column_count > 4:
        warnings.append(
            "More than four candidate columns detected; inspect the layout."
        )

    if len(line_order) != len(set(line_order)):
        warnings.append(
            "Some lines appear more than once in reading order."
        )

    expected_indices = {item["index"] for item in line_data}

    if set(line_order) != expected_indices:
        warnings.append(
            "Some lines could not be assigned to reading order."
        )

    confidence = 0.95

    if warnings:
        confidence = 0.5

    if column_count > 1:
        column_centers = [
            (column["bbox"][0] + column["bbox"][2]) / 2
            for column in columns
        ]

        if any(
            current <= previous
            for previous, current in zip(
                column_centers,
                column_centers[1:],
            )
        ):
            confidence = min(confidence, 0.5)

    return {
        "page_width": float(page_width),
        "page_height": float(page_height),
        "layout_type": layout_type,
        "columns": columns,
        "regions": regions,
        "reading_order": reading_order,
        "line_order": line_order,
        "confidence": confidence,
        "warnings": warnings,
    }
