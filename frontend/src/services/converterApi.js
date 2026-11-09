export const API_BASE_URL = (
    import.meta.env.VITE_API_BASE_URL ??
    "http://127.0.0.1:8000"
).replace(/\/$/, "");

export const MAX_UPLOAD_MB = Number(
    import.meta.env.VITE_MAX_UPLOAD_MB ?? 50
);

export const ACCEPTED_EXTENSIONS = [
    "pdf",
    "docx",
    "txt",
];

export const NETWORK_ERROR =
    "Cannot connect to the DocuJSON backend. Start the backend server at http://127.0.0.1:8000.";

function extractDetail(body) {
    if (!body) return "";

    if (typeof body.detail === "string") {
        return body.detail;
    }

    if (Array.isArray(body.detail)) {
        return body.detail
            .map((item) => item.msg)
            .join("; ");
    }

    return "";
}

async function readError(response) {
    try {
        const body = await response.json();
        const detail = extractDetail(body);

        if (detail) return detail;
    } catch {
        // The response was not JSON.
    }

    return `Request failed (${response.status}).`;
}

async function requestJson(path, options = {}) {
    let response;

    try {
        response = await fetch(
            `${API_BASE_URL}${path}`,
            options
        );
    } catch (error) {
        if (error.name === "AbortError") {
            throw error;
        }

        throw new Error(NETWORK_ERROR);
    }

    if (!response.ok) {
        throw new Error(
            await readError(response)
        );
    }

    return response.json();
}

export function uploadDocument(
    files,
    { roles = {}, onProgress, signal } = {}
) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const form = new FormData();

        Array.from(files).forEach((file) => {
            form.append("files", file, file.name);
        });

        form.append(
            "roles",
            JSON.stringify(roles)
        );

        xhr.open(
            "POST",
            `${API_BASE_URL}/api/convert`
        );

        xhr.responseType = "json";

        xhr.upload.onprogress = (event) => {
            if (event.lengthComputable) {
                onProgress?.(
                    Math.round(
                        (event.loaded / event.total) * 100
                    )
                );
            }
        };

        xhr.onload = () => {
            if (
                xhr.status >= 200 &&
                xhr.status < 300 &&
                xhr.response
            ) {
                resolve(xhr.response);
                return;
            }

            reject(
                new Error(
                    extractDetail(xhr.response) ||
                    `Upload failed (${xhr.status}).`
                )
            );
        };

        xhr.onerror = () => {
            reject(new Error(NETWORK_ERROR));
        };

        xhr.ontimeout = () => {
            reject(
                new Error("The upload timed out.")
            );
        };

        if (signal) {
            if (signal.aborted) {
                xhr.abort();
                reject(
                    new DOMException(
                        "Upload cancelled",
                        "AbortError"
                    )
                );
                return;
            }

            signal.addEventListener(
                "abort",
                () => {
                    xhr.abort();

                    reject(
                        new DOMException(
                            "Upload cancelled",
                            "AbortError"
                        )
                    );
                },
                { once: true }
            );
        }

        xhr.send(form);
    });
}

export function checkHealth(signal) {
    return requestJson("/api/health", { signal });
}

export function getConversion(
    conversionId,
    signal
) {
    return requestJson(
        `/api/conversions/${encodeURIComponent(conversionId)}`,
        { signal }
    );
}

export async function deleteConversion(
    conversionId
) {
    await fetch(
        `${API_BASE_URL}/api/conversions/${encodeURIComponent(conversionId)}`,
        { method: "DELETE" }
    );
}

export const jsonUrl = (conversionId) =>
    `${API_BASE_URL}/api/conversions/${encodeURIComponent(conversionId)}/json`;

export const zipUrl = (conversionId) =>
    `${API_BASE_URL}/api/conversions/${encodeURIComponent(conversionId)}/zip`;

export const mediaUrl = (
    conversionId,
    filename
) =>
    `${API_BASE_URL}/api/conversions/${encodeURIComponent(conversionId)}/media/${encodeURIComponent(filename)}`;

function filenameFromHeader(header) {
    const match = header?.match(
        /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i
    );

    return match
        ? decodeURIComponent(match[1])
        : null;
}

export async function downloadFile(
    url,
    fallbackName
) {
    let response;

    try {
        response = await fetch(url);
    } catch {
        throw new Error(NETWORK_ERROR);
    }

    if (!response.ok) {
        throw new Error(
            await readError(response)
        );
    }

    const blob = await response.blob();

    const filename =
        filenameFromHeader(
            response.headers.get("Content-Disposition")
        ) ?? fallbackName;

    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");

    anchor.href = objectUrl;
    anchor.download = filename;

    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();

    setTimeout(() => {
        URL.revokeObjectURL(objectUrl);
    }, 1000);
}
