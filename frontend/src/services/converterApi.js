
import { createUploadFormData } from "../utils/uploadFormData";
import { getCsrfHeaders } from "./csrfApi";

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
    "Cannot connect to the NEETDAY backend. Start the backend server at http://127.0.0.1:8000.";

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
            {
                ...options,
                credentials: "include",
            }
        );
    } catch (error) {
        if (error.name === "AbortError") {
            throw error;
        }

        throw new Error(NETWORK_ERROR);
    }

    if (!response.ok) {
        throw new Error(await readError(response));
    }

    return response.json();
}

async function mutationHeaders(contentType = false) {
    const csrfHeaders = await getCsrfHeaders(API_BASE_URL);

    return {
        ...(contentType
            ? { "Content-Type": "application/json" }
            : {}),
        ...csrfHeaders,
    };
}

export async function uploadDocument(
    files,
    { roles = {}, onProgress, signal } = {}
) {
    const headers = await mutationHeaders();

    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        const form = createUploadFormData(files, roles);

        xhr.open("POST", `${API_BASE_URL}/api/convert`);
        xhr.withCredentials = true;
        xhr.responseType = "json";

        Object.entries(headers).forEach(([name, value]) => {
            xhr.setRequestHeader(name, value);
        });

        xhr.upload.onprogress = (event) => {
            if (event.lengthComputable) {
                onProgress?.(
                    Math.round((event.loaded / event.total) * 100)
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
            reject(new Error("The upload timed out."));
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

export function getAnalyticsOverview(signal) {
    return requestJson(
        "/api/analytics/overview",
        { signal }
    );
}

export function getSettings(signal) {
    return requestJson("/api/settings", { signal });
}

export function getDocuments(
    { limit = 100, offset = 0, signal } = {}
) {
    const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
    });

    return requestJson(
        `/api/documents?${params.toString()}`,
        { signal }
    );
}

export function getConversion(conversionId, signal) {
    return requestJson(
        `/api/conversions/${encodeURIComponent(conversionId)}`,
        { signal }
    );
}

export async function deleteConversion(conversionId) {
    return requestJson(
        `/api/conversions/${encodeURIComponent(conversionId)}`,
        {
            method: "DELETE",
            headers: await mutationHeaders(),
        }
    );
}

export const jsonUrl = (conversionId) =>
    `${API_BASE_URL}/api/conversions/${encodeURIComponent(conversionId)}/json`;

export const zipUrl = (conversionId) =>
    `${API_BASE_URL}/api/conversions/${encodeURIComponent(conversionId)}/zip`;

export const mediaUrl = (conversionId, filename) =>
    `${API_BASE_URL}/api/conversions/${encodeURIComponent(conversionId)}/media/${encodeURIComponent(filename)}`;

function filenameFromHeader(header) {
    const match = header?.match(
        /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i
    );

    return match ? decodeURIComponent(match[1]) : null;
}

export async function downloadFile(url, fallbackName) {
    let response;

    try {
        response = await fetch(url, {
            credentials: "include",
        });
    } catch {
        throw new Error(NETWORK_ERROR);
    }

    if (!response.ok) {
        throw new Error(await readError(response));
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

export function getQuestions(
    {
        search = "",
        questionType = "",
        reviewRequired = "",
        limit = 25,
        offset = 0,
        signal,
    } = {}
) {
    const params = new URLSearchParams({
        limit: String(limit),
        offset: String(offset),
    });

    if (search.trim()) {
        params.set("search", search.trim());
    }

    if (questionType) {
        params.set("question_type", questionType);
    }

    if (reviewRequired !== "") {
        params.set("review_required", reviewRequired);
    }

    return requestJson(
        `/api/questions?${params.toString()}`,
        { signal }
    );
}

export function getReviewQuestions(
    {
        search = "",
        decision = "pending",
        limit = 25,
        offset = 0,
        signal,
    } = {}
) {
    const params = new URLSearchParams({
        decision,
        limit: String(limit),
        offset: String(offset),
    });

    if (search.trim()) {
        params.set("search", search.trim());
    }

    return requestJson(
        `/api/review/questions?${params.toString()}`,
        { signal }
    );
}

export async function updateReviewDecision(
    conversionId,
    questionId,
    { decision, note = "" }
) {
    return requestJson(
        `/api/review/questions/${encodeURIComponent(conversionId)}/${encodeURIComponent(questionId)}`,
        {
            method: "PATCH",
            headers: await mutationHeaders(true),
            body: JSON.stringify({
                decision,
                note: note.trim() || null,
            }),
        }
    );
}

export function getAnswerKeys(
    {
        search = "",
        status = "all",
        decision = "all",
        limit = 25,
        offset = 0,
        signal,
    } = {}
) {
    const params = new URLSearchParams({
        status,
        decision,
        limit: String(limit),
        offset: String(offset),
    });

    if (search.trim()) {
        params.set("search", search.trim());
    }

    return requestJson(
        `/api/answer-keys?${params.toString()}`,
        { signal }
    );
}

export async function updateAnswerKeyDecision(
    conversionId,
    entryId,
    {
        decision,
        correctedAnswer = "",
        note = "",
    }
) {
    return requestJson(
        `/api/answer-keys/${encodeURIComponent(conversionId)}/entries/${encodeURIComponent(entryId)}`,
        {
            method: "PATCH",
            headers: await mutationHeaders(true),
            body: JSON.stringify({
                decision,
                corrected_answer: correctedAnswer.trim() || null,
                note: note.trim() || null,
            }),
        }
    );
}

export async function createPublication(conversionId) {
    return requestJson(
        `/api/conversions/${encodeURIComponent(conversionId)}/publish`,
        {
            method: "POST",
            headers: await mutationHeaders(),
        }
    );
}

export function getPublications(conversionId, signal) {
    return requestJson(
        `/api/conversions/${encodeURIComponent(conversionId)}/publications`,
        { signal }
    );
}

export function getPublication(conversionId, version, signal) {
    return requestJson(
        `/api/conversions/${encodeURIComponent(conversionId)}/publications/${encodeURIComponent(version)}`,
        { signal }
    );
}
