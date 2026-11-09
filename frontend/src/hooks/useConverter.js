import { useCallback, useEffect, useRef, useState } from "react";
import {
    ACCEPTED_EXTENSIONS, MAX_UPLOAD_MB, checkHealth, deleteConversion,
    downloadFile, getConversion, jsonUrl, uploadDocument, zipUrl,
} from "../services/converterApi";

const POLL_INTERVAL_MS = 1200;
const IN_PROGRESS = ["queued", "processing"];

function wait(milliseconds, signal) {
    return new Promise((resolve, reject) => {
        const timer = setTimeout(resolve, milliseconds);
        signal.addEventListener("abort", () => {
            clearTimeout(timer);
            reject(new DOMException("Cancelled", "AbortError"));
        }, { once: true });
    });
}

function validateFiles(files) {
    const total = files.reduce((sum, file) => sum + file.size, 0);
    for (const file of files) {
        const extension = file.name.split(".").pop()?.toLowerCase();
        if (!ACCEPTED_EXTENSIONS.includes(extension)) return `${file.name}: unsupported file type. Select PDF, DOCX, or TXT files.`;
        if (!file.size) return `${file.name}: file is empty.`;
    }
    if (total > MAX_UPLOAD_MB * 1024 * 1024) return `Combined upload exceeds the ${MAX_UPLOAD_MB} MB limit.`;
    if (files.length > 2) return "Upload one question paper and optionally one answer key.";
    return "";
}

export function useConverter() {
    const [files, setFiles] = useState([]);
    const [roles, setRoles] = useState([]);
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
    const file = files[0] ?? null;

    const clearState = useCallback(() => {
        setFiles([]); setRoles([]); setPhase("idle"); setUploadProgress(0);
        setProgress(0); setStage(""); setResult(null); setConversionId(null);
        setError(""); setDownloadError("");
    }, []);

    const reset = useCallback(() => {
        controllerRef.current?.abort();
        controllerRef.current = null;
        busyRef.current = false;
        const previousId = conversionIdRef.current;
        conversionIdRef.current = null;
        if (previousId) deleteConversion(previousId).catch(() => {});
        clearState();
    }, [clearState]);

    const selectFiles = useCallback((incoming) => {
        if (busyRef.current) return;
        const selected = Array.from(incoming ?? []);
        reset();
        if (!selected.length) return;
        const validation = validateFiles(selected);
        if (validation) { setError(validation); return; }
        if (new Set(selected.map((item) => item.name)).size !== selected.length) {
            setError("Selected files must have different filenames so their roles can be identified."); return;
        }
        setFiles(selected);
        setRoles(selected.map((_, index) => index === 0 ? "question_paper" : "answer_key"));
    }, [reset]);

    const setFileRole = useCallback((index, role) => {
        setRoles((current) => current.map((value, itemIndex) => {
            if (itemIndex === index) return role;
            return role === "question_paper" ? "answer_key" : value;
        }));
        setError("");
    }, []);

    const removeFile = useCallback((index) => {
        setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index));
        setRoles((current) => current.filter((_, itemIndex) => itemIndex !== index));
        setError("");
    }, []);

    const runConversion = useCallback(async () => {
        if (busyRef.current) return;
        const validation = validateFiles(files);
        if (validation) { setError(validation); return; }
        if (roles.filter((role) => role === "question_paper").length !== 1) {
            setError("Choose exactly one question paper before processing."); return;
        }
        const controller = new AbortController();
        controllerRef.current = controller;
        busyRef.current = true;
        setError(""); setPhase("uploading"); setUploadProgress(0);
        try {
            await checkHealth(controller.signal);
            const roleMap = Object.fromEntries(files.map((item, index) => [item.name, roles[index]]));
            const created = await uploadDocument(files, { roles: roleMap, signal: controller.signal, onProgress: setUploadProgress });
            conversionIdRef.current = created.conversion_id;
            setConversionId(created.conversion_id);
            setUploadProgress(100); setPhase("processing");
            let status = created;
            while (IN_PROGRESS.includes(status.status)) {
                setProgress(status.progress ?? 0); setStage(status.stage ?? "");
                await wait(POLL_INTERVAL_MS, controller.signal);
                status = await getConversion(created.conversion_id, controller.signal);
            }
            if (status.status !== "completed" || !status.result) throw new Error(status.error || "The conversion failed.");
            setResult(status.result); setProgress(100); setPhase("completed");
        } catch (caught) {
            if (controller.signal.aborted) return;
            setError(caught.message); setPhase("failed");
        } finally {
            if (controllerRef.current === controller) busyRef.current = false;
        }
    }, [files, roles]);

    const download = useCallback(async (kind) => {
        if (!conversionId || downloading) return;
        const stem = file?.name.replace(/\.[^.]+$/, "") || "docujson";
        setDownloading(kind); setDownloadError("");
        try {
            await downloadFile(kind === "zip" ? zipUrl(conversionId) : jsonUrl(conversionId), kind === "zip" ? `${stem}_with_media.zip` : `${stem}.json`);
        } catch (caught) { setDownloadError(caught.message); }
        finally { setDownloading(null); }
    }, [conversionId, downloading, file]);

    useEffect(() => () => controllerRef.current?.abort(), []);
    return { file, files, roles, phase, uploadProgress, progress, stage, result, conversionId, error, downloading, downloadError, selectFiles, setFileRole, removeFile, runConversion, reset, download };
}
