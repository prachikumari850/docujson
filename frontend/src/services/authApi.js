
import { API_BASE_URL, NETWORK_ERROR } from "./converterApi";

const CSRF_COOKIE = "neetday_csrf";

let csrfToken = null;

function readCookie(name) {
    const prefix = `${name}=`;

    const cookie = document.cookie
        .split("; ")
        .find((item) => item.startsWith(prefix));

    return cookie
        ? decodeURIComponent(cookie.slice(prefix.length))
        : null;
}

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

async function getCsrfToken() {
    const response = await request("/api/auth/csrf");

    csrfToken = response.csrf_token;

    const cookieToken = readCookie(CSRF_COOKIE);

    if (!csrfToken || !cookieToken || csrfToken !== cookieToken) {
        csrfToken = null;
        throw new Error("Unable to initialize security token. Please retry.");
    }

    return csrfToken;
}

async function csrfRequest(path, body) {
    const token = await getCsrfToken();

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

export async function getCurrentUser() {
    return request("/api/auth/me");
}

export async function logout() {
    const token = await getCsrfToken();

    try {
        return await request("/api/auth/logout", {
            method: "POST",
            headers: {
                "X-CSRF-Token": token,
            },
        });
    } finally {
        csrfToken = null;
    }
}
