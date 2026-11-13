
const CSRF_COOKIE = "neetday_csrf";

function readCookie(name) {
    const prefix = `${name}=`;

    const cookie = document.cookie
        .split("; ")
        .find((item) => item.startsWith(prefix));

    return cookie
        ? decodeURIComponent(cookie.slice(prefix.length))
        : null;
}

export async function getCsrfToken(apiBaseUrl) {
    let response;

    try {
        response = await fetch(
            `${apiBaseUrl}/api/auth/csrf`,
            {
                credentials: "include",
            }
        );
    } catch {
        throw new Error("Unable to connect to the backend.");
    }

    if (!response.ok) {
        throw new Error(
            `Unable to initialize security token (${response.status}).`
        );
    }

    const data = await response.json();
    const cookieToken = readCookie(CSRF_COOKIE);

    if (
        !data.csrf_token ||
        !cookieToken ||
        data.csrf_token !== cookieToken
    ) {
        throw new Error(
            "Unable to initialize security token. Please retry."
        );
    }

    return data.csrf_token;
}

export async function getCsrfHeaders(apiBaseUrl) {
    const token = await getCsrfToken(apiBaseUrl);

    return {
        "X-CSRF-Token": token,
    };
}
