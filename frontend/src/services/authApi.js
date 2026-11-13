
import { API_BASE_URL, NETWORK_ERROR } from "./converterApi";
import { getCsrfToken } from "./csrfApi";

async function readError(response) {
    try {
        const body = await response.json();

        if (typeof body.detail === "string") {
            return body.detail;
        }

        if (Array.isArray(body.detail)) {
            return body.detail
                .map((item) => item.msg)
                .join("; ");
        }
    } catch {
        // Response was not JSON.
    }

    return `Request failed (${response.status}).`;
}

async function request(path, options = {}) {
    let response;

    try {
        response = await fetch(`${API_BASE_URL}${path}`, {
            ...options,
            credentials: "include",
        });
    } catch (error) {
        if (error.name === "AbortError") {
            throw error;
        }

        throw new Error(NETWORK_ERROR);
    }

    if (!response.ok) {
        const error = new Error(await readError(response));
        error.status = response.status;
        throw error;
    }

    return response.json();
}

async function csrfRequest(path, body) {
    const token = await getCsrfToken(API_BASE_URL);

    return request(path, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": token,
        },
        body: JSON.stringify(body),
    });
}

export function register(payload) {
    return csrfRequest("/api/auth/register", payload);
}

export function login(payload) {
    return csrfRequest("/api/auth/login", payload);
}

export function getCurrentUser() {
    return request("/api/auth/me");
}

export async function logout() {
    const token = await getCsrfToken(API_BASE_URL);

    return request("/api/auth/logout", {
        method: "POST",
        headers: {
            "X-CSRF-Token": token,
        },
    });
}
