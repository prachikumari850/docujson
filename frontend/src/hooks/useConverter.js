import { useCallback, useEffect, useRef, useState } from "react";
import {
    ACCEPTED_EXTENSIONS,
    MAX_UPLOAD_MB,
    deleteConversion,
    downloadFile,
    getConversion,
    jsonUrl,
    uploadDocument,
    zipUrl,
} from "../services/converterApi";

const POLL_INTERVAL_MS = 1000;
const IN_PROGRESS = ["queued", "processing"];

function validateFile(file) {
    const extension = file.name.split(".").pop()?.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(extension)) {
        return "Unsupported file type. Please upload a PDF, DOCX or TXT file.";
    }
    if (file.size === 0) return "This file is empty.";
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
        return `This file is larger than the ${MAX_UPLOAD_MB} MB limit.`;
    }
    return "";
}

function wait(milliseconds, signal) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(resolve, milliseconds);
        signal.addEventListener(
            "abort",
            () => {
                clearTimeout(timer);
                reject(new DOMException("Cancelled", "AbortError"));
            },
            { once: true }
        );
    });
}

export function useConverter() {
    const [file, setFile] = useState(null);
    const [phase, setPhase] = useState("idle");
    const [uploadProgress, setUploadProgress] = useState(0);
    const [progress, setProgress] = useState(0);
    const [stage, setStage] = useState("");
    const [result, setResult] = useState(null);
    const [conversionId, setConversionId] = useState(null);
    const [error, setError] = useState("");
    const [downloading, setDownloading] = useState(null);
    const [downloadError, setDownloadError] = useState("");

    const controllerRef = useRef(null);
    const busyRef = useRef(false);
    const conversionIdRef = useRef(null);

    const clearState = useCallback(() => {
        setFile(null);
        setPhase("idle");
        setUploadProgress(0);
        setProgress(0);
        setStage("");
        setResult(null);
        setConversionId(null);
        setError("");
        setDownloadError("");
    }, []);

    const reset = useCallback(() => {
        controllerRef.current?.abort();
        controllerRef.current = null;
        busyRef.current = false;
        const previousId = conversionIdRef.current;
        conversionIdRef.current = null;
        if (previousId) deleteConversion(previousId).catch(() => { });
        clearState();
    }, [clearState]);

    const runConversion = useCallback(async (selectedFile) => {
        const controller = new AbortController();
        controllerRef.current = controller;
        busyRef.current = true;
        setPhase("uploading");

        try {
            const created = await uploadDocument(selectedFile, {
                signal: controller.signal,
                onProgress: setUploadProgress,
            });
            conversionIdRef.current = created.conversion_id;
            setConversionId(created.conversion_id);
            setUploadProgress(100);
            setPhase("processing");

            let status = created;
            while (IN_PROGRESS.includes(status.status)) {
                setProgress(status.progress ?? 0);
                setStage(status.stage ?? "");
                await wait(POLL_INTERVAL_MS, controller.signal);
                status = await getConversion(created.conversion_id, controller.signal);
            }

            if (status.status !== "completed" || !status.result) {
                throw new Error(status.error || "The conversion failed.");
            }
            setResult(status.result);
            setPhase("completed");
        } catch (caught) {
            if (controller.signal.aborted) return;
            setError(caught.message);
            setPhase("failed");
        } finally {
            if (controllerRef.current === controller) busyRef.current = false;
        }
    }, []);

    const selectFile = useCallback(
        (candidate) => {
            if (!candidate || busyRef.current) return;
            const problem = validateFile(candidate);
            reset();
            if (problem) {
                setError(problem);
                return;
            }
            setFile(candidate);
            runConversion(candidate);
        },
        [reset, runConversion]
    );

    const download = useCallback(
        async (kind) => {
            if (!conversionId || downloading) return;
            const stem = file?.name.replace(/\.[^.]+$/, "") || "docujson";
            setDownloading(kind);
            setDownloadError("");
            try {
                const url = kind === "zip" ? zipUrl(conversionId) : jsonUrl(conversionId);
                await downloadFile(url, `${stem}.${kind}`);
            } catch (caught) {
                setDownloadError(caught.message);
            } finally {
                setDownloading(null);
            }
        },
        [conversionId, downloading, file]
    );

    useEffect(() => () => controllerRef.current?.abort(), []);

    return {
        file,
        phase,
        uploadProgress,
        progress,
        stage,
        result,
        conversionId,
        error,
        downloading,
        downloadError,
        selectFile,
        reset,
        download,
    };
}